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

# Projection & options
from app.options import iv_implied_move, atr20_percent, pick_best_option, PROJ_DAYS, PROJ_MIN, PROJ_MAX

# Scoring + Discord
from app.ranking import score
from app.notify import send_watchlist, send_entry_detail

# Throttles
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "25"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))

PT_TZ = settings.tz


def _targets_from_R(entry: float, stop: float, liq: list[float]) -> list[float]:
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


async def analyze_symbol(p: Polygon, sym: str, tf: tuple[int, str] = (5, "minute")) -> dict | None:
    """
    Pull data for one symbol, run ICT + Strat with MTF continuity,
    filter by 5–10% projected move (IV-first, ATR20% fallback),
    and choose best option by ROI for the direction.
    """
    # LTF aggregates (5m) ~10 calendar days
    to = datetime.utcnow().date()
    frm = (datetime.utcnow() - timedelta(days=10)).date()
    try:
        df = await p.aggs(sym, tf[0], tf[1], frm.isoformat(), to.isoformat())
    except Exception:
        return None
    if df.empty or len(df) < 50:
        return None
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert("America/Los_Angeles")

    # HTF bars (4H, 1D)
    try:
        df_4h = await p.aggs(sym, 240, "minute", (datetime.utcnow() - timedelta(days=30)).date().isoformat(), to.isoformat())
    except Exception:
        df_4h = None
    try:
        df_d = await p.aggs(sym, 1, "day", (datetime.utcnow() - timedelta(days=60)).date().isoformat(), to.isoformat())
    except Exception:
        df_d = None

    # ICT detectors on LTF
    sw_hi, sw_lo = swings(df, n=3)
    bos_list = bos(df, sw_hi, sw_lo)
    fvg_list = fvgs(df)
    ob_list = order_blocks(df, bos_list)
    eqh, eql = equal_highs_lows(df)

    # The Strat on LTF + HTF bias continuity
    strat = detect_strat(df)
    if not strat:
        return None
    bias4h = htf_bias(df_4h) if df_4h is not None and not df_4h.empty else "flat"
    bias1d = htf_bias(df_d)  if df_d  is not None and not df_d.empty  else "flat"
    bias_dir = bias4h if bias4h != "flat" else bias1d
    if not mtf_align(strat["dir"], bias_dir):
        return None

    # Direction + zone-derived entry/stop
    entry = None
    stop = None
    zones: list[dict] = []
    direction = "bullish" if strat["dir"] == "bull" else "bearish"

    if direction == "bullish":
        bull_zones = [z for z in fvg_list if z["dir"] == "bull"] + [z for z in ob_list if z["dir"] == "bull"]
        cand = bull_zones[-1] if bull_zones else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["low"]
            zones.append({"low": cand["low"], "high": cand["high"]})
    else:
        bear_zones = [z for z in fvg_list if z["dir"] == "bear"] + [z for z in ob_list if z["dir"] == "bear"]
        cand = bear_zones[-1] if bear_zones else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["high"]
            zones.append({"low": cand["low"], "high": cand["high"]})

    if entry is None or stop is None:
        return None

    # Options chain snapshot (we'll reuse for DDOI, IV, and option pick)
    try:
        chain = await p.options_chain_snapshot(sym)
    except Exception:
        chain = {}

    # Projection: IV implied move first; fallback ATR20%
    iv_move = iv_implied_move(chain, PROJ_DAYS, direction=direction)
    atr_pct = atr20_percent(df_d)
    proj_frac = max(iv_move, atr_pct)

    # Enforce 5–10% window
    if not (PROJ_MIN <= proj_frac <= PROJ_MAX):
        return None

    # Bias pack (incl. DDOI, OPEX, Earnings placeholder)
    ddoi = ddoi_from_chain(chain)
    bias = {
        "opex_week": is_opex_week(datetime.utcnow().date()),
        "earnings_soon": False,
        "ddoi": "pos" if ddoi.get("net_delta", 0) > 0 else ("neg" if ddoi.get("net_delta", 0) < 0 else "flat"),
    }
    spread_ok = bool(chain.get("results") or chain.get("options"))

    # Score & threshold
    conf = {
        "bos": bool(bos_list),
        "fvg": bool(fvg_list),
        "ob":  bool(ob_list),
        "eq_liq": bool(eqh or eql),
        "strat": True,
    }
    atr_like = float((df["high"] - df["low"]).tail(14).mean())
    sc = score(conf, bias, atr_like, spread_ok)
    if sc < settings.min_score:
        return None

    # Targets
    liq = sorted(set(eqh + eql))
    targets = _targets_from_R(entry, stop, liq)

    # Option selection (highest ROI within liquidity/delta rules)
    underlying_price = float(df["close"].iloc[-1])
    best_opt = pick_best_option(chain, underlying_price, proj_frac, direction)
    if not best_opt:
        return None  # require a tradable contract suggestion

    return {
        "symbol": sym,
        "direction": direction,
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "targets": targets,
        "score": sc,
        "zones": zones,
        "bias": bias,
        "pattern": strat["name"],
        "pattern_types": strat["types"],
        "mtf_bias": bias_dir,
        "proj_move_pct": round(proj_frac * 100.0, 1),
        "option": best_opt,
    }


async def generate(kind: str) -> list[dict]:
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
    rows = await generate(kind)
    if not rows:
        await send_watchlist(f"{kind.title()} – No Setups (min score {settings.min_score})", [])
        return

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    header = f"{kind.title()} Watchlist – {now_label}"
    fields = []
    for r in rows[:20]:
        opt = r.get("option") or {}
        opt_str = f"{opt.get('type','?')} Δ{opt.get('delta','?')} {opt.get('expiry','?')} {opt.get('strike','?')} @{opt.get('premium','?')} ROI {opt.get('roi_pct','?')}%"
        line = (
            f"{r['symbol']} {r['direction'].upper()} — {r.get('pattern','?')} | "
            f"Entry {r['entry']} | Stop {r['stop']} | T1 {r['targets'][0]} | "
            f"Score {int(r['score'])} | Proj {r.get('proj_move_pct', '?')}% | Opt {opt_str}"
        )
        fields.append(line)
    await send_watchlist(header, fields)

    # Detailed entries (top 5)
    for r in rows[:5]:
        await send_entry_detail(
            symbol=r["symbol"],
            direction=r["direction"],
            entry=float(r["entry"]),
            stop=float(r["stop"]),
            targets=[float(x) for x in r["targets"]],
            score=float(r["score"]),
            bias=r.get("bias", {}),
        )
