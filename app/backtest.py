rm -f app/backtest.py
cat > app/backtest.py <<'PY'
import os
import sys
import csv
import asyncio
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from app.polygon_client import Polygon
from app.config import settings
from app.notify import send_watchlist  # reuse for summary post

JOURNAL_PATH = os.getenv("JOURNAL_PATH", "/mnt/data/journal.csv")
DEF_DAYS = int(os.getenv("BACKTEST_DAYS", "5"))
DEF_TF_MIN = int(os.getenv("BACKTEST_TF_MIN", "5"))
DEF_LIMIT = int(os.getenv("BACKTEST_LIMIT", "50"))
DEF_CONC = int(os.getenv("BACKTEST_CONCURRENCY", "5"))

PT = settings.tz  # America/Los_Angeles tzinfo


def ensure_journal_local() -> bool:
    """If /mnt/data/journal.csv is missing, try to pull it from GitHub env vars."""
    if os.path.exists(JOURNAL_PATH):
        return True
    repo = os.getenv('GH_REPO')
    tok  = os.getenv('GH_TOKEN')
    br   = os.getenv('GH_BRANCH', 'main')
    pth  = os.getenv('GH_PATH', 'journal/journal.csv')
    if not (repo and tok):
        return False
    try:
        import httpx, base64, pathlib
        url = f"https://api.github.com/repos/{repo}/contents/{pth}"
        hdr = {'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json'}
        r = httpx.get(url, headers=hdr, params={'ref': br}, timeout=20)
        r.raise_for_status()
        data = base64.b64decode(r.json()['content'])
        pathlib.Path(os.path.dirname(JOURNAL_PATH)).mkdir(parents=True, exist_ok=True)
        with open(JOURNAL_PATH, 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


@dataclass
class Trade:
    ts: datetime
    symbol: str
    direction: str
    entry: float
    stop: float
    t1: float
    t2: float
    t3: float
    t4: float
    kind: str = "entry"

    @property
    def risk_R(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def is_long(self) -> bool:
        d = (self.direction or "").lower()
        return d in ("long", "bull", "bullish", "buy")

    @property
    def is_short(self) -> bool:
        return not self.is_long


def _parse_row(row: dict):
    n = { (k or "").strip().lower(): (v or "").strip() for k,v in row.items() }
    def pick(*names, default=None):
        for nm in names:
            if nm in n and n[nm] != "": return n[nm]
        return default
    ts_raw = pick("timestamp_pt","timestamp","time")
    sym    = (pick("symbol","ticker") or "").upper()
    direction = pick("direction","dir") or ""
    entry  = pick("entry"); stop = pick("stop")
    t1 = pick("t1","T1"); t2 = pick("t2","T2"); t3 = pick("t3","T3"); t4 = pick("t4","T4")
    kind = pick("kind","type", default="entry") or "entry"
    if not all([ts_raw,sym,direction,entry,stop,t1,t2,t3,t4]): return None
    try:
        entry=float(entry); stop=float(stop); t1=float(t1); t2=float(t2); t3=float(t3); t4=float(t4)
    except Exception:
        return None
    s = ts_raw.replace("  "," ").strip()
    ts = None
    fmts = ["%Y-%m-%d %H:%M:%S PT","%Y-%m-%d %H:%M PT","%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt.endswith("PT"):
                ts = dt.replace(tzinfo=PT)
            else:
                ts = dt if dt.tzinfo else dt.replace(tzinfo=PT)
                if ts.tzinfo != PT: ts = ts.astimezone(PT)
            break
        except Exception:
            pass
    if ts is None:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m
