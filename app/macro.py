# app/macro.py
from __future__ import annotations
import os, re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
from zoneinfo import ZoneInfo
import httpx

PT = ZoneInfo("America/Los_Angeles")

# Defaults (can override via env)
BLOCK_MIN = int(os.getenv("MACRO_BLOCK_MIN", "30"))
USE_BLOCK = os.getenv("MACRO_BLOCK_ENABLE", "1") == "1"
ICS_URL = os.getenv("MACRO_ICS_URL", "").strip()  # optional: your econ calendar ICS URL

# Keywords to keep (substring match, case-insensitive)
KEYWORDS = [
    "CPI", "Consumer Price Index",
    "Core CPI",
    "PPI", "Producer Price Index",
    "Core PPI",
    "PCE", "Core PCE",
    "Nonfarm", "NFP", "Employment Situation", "Unemployment Rate",
    "FOMC", "Fed Interest Rate", "Federal Funds Rate", "Fed Statement",
    "FOMC Minutes", "Fed Chair", "Powell Press Conference",
    "ISM Services", "ISM Manufacturing"
]
KW_RE = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)

@dataclass
class MacroEvent:
    title: str
    start_pt: datetime  # PT tz-aware

def _join_folded_ics(lines: List[str]) -> List[str]:
    out = []
    for ln in lines:
        if ln.startswith((" ", "\t")) and out:
            out[-1] += ln.strip()
        else:
            out.append(ln.rstrip("\n"))
    return out

def _parse_dt(dtstr: str, tzid: Optional[str]) -> Optional[datetime]:
    # Examples:
    # DTSTART:20251014T123000Z
    # DTSTART;TZID=America/New_York:20251014T083000
    try:
        if dtstr.endswith("Z"):
            dt = datetime.strptime(dtstr, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.astimezone(PT)
        fmt = "%Y%m%dT%H%M%S" if len(dtstr) == 15 else "%Y%m%dT%H%M"
        if tzid:
            dt = datetime.strptime(dtstr, fmt).replace(tzinfo=ZoneInfo(tzid))
            return dt.astimezone(PT)
        # assume UTC if no tz info
        dt = datetime.strptime(dtstr, fmt).replace(tzinfo=timezone.utc)
        return dt.astimezone(PT)
    except Exception:
        return None

async def _fetch_ics(url: str) -> str:
    async with httpx.AsyncClient(timeout=20) as x:
        r = await x.get(url)
        r.raise_for_status()
        return r.text

async def today_events_pt(now: Optional[datetime] = None) -> Tuple[List[MacroEvent], List[MacroEvent]]:
    """
    Returns (all_today, blocking_now) lists of MacroEvent in PT.
    If ICS_URL not set or fetch/parse fails, returns empty lists.
    """
    now = now or datetime.now(PT)
    if not ICS_URL:
        return ([], [])
    try:
        raw = await _fetch_ics(ICS_URL)
    except Exception:
        return ([], [])

    lines = _join_folded_ics(raw.splitlines())
    evs: List[MacroEvent] = []

    in_ev = False
    cur: dict = {}
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            in_ev, cur = True, {}
            continue
        if ln == "END:VEVENT":
            in_ev = False
            # finalize
            title = cur.get("SUMMARY", "")
            if not title or not KW_RE.search(title):
                continue
            dt = cur.get("DTSTART")
            tzid = cur.get("DTSTART_TZID")
            dt_pt = _parse_dt(dt, tzid) if dt else None
            if not dt_pt:
                continue
            if dt_pt.date() == now.date():
                evs.append(MacroEvent(title=title, start_pt=dt_pt))
            cur = {}
            continue
        if not in_ev:
            continue

        # DTSTART and DTSTART;TZID handling
        if ln.startswith("DTSTART;TZID="):
            # DTSTART;TZID=America/New_York:20251014T083000
            tzid, rest = ln.split(":", 1)
            cur["DTSTART_TZID"] = tzid.split("=", 1)[1]
            cur["DTSTART"] = rest.strip()
        elif ln.startswith("DTSTART:"):
            cur["DTSTART"] = ln.split(":", 1)[1].strip()
            cur["DTSTART_TZID"] = None
        elif ln.startswith("SUMMARY:"):
            cur["SUMMARY"] = ln.split(":", 1)[1].strip()

    # blocking window
    blocking: List[MacroEvent] = []
    if USE_BLOCK and BLOCK_MIN > 0:
        for e in evs:
            if abs((e.start_pt - now).total_seconds()) <= BLOCK_MIN * 60:
                blocking.append(e)
    return (evs, blocking)

def header_for_events(evs: List[MacroEvent], block_min: int = BLOCK_MIN) -> str:
    if not evs:
        return "Macro: none"
    def fmt(t: datetime) -> str:
        return t.strftime("%-I:%M%p").lower().replace(":00", "")  # e.g., '5am', '5:30am'
    parts = [f"{e.title} @ {fmt(e.start_pt)} PT" for e in evs[:4]]
    if len(evs) > 4:
        parts.append(f"+{len(evs)-4} more")
    return f"Macro: { '; '.join(parts) } (block ±{block_min}m)" if USE_BLOCK and block_min>0 else f"Macro: { '; '.join(parts) }"
