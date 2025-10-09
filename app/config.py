"""
Minimal, robust settings (no extra deps). Guarantees `SETTINGS` exists.
All values come from environment variables. TZ defaults to America/Los_Angeles.
"""
from __future__ import annotations
import os

class Settings:
    def __init__(self) -> None:
        # Discord webhooks
        wl = (os.getenv("DISCORD_WEBHOOK_WATCHLIST", "") or "").strip()
        en = (os.getenv("DISCORD_WEBHOOK_ENTRIES", "") or "").strip()
        mc = (os.getenv("DISCORD_WEBHOOK_MACRO", "") or "").strip()

        self.discord_webhook_watchlist = wl
        # entries falls back to watchlist if empty
        self.discord_webhook_entries = en or wl
        # macro falls back to watchlist if empty
        self.discord_webhook_macro = mc or wl

        # Optional integrations
        self.journal_api_key = (os.getenv("JOURNAL_API_KEY", "") or "").strip() or None
        self.polygon_api_key = (os.getenv("POLYGON_API_KEY", "") or "").strip() or None

        # Time zone for scheduler
        self.tz = os.getenv("TZ", "America/Los_Angeles")

SETTINGS = Settings()  # <-- THIS is what cli.py imports
