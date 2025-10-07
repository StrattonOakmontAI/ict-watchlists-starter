# app/journal.py
from __future__ import annotations
import csv, os
from datetime import datetime
from typing import Any, Dict, List, Iterable

# Where the journal lives (persisted on DO App Platform)
PATH = "/mnt/data/journal.csv"

FIELDS = [
    "timestamp_pt","kind","symbol","direction","entry","stop","t1","t2","t3","t4","score","proj_move_pct",
    "option_type","option_delta","option_expiry","option_strike","option_premium","option_roi_pct","option_dte","option_spread","option_oi",
    "ddoi","opex_week","earnings_soon","earnings_date","earnings_days_to","er_dir","er_conf","gex_peak_strike","gex_peak_side","gex_total"
]

def _ensure_dir():
    os.makedirs(os.path.dirname(PATH), exist_ok=True)

def append_row(row: Dict[str, Any]) -> None:
    """Append a single row to the CSV (creates header on first write)."""
    _ensure_dir()
    exists = os.path.exists(PATH)
    with open(PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)

def append_rows(rows: Iterable[Dict[str, Any]]) -> None:
    _ensure_dir()
    exists = os.path.exists(PATH)
    with open(PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)

def build_entry(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a 🚨 entry payload into one CSV row."""
    t1, t2, t3, t4 = (payload.get("targets") or [None, None, None, None])[:4]
    opt = payload.get("option") or {}
    bias = payload.get("bias") or {}
    return {
        "timestamp_pt": datetime.now().strftime("%Y-%m-%d %H:%M:%S PT"),
        "kind": kind,
        "symbol": payload.get("symbol"),
        "direction": payload.get("direction"),
        "entry": payload.get("entry"),
        "stop": payload.get("stop"),
        "t1": t1, "t2": t2, "t3": t3, "t4": t4,
        "score": payload.get("score"),
        "proj_move_pct": payload.get("proj_move_pct"),
        "option_type": opt.get("type"),
        "option_delta": opt.get("delta"),
        "option_expiry": opt.get("expiry"),
        "option_strike": opt.get("strike"),
        "option_premium": opt.get("premium"),
        "option_roi_pct": opt.get("roi_pct"),
        "option_dte": opt.get("dte"),
        "option_spread": opt.get("spread"),
        "option_oi": opt.get("oi"),
        "ddoi": bias.get("ddoi"),
        "opex_week": bias.get("opex_week"),
        "earnings_soon": bias.get("earnings_soon"),
        "earnings_date": bias.get("earnings_date"),
        "earnings_days_to": bias.get("earnings_days_to"),
        "er_dir": bias.get("er_dir"),
        "er_conf": bias.get("er_conf"),
        "gex_peak_strike": bias.get("gex_peak_strike"),
        "gex_peak_side": bias.get("gex_peak_side"),
        "gex_total": bias.get("gex_total"),
    }

def build_watchlist(kind: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn a 👀 watchlist (top N rows) into multiple journal rows (kind='watchlist')."""
    out: List[Dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S PT")
    for r in rows:
        t1, t2, t3, t4 = (r.get("targets") or [None, None, None, None])[:4]
        opt = r.get("option") or {}
        bias = r.get("bias") or {}
        out.append({
            "timestamp_pt": now,
            "kind": f"watchlist-{kind}",
            "symbol": r.get("symbol"),
            "direction": r.get("direction"),
            "entry": r.get("entry"),
            "stop": r.get("stop"),
            "t1": t1, "t2": t2, "t3": t3, "t4": t4,
            "score": r.get("score"),
            "proj_move_pct": r.get("proj_move_pct"),
            "option_type": opt.get("type"),
            "option_delta": opt.get("delta"),
            "option_expiry": opt.get("expiry"),
            "option_strike": opt.get("strike"),
            "option_premium": opt.get("premium"),
            "option_roi_pct": opt.get("roi_pct"),
            "option_dte": opt.get("dte"),
            "option_spread": opt.get("spread"),
            "option_oi": opt.get("oi"),
            "ddoi": bias.get("ddoi"),
            "opex_week": bias.get("opex_week"),
            "earnings_soon": bias.get("earnings_soon"),
            "earnings_date": bias.get("earnings_date"),
            "earnings_days_to": bias.get("earnings_days_to"),
            "er_dir": bias.get("er_dir"),
            "er_conf": bias.get("er_conf"),
            "gex_peak_strike": bias.get("gex_peak_strike"),
            "gex_peak_side": bias.get("gex_peak_side"),
            "gex_total": bias.get("gex_total"),
        })
    return out

def read_last(n: int = 200) -> List[Dict[str, Any]]:
    """Return last N rows (best-effort; small memory utility)."""
    if not os.path.exists(PATH):
        return []
    with open(PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-n:]
