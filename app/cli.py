from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Load .env for dev; ignore if missing
try:
    import app.env  # noqa: F401
except Exception:
    pass

from app.notify import send_watchlist, send_entry_detail
from app.config import SETTINGS

# Optional imports; keep CLI usable even if feature modules aren't ready.
try:
    from app.watchlist import post_watchlist  # type: ignore
except Exception:
    async def post_watchlist(_when: str) -> None:  # type: ignore
        return

try:
    from app.macro_post import post_macro_update  # type: ignore
except Exception:
    async def post_macro_update() -> None:  # type: ignore
        return

try:
    from app.live import live_loop  # type: ignore
except Exception:
    async def live_loop() -> None:  # type: ignore
        while True:
            await asyncio.sleep(10)

PT = ZoneInfo(getattr(SETTINGS, "tz", "America/Los_Angeles"))

def _now_pt_label() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

def _parse_hhmm(s: str, *, default: str) -> tuple[int, int]:
    s = (s or "").strip() or default
    hh, mm = s.split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("bad HH:MM time")
    return h, m

# ---- Commands ----

async def premarket() -> None:
    print(f"[{_now_pt_label()}] premarket → watchlist")
    await post_watchlist("premarket")
    print(f"[{_now_pt_label()}] premarket ✓ sent")

async def evening() -> None:
    print(f"[{_now_pt_label()}] evening → watchlist")
    await post_watchlist("evening")
    print(f"[{_now_pt_label()}] evening ✓ sent")

async def weekly() -> None:
    print(f"[{_now_pt_label()}] weekly → watchlist")
    await post_watchlist("weekly")
    print(f"[{_now_pt_label()}] weekly ✓ sent")

async def macro() -> None:
    print(f"[{_now_pt_label()}] macro → discord")
    await post_macro_update()
    print(f"[{_now_pt_label()}] macro ✓ sent")

async def live() -> None:
    print(f"[{_now_pt_label()}] live loop starting")
    await live_loop()

async def idle() -> None:
    print(f"[{_now_pt_label()}] idle…")
    while True:
        await asyncio.sleep(3600)

async def test_watchlist() -> None:
    title = f"Watchlist Test – {_now_pt_label()}"
    lines = [
        "Macro: CPI 5:30a PT; FOMC 11:00a PT",
        "Sectors: Tech ↑, Energy ↘, Health =",
        "AAPL LONG – Entry 185.0 | T1 186.0 | Score 92",
        "MSFT SHORT – Entry 420.5 | T1 418.0 | Score 88",
    ]
    await send_watchlist(title, lines)
    print(f"[{_now_pt_label()}] test-watchlist ✓ sent")

async def test_entry() -> None:
    await send_entry_detail(
        symbol="AAPL",
        direction="long",
        entry=185.0,
        stop=183.5,
        targets=[186.0, 187.0, 188.5],
        score=95,
        bias={"trend": "bull", "fair_value_gap": "4h"},
        option={"type": "C", "strike": 187.5, "dte": 10, "mid": 1.20},
        proj_move_pct=6.5,
    )
    print(f"[{_now_pt_label()}] test-entry ✓ sent")

async def scheduler() -> None:
    """
    Fires:
      - Weekdays: 06:30 PT (premarket), 13:00 PT (evening)
      - Sundays: 06:00 PT (weekly)
    Override with env (optional): SCHED_PREMARKET="HH:MM", SCHED_EVENING="HH:MM", SCHED_WEEKLY="HH:MM"
    """
    pre_h, pre_m = _parse_hhmm(os.getenv("SCHED_PREMARKET", ""), default="06:30")
    eve_h, eve_m = _parse_hhmm(os.getenv("SCHED_EVENING", ""), default="13:00")
    wk_h,  wk_m  = _parse_hhmm(os.getenv("SCHED_WEEKLY",  ""), default="06:00")

    last = {"premarket": None, "evening": None, "weekly": None}

    print(f"[{_now_pt_label()}] scheduler start "
          f"(premarket {pre_h:02d}:{pre_m:02d}, evening {eve_h:02d}:{eve_m:02d}, weekly {wk_h:02d}:{wk_m:02d})")

    while True:
        now = datetime.now(PT)
        wd = now.weekday()  # Mon=0..Sun=6
        try:
            if wd < 5 and now.hour == pre_h and now.minute == pre_m and last["premarket"] != now.date():
                await premarket(); last["premarket"] = now.date()
            if wd < 5 and now.hour == eve_h and now.minute == eve_m and last["evening"] != now.date():
                await evening();   last["evening"] = now.date()
            if wd == 6 and now.hour == wk_h and now.minute == wk_m and last["weekly"] != now.date():
                await weekly();    last["weekly"] = now.date()
        except Exception as e:
            print(f"[{_now_pt_label()}] scheduler error: {e}")
        await asyncio.sleep(20)  # minute-resolution with fast loop

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ict-watchlists")
    p.add_argument(
        "cmd",
        choices=[
            "premarket","evening","weekly","macro","live","scheduler",
            "idle","test-watchlist","test-entry",
        ],
        help="Command to run",
    )
    return p

def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(globals()[args.cmd.replace("-", "_")]())

if __name__ == "__main__":
    main()
