import os
import asyncio
from datetime import datetime, timedelta
import pandas as pd

from app.config import settings
from app.polygon_client import Polygon
from app.universe import load_universe
from app.detectors.swings import swings
from app.detectors.bos import bos
from app.detectors.fvg import fvgs
from app.detectors.ob import order_blocks
from app.detectors.liquidity import equal_highs_lows
from app.bias.opex import is_opex_week
from app.bias.ddoi import ddoi_from_chain
from app.ranking import score
from app.notify import send_watchlist, send_entry

# knobs to stay within API limits
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "25"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))

PT_TZ = settings.tz  # label only; scheduling is in cli.py


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


async def analyze_symbol(
    p: Polygon, sym: str, tf: tuple[int, str] = (5, "minute")
) -> dict | None:
    """
    Pull data for one symbol, run basic ICT detectors, compute an entry with T1–T4,
    and return a ranked row. Returns None if no valid setup or score below threshold.
    """
    # Pull ~10 calendar days to cover 5+ trading days of 5m bars
    to = datetime.utcnow().date()
    frm = (datetime.utcnow() - timedelta(days=10)).date()

    # Fetch aggregates with guard (skip symbol on any API error)
    try:
        df = await p.aggs(sym, tf[0], tf[1], frm.isoformat(), to.isoformat())
    except Exception:
        return None

    if df.empty or len(df) < 50:
        return None

    # Ensure tz-aware → convert to PT
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert("America/Los_Angeles")

    # Basic detectors
    sw_hi, sw_lo = swings(df, n=3)
    bos_list = bos(df, sw_hi, sw_lo)
    fvg_list = fvgs(df)
    ob_list = order_blocks(df, bos_list)
    eqh, eql = equal_highs_lows(df)

    # Simple directional bias from recent BOS
    long_bias = any(b["dir"] == "bull" for b in bos_list[-3:])
    short_bias = any(b["dir"] == "bear" for b in bos_list[-3:])

    entry = None
    stop = None
    zones: list[dict] = []
    direction = None

    if long_bias:
        bull_zones = [z for z in fvg_list if z["dir"] == "bull"] + [
            z for z in ob_list if z["dir"] == "bull"
        ]
        cand = bull_zones[-1] if bull_zones else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["low"]
            direction = "long"
            zones.append({"low": cand["low"], "high": cand["high"]})
    elif short_bias:
        bear_zones = [z for z in fvg_list if z["dir"] == "bear"] + [
            z for z in ob_list if z["dir"] == "bear"
        ]
        cand = bear_zones[-1] if bear_zones else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["high"]
            direction = "short"
            zones.append({"low": cand["low"], "high": cand["high"]})

    if entry is None or stop is None or direction is None:
        return None

    # Options chain snapshot → DDOI + basic liquidity presence check
    try:
        chain = await p.options_chain_snapshot(sym)
    except Exception:
        chain = {}
    ddoi = ddoi_from_chain(chain)
    bias = {
        "opex_week": is_opex_week(datetime.utcnow().date()),
        "earnings_soon": False,  # wire later
        "ddoi": "pos"
        if ddoi.get("net_delta", 0) > 0
        else ("neg" if ddoi.get("net_delta", 0) < 0 else "flat"),
    }
    spread_ok = bool(chain.get("results") or chain.get("options"))

    # Confluence flags
    conf = {
        "bos": bool(bos_list),
        "fvg": bool(fvg_list),
        "ob": bool(ob_list),
        "eq_liq": bool(eqh or eql),
    }

    # Score & threshold
    atr_like = float((df["high"] - df["low"]).tail(14).mean())
    sc = score(conf, bias, atr_like, spread_ok)
    if sc < settings.min_score:
        return None

    # Targets
    liq = sorted(set(eqh + eql))
    targets = _targets_from_R(entry, stop, liq)

    return {
        "symbol": sym,
        "direction": direction,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "targets": targets,
        "score": sc,
        "zones": zones,
        "bias": bias,
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
                return None

    try:
        tasks = [worker(s) for s in syms]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        rows = [r for r in results if isinstance(r, dict) and r]
        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows
    finally:
        await p.close()


async def post_watchlist(kind: str):
    """
    Post a watchlist to Discord; also send a few entry alerts (demo alert payloads).
    """
    rows = await generate(kind)
    if not rows:
        await send_watchlist(
            f"{kind.title()} – No Setups (min score {settings.min_score})", []
        )
        return

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    header = f"{kind.title()} Watchlist – {now_label}"
    fields = [
        f"{r['symbol']} {r['direction'].upper()} – Entry {r['entry']} | "
        f"Stop {r['stop']} | T1 {r['targets'][0]} | Score {int(r['score'])}"
        for r in rows[:20]
    ]
    await send_watchlist(header, fields)

    # Also post top 5 entries to 🚨entries (chart PNGs can be added later)
    for r in rows[:5]:
        await send_entry(r["symbol"])
