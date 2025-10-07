# app/polygon_client.py
# Minimal async Polygon client used by the watchlist + earnings/GEX features.

from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import httpx
import pandas as pd


class Polygon:
    def __init__(self) -> None:
        self.key = os.getenv("POLYGON_API_KEY", "").strip()
        if not self.key:
            raise RuntimeError("POLYGON_API_KEY is not set")
        self.x = httpx.AsyncClient(timeout=30)

    # ------------------------- Aggregates (bars) -------------------------

    async def aggs(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,  # "minute", "hour", "day"
        from_date: str,  # "YYYY-MM-DD"
        to_date: str,    # "YYYY-MM-DD"
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 50000,
    ) -> pd.DataFrame:
        """
        GET /v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from}/{to}
        Returns a UTC-indexed DataFrame with o/h/l/c/v columns.
        """
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {
            "adjusted": str(adjusted).lower(),
            "sort": sort,
            "limit": limit,
            "apiKey": self.key,
        }
        r = await self.x.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return pd.DataFrame(
                [], columns=["open", "high", "low", "close", "volume"]
            ).set_index(pd.DatetimeIndex([], tz="UTC"))
        df = pd.DataFrame(results)
        # Polygon uses ms epoch in "t"
        idx = pd.to_datetime(df["t"], unit="ms", utc=True)
        out = pd.DataFrame(
            {
                "open": df["o"].astype(float),
                "high": df["h"].astype(float),
                "low": df["l"].astype(float),
                "close": df["c"].astype(float),
                "volume": df["v"].astype(float),
            },
            index=idx,
        )
        return out

    # ------------------------- Options snapshots -------------------------

    async def options_chain_snapshot(
        self,
        ticker: str,
        limit: int = 250,          # Polygon docs: max 250
        paginate: bool = False,    # turn on later if you need more than 250
        max_pages: int = 8,
    ) -> Dict[str, Any]:
        """
        GET /v3/snapshot/options/{underlyingAsset}
        Returns JSON list of contracts including quotes/greeks when available.
        NOTE: 'limit' must be <= 250 or Polygon returns 400.
        """
        base = f"https://api.polygon.io/v3/snapshot/options/{ticker.upper()}"
        params = {"limit": min(250, int(limit)), "apiKey": self.key}

        # First page
        r = await self.x.get(base, params=params)
        r.raise_for_status()
        data = r.json()
        results = list(data.get("results") or [])

        # Optional pagination (next_url); off by default to save calls
        if paginate:
            next_url = data.get("next_url")
            pages = 0
            while next_url and pages < max_pages:
                # Ensure apiKey is present on the next_url (Polygon usually includes it)
                u = urlparse(next_url)
                q = parse_qs(u.query)
                if "apiKey" not in q:
                    q["apiKey"] = [self.key]
                    next_url = urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q, doseq=True), u.fragment))
                r2 = await self.x.get(next_url)
                r2.raise_for_status()
                d2 = r2.json()
                results.extend(d2.get("results") or [])
                next_url = d2.get("next_url")
                pages += 1

        return {"results": results}

    # ------------------------- Earnings (next report date) -------------------------

    async def next_earnings_date(self, ticker: str) -> Optional[str]:
        """
        GET /v3/reference/earnings?ticker=...&report_date.gte=TODAY&order=asc&sort=report_date&limit=1
        Returns 'YYYY-MM-DD' or None if no upcoming earnings found.
        """
        try:
            url = "https://api.polygon.io/v3/reference/earnings"
            params = {
                "ticker": ticker.upper(),
                "order": "asc",
                "sort": "report_date",
                "limit": 1,
                "report_date.gte": datetime.utcnow().date().isoformat(),
                "apiKey": self.key,
            }
            r = await self.x.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            res = data.get("results") or []
            if not res:
                return None
            return res[0].get("report_date")
        except Exception:
            return None

    # ------------------------- Lifecycle -------------------------

    async def close(self) -> None:
        try:
            await self.x.aclose()
        except Exception:
            pass
