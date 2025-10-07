# app/watchlist.py
from __future__ import annotations
import os, asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
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
from app.bias.gex import compute_gex, predict_earnings_move

from app.macro import today_events_pt, header_for_events
from app.sectors import sectors_header
from app import journal
from app.ranking import score
from app.notify import send_watchlist, send_entry_detail

# ------------------------- Tunables -------------------------
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "40"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "6"))
MIN_SCORE = float(os.getenv("MIN_SCORE", str(getattr(settings, "min_score", 90))))
PROJ_DAYS = int(os.getenv("PROJ_DAYS", "10"))
PROJ_MIN = float(os.getenv("PROJ_MIN", "0.05"))
PROJ_MAX = float(os.getenv("PROJ_MAX", "0.10"))
DTE_MIN = int(os.getenv("DTE_MIN", "7"))
DTE_MAX = int(os.getenv("DTE_MAX", "14"))
DELTA_TARGET = float(os.getenv("DELTA_TARGET", "0.35"))
DELTA_BAND = float(os.getenv("DELTA_BAND", "0.10"))
DELTA_FALLBACK_MIN = float(os.getenv("DELTA_FALLBACK_MIN", "0.20"))
DELTA_FALLBACK_MAX = float(os.getenv("DELTA_FALLBACK_MAX", "0.50"))
OI_MIN = int(os.getenv("OI_MIN", "1000"))
SPREAD_MAX = float(os.getenv("SPREAD_MAX", "0.10"))
EARNINGS_FLAG_DAYS = int(os.getenv("EARNINGS_FLAG_DAYS", "7"))
GEX_WINDOW_PCT = float(os.getenv("GEX_WINDOW_PCT", "0.15"))
GEX_OI_MIN = int(os.getenv("GEX_OI_MIN", "500"))
GEX_SPREAD_MAX = float(os.getenv("GEX_SPREAD_MAX", "0.20"))

# ------------------------- Helpers -------------------------
def _targets_from_R(entry: float, stop: float, liq: List[float]) -> List[float]:
    R = abs(entry - stop)
    direction_up = entry > stop
    r_targets = [entry + (i * R if direction_up else -i * R) for i in (1, 2, 3, 4)]
    liq_sorted = sorted([x for x in liq if (x > entry if direction_up else x < entry)], key=lambda x: abs(x - entry))
    t1 = liq_sorted[0] if liq_sorted else r_targets[0]
    t2 = liq_sorted[1] if len(liq_sorted) > 1 else r_targets[1]
    return [round(t1,2), round(t2,2), round(r_targets[2],2), round(r_targets[3],2)]

def _projection_pct(df: pd.DataFrame, days: int = PROJ_DAYS) -> float:
    import numpy as np
    closes = df["close"].dropna().values.astype(float)
    if len(closes) < max(20, days + 5):
        return 0.0
    y = closes[-(days + 20):]
    x = np.arange(len(y), dtype=float)
    a, b = np.polyfit(x, y, 1)
    last = y[-1]
    proj = a * (len(y) - 1 + days) + b
    return float((proj / last) - 1.0)

