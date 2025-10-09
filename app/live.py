from __future__ import annotations

import os
import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Tuple, Optional

from app.watchlist import generate
from app.polygon_client import Polygon
from app.notify import send_entry_detail

# Optional deps with safe fallbacks
try:
    from app.macro import today_events_pt
except Exception:
    async def today_events_pt(now: Optional[datetime] = None):
        return [], False

try:
    from app import journal
    _JOURNAL_OK = hasattr(journal, "append_entry") and hasattr(journal, "build_row")
except Exception:
    _JOURNAL_OK = False
    class _J:
        @staticmethod
        def append_entry(_row): pass
        @staticmethod
        def build_row(kind: str, data: dict): return {"kind": kind, **data}
    journal = _J()  # type: ignore

PT = ZoneInfo("America/Los_Angeles")

def _as_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except Exception: return default

def _as_float(name: str, default: float) -> float:
    try: return float(os.getenv(name, str(default)))
    except Exception: return default

LIVE_MAX_SYMBOLS = _as_int("LIVE_MAX_SYMBOLS", 20)
LIVE_POLL_SEC    = _as_int("LIVE_POLL_SEC", 15)

# Tolerance: treat >=1 as percent (e.g., 0.20% -> 0.20 -> 0.002)
_raw_tol = _as_float("LIVE_TOL_PCT", 0.0005)      # default 0.05% as fraction
LIVE_TOL_FRAC = _raw_tol / 100.0 if _raw_tol >= 1.0 else _raw_tol

LIVE_START_PT = os.getenv("LIVE_START_PT", "06:30")
LIVE_END_PT   = os.getenv("LIVE_END_PT",   "13:00")

_REGEN_SEC_IF_EMPTY = 120         # how often to retry generate() when empty
_REGEN_SEC_AFTER_ALL = 300        # cooldown after all symbols triggered

def _pt(hhmm: str) -> time:
    hh, mm = [int(x) for x in hhmm.split(":")]
    return time(hh, mm, tzinfo=PT)

def _now_pt() -> datetime:
    return datetime.now(PT)

async def _last_price(p: Polygon, sym: str) -> Optional[float]:
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

async def _build_watch() -> Dict[str, dict]:
    rows = await generate("premarket") or []
    rows = rows[:LIVE_MAX_SYMBOLS]
    return {r["symbol"]: r for r in rows if "symbol" in r}

async def live_loop():
    # validate hours
    try:
        start_t = _pt(LIVE_START_PT)
        end_t   = _pt(LIVE_END_PT)
    except Exception:
        print(f"[{_now_pt().strftime('%H:%M:%S')}] ERROR live: bad LIVE_START_PT/LIVE_END_PT ({LIVE_START_PT=}, {LIVE_END_PT=}); using defaults.")
        start_t = _pt("06:30"); end_t = _pt("13:00")

    print(f"[{_now_pt().strftime('%H:%M:%S')}] INFO live: loop starting; tol={LIVE_TOL_FRAC:.5f} (raw {_raw_tol}), poll={LIVE_POLL_SEC}s")

    p = Polygon()
    watch: Dict[str, dict] = {}
    posted: set[str] = set()
    last_regen_day: Optional[int] = None

    try:
        while True:
            now = _now_pt()
            wd = now.weekday()           # Mon=0..Sun=6
            cur = time(now.hour, now.minute, tzinfo=PT)
            in_hours = (wd < 5) and (cur >= start_t) and (cur < end_t)

            # Outside market hours: idle but don't exit
            if not in_hours:
                posted.clear()
                watch.clear()
                last_regen_day = None
                await asyncio.sleep(60)
                continue

            # New day → reset & rebuild
            if last_regen_day is None or last_regen_day != now.day:
                posted.clear()
                watch = await _build_watch()
                last_regen_day = now.day
                if not watch:
                    print(f"[{now.strftime('%H:%M:%S')}] INFO live: no candidates yet; retry in {_REGEN_SEC_IF_EMPTY}s")
                    await asyncio.sleep(_REGEN_SEC_IF_EMPTY)
                    continue
                else:
                    print(f"[{now.strftime('%H:%M:%S')}] INFO live: tracking {len(watch)} symbols")

            # Macro block window?
            try:
                _evs, blocking = await today_events_pt(now=now)
            except Exception:
                blocking = False
            if blocking:
                await asyncio.sleep(LIVE_POLL_SEC)
                continue

            # poll prices
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
                    continue

                if _triggered(price, entry, direction, LIVE_TOL_FRAC):
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
                    # journal (best-effort)
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

            # All fired? Cooldown then refresh list (don’t exit)
            if watch and len(posted) == len(watch):
                print(f"[{now.strftime('%H:%M:%S')}] INFO live: all {len(watch)} symbols triggered; cooldown {_REGEN_SEC_AFTER_ALL}s")
                await asyncio.sleep(_REGEN_SEC_AFTER_ALL)
                posted.clear()
                watch = await _build_watch()
                continue

            await asyncio.sleep(LIVE_POLL_SEC)
    finally:
        try:
            await p.close()
        except Exception:
            pass
