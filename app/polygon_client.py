import os, math
from datetime import datetime, timedelta, timezone
import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential_jitter


API = "https://api.polygon.io"
KEY = os.getenv("POLYGON_API_KEY", "")


class Polygon:
def __init__(self, key: str | None = None):
self.key = key or KEY
self._client = httpx.AsyncClient(timeout=30)


async def close(self):
await self._client.aclose()


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 3))
async def aggs(self, ticker: str, multiplier: int, timespan: str, _from: str, _to: str, limit: int = 50000) -> pd.DataFrame:
# /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
url = f"{API}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{_from}/{_to}"
params = {"adjusted": "true", "sort": "asc", "limit": limit, "apiKey": self.key}
r = await self._client.get(url, params=params)
r.raise_for_status()
js = r.json()
rows = js.get("results", [])
if not rows:
return pd.DataFrame(columns=["ts","open","high","low","close","volume"]).set_index("ts")
df = pd.DataFrame(rows)
df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True)
df = df.rename(columns={"o":"open","h":"high","l":"low","c":"close","v":"volume"})[["ts","open","high","low","close","volume"]]
return df.set_index("ts")


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 3))
async def options_chain_snapshot(self, underlying: str, **filters) -> dict:
# /v3/snapshot/options/{underlying}
url = f"{API}/v3/snapshot/options/{underlying}"
params = {"apiKey": self.key, **filters}
r = await self._client.get(url, params=params)
r.raise_for_status()
return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 3))
async def news(self, ticker: str, limit: int = 20) -> list[dict]:
# /v2/reference/news
url = f"{API}/v2/reference/news"
params = {"apiKey": self.key, "ticker": ticker, "limit": limit, "order": "desc"}
r = await self._client.get(url, params=params)
r.raise_for_status()
return r.json().get("results", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 3))
async def earnings(self, ticker: str, limit: int = 5) -> list[dict]:
# Partners/Benzinga earnings (availability depends on plan)
url = f"{API}/vX/reference/financials/earnings" # fallback path; swap to exact once plan confirmed
params = {"apiKey": self.key, "ticker": ticker, "limit": limit}
r = await self._client.get(url, params=params)
if r.status_code == 404:
return []
r.raise_for_status()
return r.json().get("results", [])
