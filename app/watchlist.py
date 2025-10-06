# app/watchlist.py
import os
import asyncio
from datetime import datetime, timedelta
import pandas as pd

from app.config import settings
from app.polygon_client import Polygon
from app.universe import load_universe

# ICT/SMC detectors
from app.detectors.swings import swings
from app.detectors.bos import bos
from app.detectors.fvg import fvgs
from app.detectors.ob import order_blocks
from app.detectors.liquidity import equal_highs_lows

# Bias inputs
from app.bias.opex import is_opex_week
from app.bias.ddoi import ddoi_from_chain

# The Strat
from app.strat.patterns import detect_strat
from app.strat.mtf import htf_bias, mtf_align

# Scoring + Discord
from app.ranking import score
from app.notify import send_watchlist, send_entry_detail

# Throttles (edit in DO → Settings → Environment Variables)
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "25"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))

PT_TZ = settings.tz  # label only; scheduling handled in cli.py


# ---------- helpers ----------
def _targets_from_R(entry: float, stop: float, liq: list[float]) -> list[float]:
    """
    Build T1–T4 using nearest liquidity for T1/T2 and pure-R for T3/T4.
    """
    R = abs(entry - stop)
    direction_up = entry > stop
    r_targets = [entry + (i * R if direction_up else -i * R) for i in (1, 2, 3, 4)]
    liq_sorted = sorted(
        [x for x in liq if (x > entry if direction_up else x < entry)],
        key=lambda x: abs(x - entry),
    )
    t1 = liq_sorted[0] if liq_sorted else r_targets[0]
    t2 = liq_sorted[1] if len(liq_sorted) > 1 else r_targets[1]
    t3, t4 = r_targets[2], r_targets[3]
    return [round(x, 2) for x in (t1, t2, t3, t4)]


# ---------- core analysis ----------
async def analyze_symbol(
    p: Polygon, sym: str, tf: tuple[int, str] = (5, "minute")
) -> dict | None:
    """
    Pull data for one symbol, run ICT + Strat with MTF continuity,
    and produce a candidate row (or None if it doesn't meet rules/score).
    """
    # Pull ~10 calendar days to cover 5+ trading days of 5m bars
    to = datetime.utcnow().date()
    frm = (datetime.utcnow() - timedelta(days=10)).date()

    # LTF aggregates (5m)
    try:
        df = await p.aggs(sym, tf[0], tf[1], frm.isoformat(), to.isoformat())
    except Exception:
        return None
    if df.empty or len(df) < 50:
        return None
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert("America/Los_Angeles")

    # --- HTF bars for MTF continuity ---
    try:
        df_4h = await p.aggs(
            sym,
            240,
            "minute",
            (datetime.utcnow() - timedelta(days=30)).date().isoformat(),
            to.isoformat(),
        )
    except Exception:
        df_4h = None
    try:
        df_d = await p.aggs(
            sym,
            1,
            "day",
            (datetime.utcnow() - timedelta(days=60)).date().isoformat(),
            to.isoformat(),
        )
    except Exception:
        df_d = None

    # ICT detectors on LTF
    sw_hi, sw_lo = swings(df, n=3)
    bos_list = bos(df, sw_hi, sw_lo)
    fvg_list = fvgs(df)
    ob_list = order_blocks(df, bos_list)
    eqh, eql = equal_highs_lows(df)

    # The Strat on LTF + HTF bias
    strat = detect_strat(df)
    if not strat:
        return None
    bias4h = htf_bias(df_4h) if df_4h is not None and not df_4h.empty else "flat"
    bias1d = htf_bias(df_d) if df_d is not None and not df_d.empty else "flat"
    bias_dir = bias4h if bias4h != "flat" else bias1d
    if not mtf_align(strat["dir"], bias_dir):
        return None

    # Entry/stop selection using Strat direction and most recent ICT zone
    entry = None
    stop = None
    zones: list[dict] = []
    direction = "long" if strat["dir"] == "bull" else "short"

    if direction == "long":
        bull_zones = [z for z in fvg_list if z["dir"] == "bull"] + [
            z for z in ob_list if z["dir"] == "bull"
        ]
        cand = bull_zones[-1] if bull_zones else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["low"]
            zones.append({"low": cand["low"], "high": cand["high"]})
    else:
        bear_zones = [z for z in fvg_list if z["dir"] == "bear"] + [
            z for z in ob_list if z["dir"] == "bear"
        ]
        cand = bear_zones[-1] if bear_zones else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["high"]
            zones.append({"low": cand["low"], "high": cand["high"]})

    if entry is None or stop is None:
        return None

    # Options chain snapshot → DDOI + basic liquidity presence check
    try:
        chain = await p.options_chain_snapshot(sym)
    except Exception:
        chain = {}
    ddoi = ddoi_from_chain(chain)
    bias = {
        "opex_week": is_opex_week(datetime.utcnow().date()),
        "earnings_soon": False,  # can be wired via polygon_client.earnings_calendar()
        "ddoi": "pos"
        if ddoi.get("net_delta", 0) > 0
        else ("neg" if ddoi.get("net_delta", 0) < 0 else "flat"),
    }
    spread_ok = bool(chain.get("results") or chain.get("options"))

    # Confluence & score
    conf = {
        "bos": bool(bos_list),
        "fvg": bool(fvg_list),
        "ob": bool(ob_list),
        "eq_liq": bool(eqh or eql),
        "strat": True,  # required above
    }
    atr_like = float((df["high"] - df["low"]).tail(14).mean())
    sc = score(conf, bias, atr_like, spread_ok)
    if sc < settings.min_score:
        return None

    # Targets
    liq = sorted(set(eqh + eql))
    targets = _targets_from_R(entry, stop, liq)

    return {
        "symbol": sym,
        "direction": "bullish" if direction == "long" else "bearish",
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "targets": targets,
        "score": sc,
        "zones": zones,
        "bias": bias,
        "pattern": strat["name"],
        "pattern_types": strat["types"],
        "mtf_bias": bias_dir,
    }


async def generate(kind: str) -> list[dict]:
    """
    Analyze a capped universe with bounded concurrency and return sorted rows.
    Skips symbols that raise API errors to ensure the job completes.
    """
    all_syms = load_universe()
    syms = all_syms[:MAX_SYMBOLS]

    p = Polygon()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def worker(s: str):
        async with sem:
            try:
                return await analyze_symbol(p, s)
            except Exception:
                r
