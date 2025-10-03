import os, json
import httpx
from rich import print

WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST")
EN = os.getenv("DISCORD_WEBHOOK_ENTRIES") or WL

async def _post(webhook: str, payload: dict):
    async with httpx.AsyncClient(timeout=20) as x:
        r = await x.post(webhook, json=payload)
        r.raise_for_status()
        print("[green]Sent[/]")

async def send_watchlist(title: str, items: list[str]):
    embed = {
        "title": title,
        "description": "Starter watchlist message (replace with real data during MVP)",
        "fields": [{"name": f"{i+1}.", "value": v} for i, v in enumerate(items)],
        "footer": {"text": "Not financial advice"}
    }
    await _post(WL, {"username": "ICT Watchlists 👀", "embeds": [embed]})

async def send_entry(symbol: str):
    embed = {
        "title": f"ENTRY – {symbol} (demo)",
        "fields": [
            {"name": "Entry/Stop", "value": "123.45 / 122.90 (1R=0.55)"},
            {"name": "Targets", "value": "T1 124.00 | T2 124.55 | T3 125.10 | T4 125.65"},
            {"name": "Confluence", "value": "BOS + FVG + OB (demo)"}
        ],
        "footer": {"text": "Scale: 50/25/15/10 at T1–T4"}
    }
    await _post(EN, {"username": "ICT Entries 🚨", "embeds": [embed]})
