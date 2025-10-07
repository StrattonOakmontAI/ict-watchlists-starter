# app/cli.py
from __future__ import annotations
import os
import argparse
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.watchlist import post_watchlist
from app.macro_post import post_macro_update
from app.live import live_loop

PT = ZoneInfo("America/Los_Angeles")

def _now_pt_label() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

async def premarket():
    print(f"[{_now_pt_label()}] Running premarket...")
    if os.getenv("MACRO_POST_BEFORE", "0") == "1":
        await post_macro_update()
    await post_watchlist("premarket")
    print(f"[{_now_pt_label()}] Premarket done.")

async def evening():
    print(f"[{_now_pt_label()}] Running evening...")
    if os.getenv("MACRO_POST_BEFORE", "0") == "1":
        await post_macro_update()
    await post_watchlist("evening")
    print(f"[{_now_pt_label()}] Evening done.")

async def weekly():
    print(f"[{_now_pt_label()}] Running weekly...")
    if os.getenv("MACRO_POST_BEFORE", "0") == "1":
        await post_macro_update()
    await post_watchlist("weekly")
    print(f"[{_now_pt_label()}] Weekly done.")

async def macro():
    print(f"[{_now_pt_label()}] Posting standalone macro update...")
    await post_macro_update()
    print(f"[{_now_pt_label()}] Macro update done.")

async def live():
    print(f"[{_now_pt_label()}] Starting live intraday monitor…")
    await live_loop()
    print(f"[{_now_pt_label()}] Live monitor stopped.")

async def scheduler():
    """
    Simple PT scheduler:
      - Weekdays: 06:00 premarket, 17:30 evening
      - Sundays:  06:00 weekly
    """
    print("Starting PT scheduler (weekdays + Sunday weekly)…")
    last_run = {"premarket": None, "evening": None, "weekly": None}
    while True:
        now = datetime.now(PT)
        wd = now.weekday()  # Mon=0..Sun=6

        if wd < 5 and now.hour == 6 and last_run["premarket"] != now.date():
            await premarket()
            last_run["premarket"] = now.date()

        if wd < 5 and now.hour == 17 and now.minute == 30 and last_run["evening"] != now.date():
            await evening()
            last_run["evening"] = now.date()

        if wd == 6 and now.hour == 6 and last_run["weekly"] != now.date():
            await weekly()
            last_run["weekly"] = now.date()

        await asyncio.sleep(30)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["premarket", "evening", "weekly", "macro", "live", "scheduler"])
    args = parser.parse_args()
    asyncio.run(globals()[args.cmd]())

if __name__ == "__main__":
    main()
