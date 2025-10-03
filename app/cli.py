import asyncio, argparse
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.notify import send_watchlist, send_entry

PT = pytz.timezone("America/Los_Angeles")
UTC = pytz.utc

def now_pt():
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

async def weekly():
    await send_watchlist(f"Weekly Watchlist (Sun 08:00 PT) – {now_pt()}",
                         ["AAPL 15m Long – demo","MSFT 5m Short – demo"])

async def premarket():
    await send_watchlist(f"Pre-Market Watchlist (06:00 PT) – {now_pt()}",
                         ["SPY – demo","TSLA – demo"])

async def evening():
    await send_watchlist(f"Evening Watchlist (17:30 PT) – {now_pt()}",
                         ["NVDA – demo","AMZN – demo"])

async def test_watchlist():
    await premarket()

async def test_entry():
    await send_entry("AAPL")

async def idle():
    print("Idle worker running. Waiting for scheduled jobs or console commands...")
    while True:
        await asyncio.sleep(3600)

async def scheduler():
    print("Starting internal scheduler...")
    sched = AsyncIOScheduler(timezone=UTC)
    # PDT mapping (Oct): PT 06:00 -> 13:00 UTC, PT 17:30 -> 00:30 UTC next day, Sun 08:00 -> 15:00 UTC
    sched.add_job(premarket, CronTrigger(hour=13, minute=0))                 # daily 13:00 UTC
    sched.add_job(evening,   CronTrigger(hour=0,  minute=30))                # daily 00:30 UTC
    sched.add_job(weekly,    CronTrigger(day_of_week='sun', hour=15, minute=0))  # Sunday 15:00 UTC
    sched.start()
    await idle()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?", default="scheduler",
                   choices=["idle","scheduler","weekly","premarket","evening","test-watchlist","test-entry"])
    args = p.parse_args()
    asyncio.run(globals()[args.cmd.replace('-', '_')]())
