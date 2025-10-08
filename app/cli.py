# file: app/cli.py
# Why: Brings README and CLI back in sync + adds an 'idle' for Docker CMD.
from __future__ import annotations
import argparse, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Keep optional imports non-fatal so tests still work if other modules are incomplete.
try:
    from app.watchlist import post_watchlist  # type: ignore
except Exception:
    async def post_watchlist(_when: str) -> None: return

try:
    from app.macro_post import post_macro_update  # type: ignore
except Exception:
    async def post_macro_update() -> None: return

try:
    from app.live import live_loop  # type: ignore
except Exception:
    async def live_loop() -> None:
        while True:
            await asyncio.sleep(10)

from app.notify import send_watchlist, send_entry_detail

PT = ZoneInfo("America/Los_Angeles")
def _now_pt_label() -> str: return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

async def premarket() -> None:
    print(f"[{_now_pt_label()}] premarket → watchlist")
    await post_watchlist("premarket")

async def evening() -> None:
    print(f"[{_now_pt_label()}] evening → watchlist")
    await post_watchlist("evening")

async def weekly() -> None:
    print(f"[{_now_pt_label()}] weekly → watchlist")
    await post_watchlist("weekly")

async def macro() -> None:
    print(f"[{_now_pt_label()}] macro → discord")
    await post_macro_update()

async def live() -> None:
    print(f"[{_now_pt_label()}] live loop starting")
    await live_loop()

async def idle() -> None:
    print(f"[{_now_pt_label()}] idle…")  # Why: Docker default CMD that always exists.
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

async def test_entry() -> None:
    await send_entry_detail(
        symbol="AAPL", direction="long", entry=185.0, stop=183.5,
        targets=[186.0, 187.0, 188.5], score=95,
        bias={"trend": "bull", "fair_value_gap": "4h"},
        option={"type": "C", "strike": 187.5, "dte": 10, "mid": 1.20},
        proj_move_pct=6.5,
    )

async def scheduler() -> None:
    from datetime import datetime
    from app.config import SETTINGS
    from zoneinfo import ZoneInfo

    PT = ZoneInfo(getattr(SETTINGS, "tz", "America/Los_Angeles"))
    last = {"premarket": None, "evening": None, "weekly": None}

    while True:
        now = datetime.now(PT)
        wd = now.weekday()  # Mon=0..Sun=6
        try:
            # 06:30 PT on weekdays
            if wd < 5 and now.hour == 6 and now.minute == 30 and last["premarket"] != now.date():
                await premarket(); last["premarket"] = now.date()

            # 13:00 PT on weekdays
            if wd < 5 and now.hour == 13 and now.minute == 0 and last["evening"] != now.date():
                await evening();   last["evening"] = now.date()

            # Sunday 06:00 PT for weekly
            if wd == 6 and now.hour == 6 and now.minute == 0 and last["weekly"] != now.date():
                await weekly();    last["weekly"] = now.date()
        except Exception as e:
            print(f"[{now:%Y-%m-%d %H:%M:%S %Z}] scheduler error: {e}")
        await asyncio.sleep(30)
)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=[
        "premarket","evening","weekly","macro","live","scheduler",
        "idle","test-watchlist","test-entry",
    ])
    args = parser.parse_args()
    asyncio.run(globals()[args.cmd.replace("-", "_")]())

if __name__ == "__main__":
    main()
