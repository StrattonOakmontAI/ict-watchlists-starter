# app/macro_post.py
from __future__ import annotations
import os
from datetime import datetime
from typing import List, Dict, Any

import httpx

from app.macro import today_events_pt, header_for_events
from app.polygon_client import Polygon
from app.sectors import sectors_header

# Webhooks
WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "").strip()
MAC = os.getenv("DISCORD_WEBHOOK_MACRO", "").strip()  # <- set this in DO; falls back to WL

async def _post(webhook: str, payload: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=15) as x:
        r = await x.post(webhook, json=payload)
        r.raise_for_status()

async def post_macro_update() -> None:
    """
    Send a standalone Macro + Sectors update as its own Discord message.
    Uses DISCORD_WEBHOOK_MACRO, falls back to watchlist webhook if missing.
    """
    webhook = MAC or WL
    if not webhook:
        return  # nowhere to post

    # Build lines
    evs, _blocking = await today_events_pt()
    macro_line = header_for_events(evs)

    try:
        p = Polygon()
        sectors_line = await sectors_header(p)
        await p.close()
    except Exception:
        sectors_line = "Sectors: n/a"

    title = f"Macro Update – {datetime.now().strftime('%Y-%m-%d %H:%M PT')}"
    embed = {
        "title": title,
        "fields": [
            {"name": "Macro", "value": macro_line, "inline": False},
            {"name": "Sectors", "value": sectors_line, "inline": False},
        ],
        "footer": {"text": "Not financial advice"},
    }
    await _post(webhook, {"username": "Macro Bot 🗓️", "embeds": [embed]})
