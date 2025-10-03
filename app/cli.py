import asyncio, argparse
from datetime import datetime
import pytz
from app.notify import send_watchlist, send_entry

PT = pytz.timezone("America/Los_Angeles")

def now_pt():
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

async def weekly():
    await send_watchlist(
        f"Weekly Watchlist (Sun 08:00 PT) – {now_pt()}",
        ["AAPL 15m Long – demo", "MSFT 5m Short – demo"]
    )

async def premarket():
    await send_watchlist(
        f"Pre-Market Watchlist (06:00 PT) – {now_pt()}",
        ["SPY – demo", "TSLA – demo"]
    )

async def evening():
    await send_watchlist(
        f"Evening Watchlist (17:30 PT) – {now_pt()}",
        ["NVDA – demo", "AMZN – demo"]
    )

async def test_watchlist():
    await premarket()

async def test_entry():
    await send_entry("AAPL")

async def run_once():
    print("Container up; use DigitalOcean Console → Run Command to invoke jobs.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "cmd",
        nargs="?",
        default="run-once",
        choices=["run-once", "weekly", "premarket", "evening", "test-watchlist", "test-entry"]
    )
    args = p.parse_args()
    asyncio.run(globals()[args.cmd.replace('-', '_')]())
