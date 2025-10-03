# app/polygon_client.py
# Minimal, indentation-safe Polygon client used by the MVP.
# Async httpx + pandas only. No decorators, no fancy retries (kept simple).

import os
import httpx
import pandas as pd

API = "https://api.polygon.io"
KEY = os.getenv("POLYGON_API_KEY", "")


class Polygon:
    def __init__(self, key: str | None = None):
        self.key = key or KEY
        # One async client reused for all calls
        self._client = httpx.AsyncClient(timeout=30)

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass

    async def aggs(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        _from: str,
        _to: str,
        limit: int = 50000,
    ) -> pd.DataFrame:
        """
        GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
        Returns a DataFrame indexed by UTC timestamp with columns:
        open, high, low, close, volume
        """
        url = f"{API}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{_from}/{_to}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": limit,
            "apiKey": self.key,
        }
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        js = r.json()
        rows = js.get("results", [])
        if not rows:
            # return an empty, correctly-shaped DataFrame
            return pd.DataFrame(
                columns=["ts", "open", "high", "low", "close", "volume"]
            ).set_index("ts")

        df = pd.DataFrame(rows)
        # Convert ms epoch to UTC tz-aware timestamp
        df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True)
        df = df.rename(
            columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
        )[["ts", "open", "high", "low", "close", "volume"]]
        return df.set_index("ts")

    async def options_chain_snapshot(self, underlying: str, **filters) -> dict:
        """
        GET /v3/snapshot/options/{underlying}
        Returns raw JSON (or {} on error/plan limitation).
        """
        url = f"{API}/v3/snapshot/options/{underlying}"
        params = {"apiKey": self.key, **filters}
        r = await self._client.get(url, params=params)
        if r.status_code >= 400:
            # Some Polygon plans may not include this endpoint; fail soft.
            try:
                r.raise_for_status()
            finally:
                return {}
        try:
            return r.json()
        except Exception:
            return {}

    async def news(self, ticker: str, limit: int = 20) -> list[dict]:
        """
        GET /v2/reference/news?ticker=...
        """
        url = f"{API}/v2/reference/news"
        params = {"apiKey": self.key, "ticker": ticker, "limit": limit, "order": "desc"}
        r = await self._client.get(url, params=params)
        if r.status_code >= 400:
            return []
        try:
            return r.json().get("results", [])
        except Exception:
            return []

    async def earnings(self, ticker: str, limit: int = 5) -> list[dict]:
        """
        Placeholder for earnings (depends on plan/endpoint availability).
        Return empty list for MVP; we’ll wire later.
        """
        return []
