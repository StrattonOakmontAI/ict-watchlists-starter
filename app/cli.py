from __future__ import annotations  # must be first

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import logging

# Structured logging
from app.logging_setup import setup_logging
setup_logging()
log = logging.getLogger("cli")

# Load .env for local/dev (no-op on DO)
try:
    import app.env  # noqa: F401
except Exception:
    pass

# ✅ Your config exports `settings` (lowercase)
try:
    from app.config import settings as SETTINGS  # alias for uniform usage
except Exception:
    # fallback if both exist in future
    from app.config import SETTINGS  # type: ignore

# Core notifications
from app.notify import send_watchlist, send_entry_detail

# Optional modules (keep CLI usable if any piece is missing)
try:
    from app.watchlist import post_watchlist  # type: ignore
except Exception:
    async def post_watchlist(_when: str) -> None:  # type: ignore
        log.warning("post_watchlist not available; skipping")
        return

try:
    from app.macro_post import post_macro_update  # type: ignore
except Exception:
    async def post_macro_update() -> None:  # type: ignore
        log.warning("post_macro_update not available; skipping")
        return

try:
    from app.live import live_loop  # type: ignore
except Exception:
    async def live_loop() -> None:  # type: ignore
        log.warning("live_loop not available; sleeping")
        while True:
            await asyncio.sleep(30)

PT = ZoneInfo(getattr(SETTINGS, "tz", "America/Los_Angeles"))
LAST_RUNS_PATH = Path("/tmp/last_runs.json")  # container-local only


def _now_pt_label() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")


def _save_last_run(key: str) -> None:
    data = {}
    try:
        if LAST_RUNS_PATH.exists():
            data = json.loads(LAST_RUNS_PATH.read_text())
    except Exception as e:
        log.error("reading last-run file failed: %s", e)
    data[key] = _now_pt_label()
    try:
        LAST_RUNS_PATH.write_text(json.dumps(data))
    except Exception as e:
        log.error("writing last-run file failed: %s", e)


def _parse_hhmm(s: str, *, default: str) -> tuple[int, int]:
    s = (s or "").strip() or default
    hh, mm = s.split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("bad HH:MM time")
    return h, m


# -------------------- Commands --------------------

async def premarket() -> None:
    log.info("premarket → watchlist")
    await post_watchlist("premarket")
    _save_last_run("premarket")
    log.info("premarket ✓ sent")


async def evening() -> None:
    log.info("evening → watchlist")
    await post_watchlist("evening")
    _save_last_run("evening")
    log.info("evening ✓ sent")


async def weekly() -> None:
    log.info("weekly → watchlist")
    await post_watchlist("weekly")
    _save_last_run("weekly")
    log.info("weekly ✓ sent")


async def macro() -> None:
    log.info("macro → discord")
    await post_macro_update()
    _save_last_run("macro")
    log.info("macro ✓ sent")


async def live() -> None:
    log.info("live loop starting")
    await live_loop()


async def idle() -> None:
    log.info("idle…")
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
    _save_last_run("test-watchlist")
    log.info("test-watchlist ✓ sent")


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
    _save_last_run("test-entry")
    log.info("test-entry ✓ sent")


async def scheduler() -> None:
    """
    Fires:
      - Weekdays: 06:30 PT (premarket), 13:00 PT (evening)
      - Sundays: 06:00 PT (weekly)
    Override via env (optional): SCHED_PREMARKET, SCHED_EVENING, SCHED_WEEKLY (HH:MM).
    """
    pre_h, pre_m = _parse_hhmm(os.getenv("SCHED_PREMARKET", ""), default="06:30")
    eve_h, eve_m = _parse_hhmm(os.getenv("SCHED_EVENING", ""), default="13:00")
    wk_h,  wk_m  = _parse_hhmm(os.getenv("SCHED_WEEKLY",  ""), default="06:00")

    last = {"premarket": None, "evening": None, "weekly": None}
    log.info(
        "scheduler start (premarket %02d:%02d, evening %02d:%02d, weekly %02d:%02d, TZ=%s)",
        pre_h, pre_m, eve_h, eve_m, wk_h, wk_m, getattr(SETTINGS, "tz", "America/Los_Angeles"),
    )

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
            log.error("scheduler error: %s", e)
        await asyncio.sleep(20)  # minute-resolution loop


# -------------------- Entrypoint --------------------

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
