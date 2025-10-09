# app/live.py
from __future__ import annotations

import os
import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional

from app.watchlist import generate  # reuse your ranked analyzer
from app.polygon_client import Polygon
from app.notify import send_entry_detail

# ---- Optional deps with safe fallbacks --------------------------------------
try:
    from app.macro import today_events_pt  # expected to return (events, blocking: bool)
except Exception:
    async def today_events_pt(now: Optional[datetime] = None):
        # Fallback: never block if macro module not available
        return [], False

try:
    from app import journal
    _JOURNAL_OK = hasattr(journal, "append_entry") and hasattr(journal, "build_row")
except Exception:
    _JOURNAL_OK = False
    class _J:
        @staticmethod
        def append_entry(_row):  # no-op
            pass
        @staticmethod
        def build_row(kind: str, data: dict):
            return {"kind": kind, **data}
    journal = _J()  # type: ignore


PT = ZoneInfo("America/Los_Angeles")

# ---- Tunables via env -------------------------------------------------------
def _as_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _as_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

LIVE_MAX_SYMBOLS = _as_int("LIVE_MAX_SYMBOLS", 20)     # monitor top-N rows
LIVE_POLL_SEC    = _as_int("LIVE_POLL_SEC", 15)        # polling cadence (sec)

# NOTE: Users often set 0.20 meaning 0.20% (not 20%). Normalize automatically:
_raw_tol = _as_float("LIVE_TOL_PCT", 0.0005)           # default 0.05% as fraction
LIVE_TOL_FRAC = _raw_tol / 100.0 if _raw_tol >= 1.0 else _raw_tol  # 0.20 -> 0.002

LIVE_START_PT = os.getenv("LIVE_START_PT", "06:30")
LIVE_END_PT   = os.getenv("LIVE_END_PT",   "13:00")


# ---- Helpers ----------------------------------------------------------------
def _pt(hhmm: str) -> time:
    hh_str, mm_str = hhmm.split(":")
    hh, mm = int(hh_str), int(mm_str)
    return time(hh, mm, tzinfo=PT)

def _now_pt() -> datetime:
    return datetime.now(PT)

async def _last_price(p: Polygon, sym: str) -> Optional[float]:
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

def _triggered(price: Optional[float], entry: float, direction: str, tol_frac: float) -> bool:
    if price is None:
        return False
    if direction == "long":
        return price >= entry * (1.0 - tol_frac)
    else:
        return price <= entry * (1.0 + tol_frac)

async def live_once() -> List[dict]:
    """
    Produce the live watch set (top rows) once. Returns the rows list.
    """
    rows = await generate("premarket")
    return rows[:LIVE_MAX_SYMBOLS] if rows else []

# ---- Main loop --------------------------------------------------------------
async def live_loop():
    """
    Weekdays intraday loop:
      - Skips outside [LIVE_START_PT, LIVE_END_PT) PT
      - Honors macro blocking window (no entries posted while blocking)
      - Posts each symbol at most once (first hit)
    """
    try:
        start_t = _pt(LIVE_START_PT)
        end_t   = _pt(LIVE_END_PT)
    except Exception:
        print(f"[{_now_pt().strftime('%H:%M:%S')}] ERROR live: bad LIVE_START_PT/LIVE_END_PT ({LIVE_START_PT=}, {LIVE_END_PT=}); using defaults.")
        start_t = _pt("06:30")
        end_t   = _pt("13:00")

    rows = await live_once()
    if not rows:
        print(f"[{_now_pt().strftime('%H:%M:%S')}] INFO live: no rows from generate('premarket'); sleeping.")
        await asyncio.sleep(max(LIVE_POLL_SEC, 15))
        return

    watch: Dict[str, dict] = {r["symbol"]: r for r in rows if "symbol" in r}
    posted: set[str] = set()

    print(f"[{_now_pt().strftime('%H:%M:%S')}] INFO live: monitor started for {len(watch)} symbols; tol={LIVE_TOL_FRAC:.5f} ({_raw_tol} raw), poll={LIVE_POLL_SEC}s")
    p = Polygon()
    try:
        while True:
            now = _now_pt()
            wd = now.weekday()  # Mon=0..Sun=6
            cur = time(now.hour, now.minute, tzinfo=PT)
            in_hours = (wd < 5) and (cur >= start_t) and (cur < end_t)
            if not in_hours:
                await asyncio.sleep(30)
                continue

            # Respect macro block (from BLS ICS)
            try:
                _evs, blocking = await today_events_pt(now=now)
            except Exception:
                blocking = False
            if blocking:
                await asyncio.sleep(LIVE_POLL_SEC)
                continue

            # Poll prices and trigger
            tasks: List[Tuple[str, asyncio.Task[Optional[float]]]] = []
            for sym, r in watch.items():
                if sym in posted:
                    continue
                tasks.append((sym, asyncio.create_task(_last_price(p, sym))))

            for sym, t in tasks:
                price = await t
                r = watch[sym]
                try:
                    entry = float(r["entry"])
                    direction = str(r["direction"]).lower()
                    stop = float(r["stop"])
                    targets = [float(x) for x in r.get("targets", [])]
                    score = float(r.get("score", 0))
                except Exception:
                    continue  # skip malformed row

                if _triggered(price, entry, direction, LIVE_TOL_FRAC):
                    # Send entry alert
                    await send_entry_detail(
                        symbol=sym,
                        direction=direction,
                        entry=entry,
                        stop=stop,
                        targets=targets,
                        score=score,
                        bias=r.get("bias", {}),
                        option=r.get("option"),
                        proj_move_pct=r.get("proj_move_pct"),
                    )
                    # Journal it (best-effort)
                    try:
                        row = journal.build_row("entry-live", {
                            "symbol": sym,
                            "direction": direction,
                            "entry": entry,
                            "stop": stop,
                            "targets": targets,
                            "score": score,
                            "proj_move_pct": r.get("proj_move_pct"),
                            "option": r.get("option"),
                            "bias": r.get("bias", {}),
                        })
                        journal.append_entry(row)
                    except Exception:
                        pass
                    posted.add(sym)

            # Exit early if all have fired
            if len(posted) == len(watch) and len(watch) > 0:
                print(f"[{_now_pt().strftime('%H:%M:%S')}] INFO live: finished (all symbols triggered).")
                return

            await asyncio.sleep(LIVE_POLL_SEC)
    finally:
        try:
            await p.close()
        except Exception:
            pass
