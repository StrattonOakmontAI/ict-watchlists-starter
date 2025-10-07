# app/cli.py
from __future__ import annotations
import os
import argparse
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.watchlist import post_watchlist
from app.macro_post import post_macro_update

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", help="premarket | evening | weekly | macro")
    args = parser.parse_args()
    cmd = args.cmd.replace("-", "_")
    if cmd not in {"premarket", "evening", "weekly", "macro"}:
        raise SystemExit("unknown command")
    asyncio.run(globals()[cmd]())

if __name__ == "__main__":
    main()
