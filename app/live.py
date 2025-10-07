# app/live.py
from __future__ import annotations
import os, asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple

from app.watchlist import generate  # reuse your ranked analyzer
from app.polygon_client import Polygon
from app.notify import send_entry_detail
from app.macro import today_events_pt
from app import journal

PT = ZoneInfo("America/Los_Angeles")

# ---- Tunables via env ----
LIVE_MAX_SYMBOLS   = int(os.getenv("LIVE_MAX_SYMBOLS", "20"))   # monitor top-N rows
LIVE_POLL_SEC      = int(os.getenv("LIVE_POLL_SEC", "15"))      # polling cadence
LIVE_TOL_PCT       = float(os.getenv("LIVE_TOL_PCT", "0.0005")) # 5 bps = 0.05%
LIVE_START_PT      = os.getenv("LIVE_START_PT", "06:30")        # 06:30 PT
LIVE_END_PT        = os.getenv("LIVE_END_PT", "13:00")          # 13:00 PT

def _pt(hhmm: str) -> time:
    hh, mm = [int(x) for x in hhmm.split(":")]
    return time(hh, mm, tzinfo=PT)

def _now_pt() -> datetime:
    return datetime.now(PT)

async def _last_price(p: Polygon, sym: str) -> float | None:
    """
    Lightweight last price using recent 1m bars. Uses the latest close available.
    Pull a 15m window to be robust to minute boundaries.
    """
    to_dt = datetime.utcnow()
    frm_dt = to_dt - timedelta(minutes=15)
    try:
        df = await p.aggs(sym, 1, "minute", frm_dt.isoformat(), to_dt.isoformat())
        if df is None or df.empty:
            return None
        return float(df["close"].iloc[-1])
    except Exception:
        return None

def _triggered(price: float | None, entry: float, direction: str, tol: float) -> bool:
    if price is None:
        return False
    if direction == "long":
        return price >= entry * (1.0 - tol)  # small tolerance
    else:
        return price <= entry * (1.0 + tol)

async def live_once() -> List[dict]:
    """
    Produce the live watch set (top rows) once. Returns the rows list.
    """
    rows = await generate("premarket")
    return rows[:LIVE_MAX_SYMBOLS]

async def live_loop():
    """
    Weekdays intraday loop:
      - Skips outside [LIVE_START_PT, LIVE_END_PT) PT
      - Honors macro blocking window (no entries posted while blocking)
      - Posts each symbol at most once (first hit)
    """
    rows = await live_once()
    if not rows:
        return

    watch: Dict[str, dict] = {r["symbol"]: r for r in rows}
    posted: set[str] = set()

    start_t = _pt(LIVE_START_PT)
    end_t   = _pt(LIVE_END_PT)

    print(f"[{_now_pt().strftime('%H:%M:%S')}] Live monitor started for {len(watch)} symbols…")
    p = Polygon()
    try:
        while True:
            now = _now_pt()
            wd = now.weekday()  # Mon=0..Sun=6
            in_hours = (wd < 5) and (time(now.hour, now.minute, tzinfo=PT) >= start_t) and (time(now.hour, now.minute, tzinfo=PT) < end_t)
            if not in_hours:
                await asyncio.sleep(30)
                continue

            # Respect macro block (from BLS ICS)
            _evs, blocking = await today_events_pt(now=now)
            if blocking:
                await asyncio.sleep(LIVE_POLL_SEC)
                continue

            # Poll prices and trigger
            tasks: List[Tuple[str, asyncio.Task]] = []
            for sym, r in watch.items():
                if sym in posted:
                    continue
                tasks.append((sym, asyncio.create_task(_last_price(p, sym))))
            for sym, t in tasks:
                price = await t
                r = watch[sym]
                if _triggered(price, float(r["entry"]), r["direction"], LIVE_TOL_PCT):
                    # Send entry alert
                    await send_entry_detail(
                        symbol=sym,
                        direction=r["direction"],
                        entry=float(r["entry"]),
                        stop=float(r["stop"]),
                        targets=[float(x) for x in r["targets"]],
                        score=float(r["score"]),
                        bias=r.get("bias", {}),
                        option=r.get("option"),
                        proj_move_pct=r.get("proj_move_pct"),
                    )
                    # Journal it
                    journal.append_entry(journal.build_row("entry-live", {
                        "symbol": sym,
                        "direction": r["direction"],
                        "entry": float(r["entry"]),
                        "stop": float(r["stop"]),
                        "targets": [float(x) for x in r["targets"]],
                        "score": float(r["score"]),
                        "proj_move_pct": r.get("proj_move_pct"),
                        "option": r.get("option"),
                        "bias": r.get("bias", {}),
                    }))
                    posted.add(sym)

            # Exit early if all have fired
            if len(posted) == len(watch):
                print(f"[{_now_pt().strftime('%H:%M:%S')}] Live monitor finished (all symbols triggered).")
                return

            await asyncio.sleep(LIVE_POLL_SEC)
    finally:
        await p.close()
