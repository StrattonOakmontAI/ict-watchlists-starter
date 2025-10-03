# app/config.py  (simple, no external libs; safe indentation)

import os

# Read env vars (with sensible defaults)
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
MIN_SCORE = float(os.getenv("MIN_SCORE", "70"))
TZ = os.getenv("TZ", "America/Los_Angeles")

# Small holder object so other files can do: from app.config import settings
class Settings:
    polygon_key = POLYGON_API_KEY
    min_score = MIN_SCORE
    tz = TZ

settings = Settings()
