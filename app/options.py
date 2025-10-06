# app/options.py
# Projection + option selection helpers (text-only alerts)

import os
from datetime import datetime, timezone
from math import sqrt

# Tunables from env (with safe defaults)
PROJ_DAYS = int(os.getenv("PROJ_DAYS", "10"))           # horizon for projection (calendar days)
DTE_MIN   = int(os.getenv("DTE_MIN", "7"))
DTE_MAX   = int(os.getenv("DTE_MAX", "14"))
DELTA_TARGET = float(os.getenv("DELTA_TARGET", "0.35"))
DELTA_BAND   = float(os.getenv("DELTA_BAND", "0.10"))   # target ± band -> [0.25..0.45]
DELTA_FALLBACK_MIN = float(os.getenv("DELTA_FALLBACK_MIN", "0.20"))
DELTA_FALLBACK_MAX = float(os.getenv("DELTA_FALLBACK_MAX", "0.50"))
OI_MIN     = int(os.getenv("OI_MIN", "1000"))
SPREAD_MAX = float(os.getenv("SPREAD_MAX", "0.10"))     # 10% of mid
PROJ_MIN   = float(os.getenv("PROJ_MIN", "0.05"))       # 5%
PROJ_MAX   = float(os.getenv("PROJ_MAX", "0.10"))       # 10%


def _get(d, *path, default=None):
    """Nested getter with default."""
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _try_float(x, default=0.0):
    try:
        if x is None: 
            return default
        return float(x)
    except Exception:
        return default


def _mid_quote(opt: dict) -> float:
    """Return mid from last_quote; fallback to (ask+bid)/2 > 0."""
    bid = _try_float(_get(opt, "last_quote", "bid"))
    ask = _try_float(_get(opt, "last_quote", "ask"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    # try alternative nesting
    bid = _try_float(_get(opt, "quote", "bid_price"))
    ask = _try_float(_get(opt, "quote", "ask_price"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    price = _try_float(_get(opt, "last_trade", "price"))
    return price if price > 0 else 0.0


def _spread_pct(opt: dict) -> float:
    bid = _try_float(_get(opt, "last_quote", "bid"))
    ask = _try_float(_get(opt, "last_quote", "ask"))
    mid = _mid_quote(opt)
    if mid <= 0 or ask <= 0 or bid < 0:
        return 1.0
    return (ask - bid) / mid


def _dte_days(exp_str: str) -> int:
    try:
        # exp string 'YYYY-MM-DD'
        e = datetime.fromisoformat(exp_str).replace(tzinfo=timezone.utc)
        today = datetime.utcnow().replace(tzinfo=timezone.utc)
        return max(0, (e - today).days)
    except Exception:
        return 0


def iv_implied_move(chain_json: dict, t_days: int = PROJ_DAYS, direction: str = "bullish") -> float:
    """
    Approximate underlying move fraction from ATM IV over t_days:
      move ≈ IV * sqrt(t_days / 365)
    Pull IV from near-ATM options within DTE_RANGE and |delta| ~ 0.35 (fallback to 0.30..0.50).
    Returns a fraction (e.g., 0.07 = 7%).
    """
    results = chain_json.get("results") or chain_json.get("options") or []
    if not results:
        return 0.0

    # Filter by type (CALL for bullish, PUT for bearish) and DTE window
    want_call = (direction == "bullish")
    primary, fallback = [], []
    for opt in results:
        ctype = str(_get(opt, "details", "contract_type", default=_get(opt, "contract_type", default=""))).lower()
        if want_call and not ctype.startswith("c"): 
            continue
        if (not want_call) and not ctype.startswith("p"):
            continue
        exp = str(_get(opt, "details", "expiration_date", default=_get(opt, "expiration_date", default="")))
        dte = _dte_days(exp)
        if dte < DTE_MIN or dte > DTE_MAX:
            continue
        delta = abs(_try_float(_get(opt, "greeks", "delta")))
        iv = _try_float(_get(opt, "greeks", "iv"))
        if iv <= 0:
            continue
        if abs(delta - DELTA_TARGET) <= DELTA_BAND:
            primary.append(iv)
        elif DELTA_FALLBACK_MIN <= delta <= DELTA_FALLBACK_MAX:
            fallback.append(iv)

    pool = primary or fallback
    if not pool:
        return 0.0
    iv_avg = sum(pool) / len(pool)
    return max(0.0, float(iv_avg) * sqrt(max(1.0, float(t_days)) / 365.0))


def atr20_percent(df_daily) -> float:
    """
    ATR20 as a % of last close using daily bars DataFrame with columns: open, high, low, close.
    """
    try:
        if df_daily is None or len(df_daily) < 21:
            return 0.0
        h = df_daily["high"]
        l = df_daily["low"]
        c = df_daily["close"]
        c1 = c.shift(1)
        tr = (h - l).combine((h - c1).abs(), max).combine((l - c1).abs(), max)
        atr = tr.rolling(20).mean()
        last_close = float(c.iloc[-1])
        if last_close <= 0:
            return 0.0
        return float(atr.iloc[-1]) / last_close
    except Exception:
        return 0.0


def pick_best_option(chain_json: dict, underlying_price: float, move_frac: float, direction: str):
    """
    Choose the option with highest estimated ROI under the projected move:
      ROI% ≈ (|delta| * underlying_price * move_frac) / premium * 100
    Filters: DTE [7,14], OI≥1000, spread≤10%, delta in [0.25..0.45] (fallback 0.20..0.50).
    Returns dict or None:
      {
        'type': 'CALL'|'PUT', 'expiry': 'YYYY-MM-DD', 'strike': float,
        'delta': float, 'premium': float, 'roi_pct': float, 'dte': int, 'spread': float
      }
    """
    results = chain_json.get("results") or chain_json.get("options") or []
    if underlying_price <= 0 or not results or move_frac <= 0:
        return None

    want_call = (direction == "bullish")
    primary, secondary = [], []

    for opt in results:
        ctype = str(_get(opt, "details", "contract_type", default=_get(opt, "contract_type", default=""))).lower()
        if want_call and not ctype.startswith("c"): 
            continue
        if (not want_call) and not ctype.startswith("p"):
            continue

        exp = str(_get(opt, "details", "expiration_date", default=_get(opt, "expiration_date", default="")))
        dte = _dte_days(exp)
        if dte < DTE_MIN or dte > DTE_MAX:
            continue

        oi = int(_try_float(_get(opt, "open_interest")))
        if oi < OI_MIN:
            continue

        mid = _mid_quote(opt)
        if mid <= 0:
            continue

        sp_pct = _spread_pct(opt)
        if sp_pct > SPREAD_MAX:
            continue

        delta = abs(_try_float(_get(opt, "greeks", "delta")))
        strike = _try_float(_get(opt, "details", "strike_price", default=_get(opt, "strike_price", default=0.0)))

        # estimated ROI
        roi = (delta * underlying_price * move_frac) / mid * 100.0

        row = {
            "type": "CALL" if want_call else "PUT",
            "expiry": exp,
            "strike": strike,
            "delta": round(delta, 2),
            "premium": round(mid, 2),
            "roi_pct": round(roi, 1),
            "dte": dte,
            "spread": round(sp_pct, 3),
        }

        if abs(delta - DELTA_TARGET) <= DELTA_BAND:
            primary.append(row)
        elif DELTA_FALLBACK_MIN <= delta <= DELTA_FALLBACK_MAX:
            secondary.append(row)

    pool = primary or secondary
    if not pool:
        return None
    # pick by highest ROI%
    pool.sort(key=lambda r: r["roi_pct"], reverse=True)
    return pool[0]
