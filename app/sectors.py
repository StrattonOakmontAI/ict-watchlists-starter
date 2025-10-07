# app/sectors.py
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from app.polygon_client import Polygon

SECTORS = [
    ("XLC", "CommSvcs"),
    ("XLY", "Disc"),
    ("XLP", "Staples"),
    ("XLE", "Energy"),
    ("XLF", "Fin"),
    ("XLV", "Health"),
    ("XLI", "Indust"),
    ("XLB", "Mat"),
    ("XLRE", "RE"),
    ("XLK", "Tech"),
    ("XLU", "Utils"),
]

THRESH = 0.003  # 0.3% up/down threshold for arrow

async def sectors_header(p: Polygon) -> str:
    to = datetime.utcnow().date()
    frm = (datetime.utcnow() - timedelta(days=15)).date()
    out: List[str] = []
    for sym, label in SECTORS:
        try:
            df = await p.aggs(sym, 1, "day", frm.isoformat(), to.isoformat())
            closes = df["close"].dropna().tail(2).tolist()
            if len(closes) < 2:
                out.append(f"{label}·")
                continue
            pct = (closes[-1] / closes[-2] - 1.0)
            arrow = "↑" if pct > THRESH else ("↓" if pct < -THRESH else "–")
            out.append(f"{label}{arrow}")
        except Exception:
            out.append(f"{label}·")
    return "Sectors: " + "  ".join(out)
