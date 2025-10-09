# app/cli.py
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Ensure .env is loaded locally; on DO, real env vars take precedence.
# file: app/cli.py  (top of file — replace the plain 'import app.env' with guarded import)
from __future__ import annotations
import argparse, asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Load .env if the helper exists; never crash if it's missing.
try:
    import app.env  # noqa: F401
except Exception:
    pass

from app.notify import send_watchlist, send_entry_detail
from app.config import SETTINGS
# ... rest of your cli.py unchanged ...

from app.notify import send_watchlist, send_entry_detail
from app.config import SETTINGS

# Optional imports; keep CLI usable if feature modules aren't ready.
try:
    from app.watchlist import post_watchlist  # type: ignore
except Exception:  # noqa: BLE001
    async def post_watchlist(_when: str) -> None:  # type: ignore
        return

try:
    from app.macro_post import post_macro_update  # type: ignore
except Exception:  # noqa: BLE001
    async def post_macro_update() -> None:  # type: ignore
        return

try:
    from app.live import live_loop  # type: ignore
except Exception:  # noqa: BLE001
    async def live_loop() -> None:  # type: ignore
        while True:
            await asyncio.sleep(10)

PT = ZoneInfo(getattr(SETTINGS, "tz", "America/Los_Angeles"))


def _now_pt_label() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")


# --- Commands ---------------------------------------------------------------

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
    print(f"[{_now_pt_label()}] idle…")  # Why: safe default CMD in Docker/DO.
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
    Simple tick-based scheduler. For production, cron/K8s is preferred.
    """
    last = {"premarket": None, "evening": None, "weekly": None}
    while True:
        now = datetime.now(PT)
        wd = now.weekday()  # Mon=0..Sun=6
        try:
            if wd < 5 and now.hour == 6 and last["premarket"] != now.date():
                await premarket()
                last["premarket"] = now.date()
            if wd < 5 and now.hour == 13 and last["evening"] != now.date():
                await evening()
                last["evening"] = now.date()
            if wd == 6 and now.hour == 6 and last["weekly"] != now.date():
                await weekly()
                last["weekly"] = now.date()
        except Exception as e:  # Why: never crash the worker; log and continue.
            print(f"[{_now_pt_label()}] scheduler error: {e}")
        await asyncio.sleep(30)


# --- Entry ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ict-watchlists")
    p.add_argument(
        "cmd",
        choices=[
            "premarket",
            "evening",
            "weekly",
            "macro",
            "live",
            "scheduler",
            "idle",
            "test-watchlist",
            "test-entry",
        ],
        help="Command to run",
    )
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cmd = args.cmd.replace("-", "_")
    asyncio.run(globals()[cmd]())


if __name__ == "__main__":
    main()
