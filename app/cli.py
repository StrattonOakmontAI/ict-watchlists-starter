import asyncio, argparse, json, os
from datetime import datetime, timedelta, timezone
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.notify import send_watchlist, send_entry

PT = pytz.timezone("America/Los_Angeles")
UTC = pytz.utc

# --- simple duplicate guard (persists across restarts in container) ---
DEDUP_FILE = "/tmp/ict_last_runs.json"
def _now_utc():
    return datetime.now(timezone.utc)

def _load_last():
    try:
        with open(DEDUP_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_last(data: dict):
    try:
        os.makedirs(os.path.dirname(DEDUP_FILE), exist_ok=True)
        with open(DEDUP_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def should_run(job: str, min_minutes: int = 10) -> bool:
    data = _load_last()
    last = data.get(job)
    if last:
        last_dt = datetime.fromisoformat(last)
        if _now_utc() - last_dt < timedelta(minutes=min_minutes):
            # too soon; probable duplicate trigger
            return False
    data[job] = _now_utc().isoformat()
    _save_last(data)
    return True
# ----------------------------------------------------------------------

def now_pt_str():
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

# ----- job bodies -----
async def weekly():
    if not should_run("weekly", 5):  # 5-minute dedupe window
        return
    await send_watchlist(
        f"Weekly Watchlist (Sun 08:00 PT) – {now_pt_str()}",
        ["AAPL 15m Long – demo", "MSFT 5m Short – demo"]
    )

async def premarket():
    if not should_run("premarket", 5):
        return
    await send_watchlist(
        f"Pre-Market Watchlist (06:00 PT) – {now_pt_str()}",
        ["SPY – demo", "TSLA – demo"]
    )

async def evening():
    if not should_run("evening", 5):
        return
    await send_watchlist(
        f"Evening Watchlist (17:30 PT) – {now_pt_str()}",
        ["NVDA – demo", "AMZN – demo"]
    )

# quick manual tests
async def test_watchlist():
    await premarket()

async def test_entry():
    await send_entry("AAPL")

# ----- keep-alive loop -----
async def idle():
    """
    IMPORTANT: We also start the scheduler from here so even if
    the DO run command is 'idle', schedules still run.
    """
    await scheduler(startup_log="Idle worker: starting internal scheduler...")
    # If scheduler returns, keep the container alive
    while True:
        await asyncio.sleep(3600)

# ----- internal scheduler -----
async def scheduler(startup_log="Starting internal scheduler..."):
    print(startup_log)
    sched = AsyncIOScheduler(timezone=UTC)
    # PDT mapping (Oct): PT 06:00 -> 13:00 UTC, PT 17:30 -> 00:30 UTC, Sun 08:00 -> 15:00 UTC
    sched.add_job(premarket, CronTrigger(hour=13, minute=0))                     # daily 13:00 UTC
    sched.add_job(evening,   CronTrigger(hour=0,  minute=30))                    # daily 00:30 UTC
    sched.add_job(weekly,    CronTrigger(day_of_week='sun', hour=15, minute=0))  # Sunday 15:00 UTC
    sched.start()
    print("Scheduler started. Waiting for triggers...")
    # Don't exit; keep loop running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "cmd",
        nargs="?",
        default="idle",  # default to 'idle' (which starts scheduler)
        choices=["idle","scheduler","weekly","premarket","evening","test-watchlist","test-entry"]
    )
    args = p.parse_args()
    asyncio.run(globals()[args.cmd.replace('-', '_')]())
