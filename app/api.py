from __future__ import annotations

# Why: allow .env in local/dev without breaking production
try:
    import app.env  # noqa: F401
except Exception:
    pass

import os
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse

# ---- Robust config import (works whether config exports `settings` or `SETTINGS`) ----
try:
    from app.config import settings as SETTINGS  # preferred: instance "settings"
except Exception:
    try:
        from app.config import SETTINGS  # fallback: uppercase const
    except Exception:
        # Final fallback so API stays up even if config import fails
        class _Fallback:
            tz = "America/Los_Angeles"
        SETTINGS = _Fallback()  # type: ignore

# ---- App instance ----
app = FastAPI(title="ICT Watchlists API", version="1.0.0")
API = app  # alias so both `uvicorn app.api:app` and `uvicorn app.api:API` work

# ---- Optional: mount /env-check if the module exists ----
try:
    from app.env_check import router as env_router
    app.include_router(env_router)
except Exception:
    pass

# ---- Shared state file written by the scheduler/cli (container-local) ----
LAST_RUNS_PATH = Path("/tmp/last_runs.json")


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/status", response_class=JSONResponse)
def status() -> Dict[str, Any]:
    """Return TZ, schedule times, last-run markers, and env presence flags."""
    # Schedule from env with safe defaults
    pre = os.getenv("SCHED_PREMARKET", "06:30")
    eve = os.getenv("SCHED_EVENING", "13:00")
    wk  = os.getenv("SCHED_WEEKLY",  "06:00")

    # Read last-run markers if present
    last_runs: Dict[str, Any] = {}
    try:
        if LAST_RUNS_PATH.exists():
            last_runs = json.loads(LAST_RUNS_PATH.read_text())
        else:
            last_runs = {"_note": "no runs recorded yet"}
    except Exception as e:
        last_runs = {"_error": f"unable to read last-run file: {e!s}"}

    # Do not leak secrets; only indicate presence
    env_flags = {
        "DISCORD_WEBHOOK_WATCHLIST_set": bool(os.getenv("DISCORD_WEBHOOK_WATCHLIST")),
        "DISCORD_WEBHOOK_ENTRIES_set":  bool(os.getenv("DISCORD_WEBHOOK_ENTRIES")),
        "POLYGON_API_KEY_set":          bool(os.getenv("POLYGON_API_KEY")),
    }

    return {
        "service": "ict-watchlists",
        "tz": getattr(SETTINGS, "tz", "America/Los_Angeles"),
        "schedule": {"premarket": pre, "evening": eve, "weekly": wk},
        "last_runs": last_runs,
        "env": env_flags,
    }
