# app/macro.py
from __future__ import annotations
import os, re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from zoneinfo import ZoneInfo
import httpx

PT = ZoneInfo("America/Los_Angeles")

# ===== Env knobs (ICS-only) =====
BLOCK_MIN   = int(os.getenv("MACRO_BLOCK_MIN", "30"))
USE_BLOCK   = os.getenv("MACRO_BLOCK_ENABLE", "1") == "1"

# Supply ONE or more ICS URLs (we’ll merge them). For you: just BLS.
ICS_URL       = os.getenv("MACRO_ICS_URL", "").strip()
ICS_URL_BLS   = os.getenv("MACRO_ICS_URL_BLS", "").strip()
ICS_URLS_LIST = [u.strip() for u in os.getenv("MACRO_ICS_URLS", "").split(",") if u.strip()]

# Keep only macro keywords you care about (BLS covers CPI, PPI, NFP, etc.)
KEYWORDS = [
    "CPI","Consumer Price Index","Core CPI",
    "PPI","Producer Price Index","Core PPI",
    "PCE","Core PCE",
    "Nonfarm","NFP","Employment Situation","Unemployment Rate",
    "ISM Services","ISM Manufacturing",
]
KW_RE = re.compile("|".join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)


@dataclass
class MacroEvent:
    title: str
    start_pt: datetime  # tz-aware PT


def _gather_ics_urls() -> List[str]:
    urls: List[str] = []
    for u in (ICS_URL, ICS_URL_BLS):
        if u:
            urls.append(u)
    urls.extend(ICS_URLS_LIST)
    # de-dupe, keep order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            out.append(u); seen.add(u)
    return out


async def _fetch_ics(url: str) -> str:
    async with httpx.AsyncClient(timeout=20) as x:
        r = await x.get(url)
        r.raise_for_status()
        return r.text


def _join_folded_ics(lines: List[str]) -> List[str]:
    out = []
    for ln in lines:
        if ln.startswith((" ", "\t")) and out:
            out[-1] += ln.strip()
        else:
            out.append(ln.rstrip("\n"))
    return out


def _parse_dt_to_pt(dtstr: str, tzid: Optional[str]) -> Optional[datetime]:
    # Handles: DTSTART:20251014T123000Z  |  DTSTART;TZID=America/New_York:20251014T083000
    try:
        if dtstr.endswith("Z"):
            dt = datetime.strptime(dtstr, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.astimezone(PT)
        fmt = "%Y%m%dT%H%M%S" if len(dtstr) == 15 else "%Y%m%dT%H%M"
        if tzid:
            dt = datetime.strptime(dtstr, fmt).replace(tzinfo=ZoneInfo(tzid))
            return dt.astimezone(PT)
        dt = datetime.strptime(dtstr, fmt).replace(tzinfo=timezone.utc)
        return dt.astimezone(PT)
    except Exception:
        return None


def _parse_ics_to_events(ics_text: str) -> List[MacroEvent]:
    lines = _join_folded_ics(ics_text.splitlines())
    evs: List[MacroEvent] = []
    in_ev, cur = False, {}
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            in_ev, cur = True, {}; continue
        if ln == "END:VEVENT":
            in_ev = False
            title = cur.get("SUMMARY", "")
            if title and KW_RE.search(title):
                dt = cur.get("DTSTART"); tzid = cur.get("DTSTART_TZID")
                dt_pt = _parse_dt_to_pt(dt, tzid) if dt else None
                if dt_pt:
                    evs.append(MacroEvent(title=title, start_pt=dt_pt))
            cur = {}; continue
        if not in_ev:
            continue

        if ln.startswith("DTSTART;TZID="):
            tzid, rest = ln.split(":", 1)
            cur["DTSTART_TZID"] = tzid.split("=", 1)[1]
            cur["DTSTART"] = rest.strip()
        elif ln.startswith("DTSTART:"):
            cur["DTSTART"] = ln.split(":", 1)[1].strip()
            cur["DTSTART_TZID"] = None
        elif ln.startswith("SUMMARY:"):
            cur["SUMMARY"] = ln.split(":", 1)[1].strip()
    return evs


def header_for_events(evs: List[MacroEvent], block_min: int = BLOCK_MIN) -> str:
    if not evs:
        return "Macro: none"
    def fmt(t: datetime) -> str:
        s = t.strftime("%-I:%M%p").lower()
        return s.replace(":00", "")  # 5am / 5:30am
    parts = [f"{e.title} @ {fmt(e.start_pt)} PT" for e in sorted(evs, key=lambda x: x.start_pt)[:4]]
    more = len(evs) - 4
    if more > 0:
        parts.append(f"+{more} more")
    if USE_BLOCK and block_min > 0:
        return f"Macro: {'; '.join(parts)} (block ±{block_min}m)"
    return f"Macro: {'; '.join(parts)}"


async def today_events_pt(now: Optional[datetime] = None) -> Tuple[List[MacroEvent], List[MacroEvent]]:
    """
    Merge events from provided ICS feeds (e.g., BLS). Returns (today, blocking_now).
    """
    now = now or datetime.now(PT)
    urls = _gather_ics_urls()
    if not urls:
        return ([], [])

    # fetch ICS in parallel
    texts: List[str] = []
    async with httpx.AsyncClient(timeout=20) as x:
        results = []
        for u in urls:
            try:
                r = await x.get(u); r.raise_for_status()
                results.append(r.text)
            except Exception:
                results.append("")
        texts = results

    # parse & keep only today (PT)
    all_evs: List[MacroEvent] = []
    for txt in texts:
        if not txt:
            continue
        try:
            all_evs.extend(_parse_ics_to_events(txt))
        except Exception:
            pass

    today = [e for e in all_evs if e.start_pt.date() == now.date()]

    # blocking window
    blocking: List[MacroEvent] = []
    if USE_BLOCK and BLOCK_MIN > 0:
        for e in today:
            if abs((e.start_pt - now).total_seconds()) <= BLOCK_MIN * 60:
                blocking.append(e)
    return (today, blocking)
