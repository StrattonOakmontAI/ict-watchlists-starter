# app/cli.py
# Simple CLI + PT scheduler for ICT watchlists (text-only entries inside watchlist.post_watchlist)

import os
import asyncio
import argparse
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.watchlist import post_watchlist
from app.config import settings

PT = pytz.timezone("America/Los_Angeles")


def now_pt_str() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")


async def premarket():
    print(f"[{now_pt_str()}] Running premarket...")
    await post_watchlist("premarket")
    print(f"[{now_pt_str()}] Premarket done.")


async def evening():
    print(f"[{now_pt_str()}] Running evening...")
    await post_watchlist("evening")
    print(f"[{now_pt_str()}] Evening done.")


async def weekly():
    print(f"[{now_pt_str()}] Running weekly...")
    await post_watchlist("weekly")
    print(f"[{now_pt_str()}] Weekly done.")


async def scheduler(startup_log="Starting PT scheduler (weekdays only)..."):
    """
    Runs:
      - Mon–Fri: 06:00 PT premarket, 17:30 PT evening
      - Sun:     08:00 PT weekly
    """
    print(startup_log)
    sched = AsyncIOScheduler(timezone=PT)
    sched.add_job(premarket, CronTrigger(day_of_week="mon-fri", hour=6, minute=0))
    sched.add_job(evening,   CronTrigger(day_of_week="mon-fri", hour=17, minute=30))
    sched.add_job(weekly,    CronTrigger(day_of_week="sun",     hour=8, minute=0))
    sched.start()
    print("Scheduler started (PT). Waiting for triggers...")
    while True:
        await asyncio.sleep(3600)


def main():
    parser = argparse.ArgumentParser(description="ICT Watchlists CLI")
    parser.add_argument("cmd", choices=["premarket", "evening", "weekly", "scheduler"], help="Command to run")
    args = parser.parse_args()

    cmd_map = {
        "premarket": premarket,
        "evening": evening,
        "weekly": weekly,
        "scheduler": scheduler,
    }

    asyncio.run(cmd_map[args.cmd]())


if __name__ == "__main__":
    main()
