# app/journal.py
from __future__ import annotations
import csv, os
from datetime import datetime
from typing import Any, Dict, List

PATH = "/mnt/data/journal.csv"
FIELDS = [
    "timestamp_pt","kind","symbol","direction","entry","stop","t1","t2","t3","t4","score","proj_move_pct",
    "option_type","option_delta","option_expiry","option_strike","option_premium","option_roi_pct","option_dte","option_spread",
    "ddoi","opex_week","earnings_soon","earnings_date","earnings_days_to","er_dir","er_conf","gex_peak_strike","gex_peak_side","gex_total"
]

def append_entry(row: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    exists = os.path.exists(PATH)
    with open(PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)

def build_row(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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