def _mid(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return 0.5 * (bid + ask)

def _asfloat(x):
    try: return float(x)
    except Exception: return None

def _pick_option(chain: dict, spot: float, direction: str) -> dict | None:
    items = (chain.get("results") or chain.get("options") or [])
    if not isinstance(items, list):
        return None
    def norm(c: dict) -> dict:
        details = c.get("details", {})
        last_quote = c.get("last_quote", {}) or c.get("quote", {}) or {}
        greeks = c.get("greeks", {}) or {}
        typ = (details.get("contract_type") or c.get("contract_type") or c.get("type") or "").lower()
        strike = details.get("strike_price") or c.get("strike") or c.get("strike_price")
        expiry = details.get("expiration_date") or c.get("expiration_date") or c.get("expiry")
        delta = greeks.get("delta")
        bid = last_quote.get("bid")
        ask = last_quote.get("ask")
        oi = c.get("open_interest") or last_quote.get("open_interest") or c.get("oi")
        return {"type":typ,"strike":_asfloat(strike),"expiry":expiry,"delta":_asfloat(delta),
                "bid":_asfloat(bid),"ask":_asfloat(ask),"oi": int(oi) if isinstance(oi,(int,float)) else 0}
    want = "call" if direction == "long" else "put"
    pool = [norm(c) for c in items if isinstance(c, dict)]
    pool = [c for c in pool if c["type"] == want and c["expiry"]]
    from datetime import datetime as _dt, timedelta as _td
    today = _dt.utcnow().date()
    kept = []
    for c in pool:
        try: dte = (_dt.fromisoformat(c["expiry"]).date() - today).days
        except Exception: continue
        if dte < DTE_MIN or dte > DTE_MAX: continue
        mid = _mid(c["bid"], c["ask"])
        if mid is None: continue
        spread = (c["ask"] - c["bid"]) / mid if mid > 0 else 999.0
        if c["oi"] < OI_MIN or spread > SPREAD_MAX: continue
        c["mid"]=mid; c["spread"]=round(spread,3); c["dte"]=dte
        kept.append(c)
    if not kept: return None
    lo, hi = DELTA_TARGET - DELTA_BAND, DELTA_TARGET + DELTA_BAND
    cand = [c for c in kept if c["delta"] is not None and lo <= abs(c["delta"]) <= hi] \
        or [c for c in kept if c["delta"] is not None and DELTA_FALLBACK_MIN <= abs(c["delta"]) <= DELTA_FALLBACK_MAX] \
        or kept
    cand.sort(key=lambda c: (abs((abs(c.get("delta",0.0) or 0.0) - DELTA_TARGET)), c["spread"], c["dte"]))
    z = cand[0]
    return {"type": z["type"].upper(),"delta": round(abs(z.get("delta",0.0) or 0.0),2),
            "expiry": z["expiry"],"strike": z["strike"],"premium": round(z["mid"],2),
            "dte": int(z["dte"]),"spread": z["spread"],"oi": int(z["oi"])}

# ------------------------- Core analysis -------------------------
async def analyze_symbol(p: Polygon, sym: str, tf: Tuple[int, str]=(5,"minute")) -> dict | None:
    to = datetime.utcnow().date()
    frm = (datetime.utcnow() - timedelta(days=10)).date()
    try:
        df = await p.aggs(sym, tf[0], tf[1], frm.isoformat(), to.isoformat())
    except Exception:
        return None
    if df.empty or len(df) < 80:
        return None
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert("America/Los_Angeles")

    sw_hi, sw_lo = swings(df, n=3)
    bos_list = bos(df, sw_hi, sw_lo)
    fvg_list = fvgs(df)
    ob_list = order_blocks(df, bos_list)
    eqh, eql = equal_highs_lows(df)

    long_bias = any(b["dir"] == "bull" for b in bos_list[-3:])
    short_bias = any(b["dir"] == "bear" for b in bos_list[-3:])

    entry = stop = None
    direction = None
    zones: List[dict] = []

    if long_bias:
        z = ([z for z in fvg_list if z["dir"]=="bull"] + [z for z in ob_list if z["dir"]=="bull"]) or []
        cand = z[-1] if z else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["low"]; direction = "long"
            zones.append({"low": cand["low"], "high": cand["high"]})
    elif short_bias:
        z = ([z for z in fvg_list if z["dir"]=="bear"] + [z for z in ob_list if z["dir"]=="bear"]) or []
        cand = z[-1] if z else None
        if cand:
            entry = (cand["low"] + cand["high"]) / 2
            stop = cand["high"]; direction = "short"
            zones.append({"low": cand["low"], "high": cand["high"]})

    if entry is None or stop is None or direction is None:
        return None

    try:
        chain = await p.options_chain_snapshot(sym)
    except Exception:
        chain = {}

    ddoi = ddoi_from_chain(chain)
    bias: Dict[str, Any] = {
        "opex_week": is_opex_week(datetime.utcnow().date()),
        "ddoi": "pos" if (ddoi.get("net_delta",0) or 0) > 0 else ("neg" if (ddoi.get("net_delta",0) or 0) < 0 else "flat"),
        "earnings_soon": False,
    }

    # Earnings flag + GEX
    try:
        edate = await p.next_earnings_date(sym)
    except Exception:
        edate = None
    if edate:
        try:
            ed = datetime.fromisoformat(edate).date()
            days_to = (ed - datetime.utcnow().date()).days
        except Exception:
            ed, days_to = None, None
        if ed is not None:
            soon = (days_to is not None) and (0 <= days_to <= EARNINGS_FLAG_DAYS)
            bias["earnings_soon"] = soon
            bias["earnings_date"] = ed.isoformat()
            bias["earnings_days_to"] = days_to
    try:
        if bias.get("earnings_soon"):
            spot = float(df["close"].iloc[-1])
            g = compute_gex(chain, spot, window_pct=GEX_WINDOW_PCT, oi_min=GEX_OI_MIN, spread_max=GEX_SPREAD_MAX)
            pred = predict_earnings_move(g, days_to_earnings=bias.get("earnings_days_to"))
            bias.update({
                "gex_total": g.get("gex_total"),
                "gex_peak_strike": g.get("gex_peak_strike"),
                "gex_peak_side": g.get("gex_peak_side"),
                "gex_tilt": g.get("gex_tilt"),
                "er_dir": pred.get("er_dir"),
                "er_conf": pred.get("er_conf"),
            })
    except Exception:
        pass

    eq_liq = sorted(set(eqh + eql))
    targets = _targets_from_R(entry, stop, eq_liq)

    atr_like = float((df["high"] - df["low"]).tail(14).mean())
    conf = {"bos": bool(bos_list), "fvg": bool(fvg_list), "ob": bool(ob_list), "eq_liq": bool(eq_liq)}
    sc = score(conf, bias, atr_like, True)
    if sc < MIN_SCORE:
        return None

    proj = _projection_pct(df, PROJ_DAYS)
    if not (PROJ_MIN <= proj <= PROJ_MAX):
        return None

    option = _pick_option(chain, spot=float(df["close"].iloc[-1]), direction=direction)
    if option and targets:
        move = abs(targets[0] - entry)
        delta = option.get("delta") or 0.35
        prem = option.get("premium") or 1.0
        option["roi_pct"] = round(100.0 * (delta * move) / max(prem, 0.01), 1)

    return {
        "symbol": sym, "direction": direction,
        "entry": round(entry,2), "stop": round(stop,2), "targets": targets,
        "score": float(sc), "zones": [{"low": z["low"], "high": z["high"]} for z in zones],
        "bias": bias, "proj_move_pct": round(100.0*proj,1), "option": option,
    }

async def generate(kind: str) -> List[dict]:
    all_syms = load_universe()
    syms = all_syms[:MAX_SYMBOLS]
    p = Polygon(); sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async def worker(s: str):
        async with sem:
            try: return await analyze_symbol(p, s)
            except Exception: return None
    try:
        rows = [r for r in await asyncio.gather(*[worker(s) for s in syms]) if isinstance(r, dict) and r]
        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows
    finally:
        await p.close()

async def post_watchlist(kind: str):
    rows = await generate(kind)
    from app.macro import today_events_pt, header_for_events
    evs, blocking = await today_events_pt()
    macro_line = header_for_events(evs)
    try:
        p2 = Polygon()
        sectors_line = await sectors_header(p2)
        await p2.close()
    except Exception:
        sectors_line = "Sectors: n/a"

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    header = f"{kind.title()} Watchlist – {now_label}"

    def _fmt(r: dict) -> str:
        b = r.get("bias", {})
        eflag = ""
        if b.get("earnings_soon"):
            er = f" • ER:{b.get('er_dir','?')} {int(round(100*(b.get('er_conf',0.0) or 0.0)))}%" if b.get("er_dir") else ""
            eflag = f" • E:{b.get('earnings_date','?')} ({b.get('earnings_days_to','?')}d){er}"
        proj = f" • Proj:{r.get('proj_move_pct','?')}%"
        return f"{r['symbol']} {r['direction'].upper()} – Entry {r['entry']} | Stop {r['stop']} | T1 {r['targets'][0]} | Score {int(r['score'])}{proj}{eflag}"

    body = [_fmt(r) for r in rows[:20]] or [f"No Setups (min score {int(MIN_SCORE)}, proj {int(PROJ_MIN*100)}–{int(PROJ_MAX*100)}% over {PROJ_DAYS}d)"]
    await send_watchlist(header, [macro_line, sectors_line, *body])

    # 👉 NEW: journal the top rows as a snapshot
    if rows:
        snapshot_rows = journal.build_watchlist(kind, rows[:20])
        journal.append_rows(snapshot_rows)

    # Respect macro block window for 🚨 entries
    if blocking:
        return

    # Post top 5 entries + journal each
    for r in rows[:5]:
        await send_entry_detail(
            symbol=r["symbol"], direction=r["direction"],
            entry=float(r["entry"]), stop=float(r["stop"]),
            targets=[float(x) for x in r["targets"]],
            score=float(r["score"]), bias=r.get("bias", {}),
            option=r.get("option"), proj_move_pct=r.get("proj_move_pct"),
        )
        journal.append_row(journal.build_entry("entry", {
            "symbol": r["symbol"], "direction": r["direction"],
            "entry": float(r["entry"]), "stop": float(r["stop"]),
            "targets": [float(x) for x in r["targets"]],
            "score": float(r["score"]), "proj_move_pct": r.get("proj_move_pct"),
            "option": r.get("option"), "bias": r.get("bias", {}),
        }))
