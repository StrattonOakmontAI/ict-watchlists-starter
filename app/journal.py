# app/journal.py
from __future__ import annotations
import csv, os, io, base64
from datetime import datetime
from typing import Any, Dict, List, Iterable

# Local cache path (per-container)
PATH = "/mnt/data/journal.csv"

# -------- GitHub storage config --------
GH_REPO   = os.getenv("GH_REPO", "").strip()        # "owner/repo"
GH_TOKEN  = os.getenv("GH_TOKEN", "").strip()
GH_BRANCH = os.getenv("GH_BRANCH", "main").strip()
GH_PATH   = os.getenv("GH_PATH", "journal/journal.csv").lstrip("/")

GH_ENABLED = bool(GH_REPO and GH_TOKEN and GH_PATH)

FIELDS = [
    "timestamp_pt","kind","symbol","direction","entry","stop","t1","t2","t3","t4","score","proj_move_pct",
    "option_type","option_delta","option_expiry","option_strike","option_premium","option_roi_pct","option_dte","option_spread","option_oi",
    "ddoi","opex_week","earnings_soon","earnings_date","earnings_days_to","er_dir","er_conf","gex_peak_strike","gex_peak_side","gex_total"
]

def _ensure_dir():
    os.makedirs(os.path.dirname(PATH), exist_ok=True)

# -------- GitHub API helpers (contents API) --------
def _gh_base():
    return f"https://api.github.com/repos/{GH_REPO}/contents/{GH_PATH}"

def _gh_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _gh_get():
    """GET file metadata+content (base64) from GitHub. Returns dict or None."""
    if not GH_ENABLED: return None
    import httpx
    params = {"ref": GH_BRANCH}
    r = httpx.get(_gh_base(), headers=_gh_headers(), params=params, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()

def _gh_download_bytes() -> bytes | None:
    """Download file bytes from GitHub Contents API. Returns None if missing."""
    meta = _gh_get()
    if not meta or "content" not in meta:
        return None
    b64 = meta["content"].encode()
    # GitHub inserts newlines every 76 chars; safe to decode anyway
    return base64.b64decode(b64)

def _gh_put_bytes(data: bytes, message: str = "Update journal.csv") -> None:
    """PUT new content to GitHub (create or update)."""
    if not GH_ENABLED: return
    import httpx, json
    sha = None
    meta = _gh_get()
    if meta and isinstance(meta, dict):
        sha = meta.get("sha")
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode(),
        "branch": GH_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = httpx.put(_gh_base(), headers=_gh_headers(), json=payload, timeout=30)
    # Avoid crashing the app on 409 (conflict) or other issues; best-effort only
    if r.status_code in (200, 201):
        return
    # Try one simple conflict retry: refresh SHA then PUT again
    try:
        meta2 = _gh_get()
        if meta2 and meta2.get("sha") != sha:
            payload["sha"] = meta2.get("sha")
            r2 = httpx.put(_gh_base(), headers=_gh_headers(), json=payload, timeout=30)
            if r2.status_code in (200, 201):
                return
    except Exception:
        pass
    # last resort: do nothing (silent)

# Expose for API module
def _remote_download_bytes() -> bytes | None:
    return _gh_download_bytes() if GH_ENABLED else None

# -------- CSV I/O --------
def append_row(row: Dict[str, Any]) -> None:
    _ensure_dir()
    exists = os.path.exists(PATH)
    with open(PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)
    # mirror to GitHub
    try:
        with open(PATH, "rb") as f:
            _gh_put_bytes(f.read(), message=f"append 1 row ({row.get('symbol','?')})")
    except Exception:
        pass

def append_rows(rows: Iterable[Dict[str, Any]]) -> None:
    _ensure_dir()
    exists = os.path.exists(PATH)
    with open(PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)
    try:
        with open(PATH, "rb") as f:
            _gh_put_bytes(f.read(), message=f"append {len(list(rows))} rows")
    except Exception:
        pass

def read_last(n: int = 200) -> List[Dict[str, Any]]:
    # prefer local cache; hydrate from GitHub if missing
    if not os.path.exists(PATH) and GH_ENABLED:
        data = _gh_download_bytes()
        if data:
            _ensure_dir()
            with open(PATH, "wb") as f:
                f.write(data)
    if not os.path.exists(PATH):
        return []
    with open(PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-n:]

def build_entry(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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
