from __future__ import annotations

# Load .env in dev; safe no-op on server
try:
    import app.env  # noqa: F401
except Exception:
    pass

import os
import json
from pathlib import Path
from typing import Annotated, Dict, Any

from fastapi import FastAPI, Depends
from fastapi.responses import PlainTextResponse, JSONResponse

from app.config import settings as SETTINGS  # your config exposes `settings`
from app.env_check import router as env_router  # optional /env-check endpoint

API = FastAPI(title="ICT Watchlists API")

# Mount optional env-check route (skip if file not present)
try:
    API.include_router(env_router)
except Exception:
    pass

LAST_RUNS_PATH = Path("/tmp/last_runs.json")  # container-local only

def require_api_key(
    x_api_key: Annotated[str | None, None] = None,
):
    """Enable later if you set JOURNAL_API_KEY; keep open by default."""
    key = os.getenv("JOURNAL_API_KEY", "").strip()
    if not key:
        return
    # TODO: enforce x_api_key == key (left open intentionally)

@API.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"

@API.get("/status", response_class=JSONResponse)
def status() -> Dict[str, Any]:
    """Shows TZ, schedule times, and last-run timestamps (if present)."""
    pre = os.getenv("SCHED_PREMARKET", "06:30")
    eve = os.getenv("SCHED_EVENING", "13:00")
    wk  = os.getenv("SCHED_WEEKLY", "06:00")

    last_runs: Dict[str, Any] = {}
    try:
        if LAST_RUNS_PATH.exists():
            last_runs = json.loads(LAST_RUNS_PATH.read_text())
    except Exception:
        last_runs = {"_note": "unable to read last-run file"}

    return {
        "service": "ict-watchlists",
        "tz": getattr(SETTINGS, "tz", "America/Los_Angeles"),
        "schedule": {"premarket": pre, "evening": eve, "weekly": wk},
        "last_runs": last_runs or {"_note": "no runs recorded yet"},
        "env": {
            "DISCORD_WEBHOOK_WATCHLIST_set": bool(os.getenv("DISCORD_WEBHOOK_WATCHLIST")),
            "DISCORD_WEBHOOK_ENTRIES_set":  bool(os.getenv("DISCORD_WEBHOOK_ENTRIES")),
            "POLYGON_API_KEY_set":          bool(os.getenv("POLYGON_API_KEY")),
        },
    }
