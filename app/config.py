import os
from pydantic import BaseModel


class Settings(BaseModel):
polygon_key: str = os.getenv("POLYGON_API_KEY", "")
min_score: float = float(os.getenv("MIN_SCORE", "70"))
tz: str = os.getenv("TZ", "America/Los_Angeles")


settings = Settings()
