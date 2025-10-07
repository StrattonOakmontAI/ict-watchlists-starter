# app/bias/gex.py
from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List, Tuple

def _num(x, d=None):
    try:
        return float(x)
    except Exception:
        return d

def _contract_iter(chain: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Yield option contracts from Polygon chain snapshot safely."""
    if not chain:
        return []
    # Polygon returns either {"results":[{...}, ...]} or {"options":[...]}
    items = chain.get("results") or chain.get("options") or []
    return items if isinstance(items, list) else []

def _extract_contract_fields(c: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common fields across Polygon shapes."""
    details = c.get("details", {})
    last_quote = c.get("last_quote", {}) or c.get("quote", {}) or {}
    greeks = c.get("greeks", {}) or {}
    typ = (details.get("contract_type") or c.get("contract_type") or c.get("type") or "").lower()
    strike = _num(details.get("strike_price") or c.get("strike") or c.get("strike_price"))
    expiry = (details.get("expiration_date") or c.get("expiration_date") or c.get("expiry") or "")
    oi = _num(c.get("open_interest") or last_quote.get("open_interest") or c.get("oi"), 0.0)
    bid = _num(last_quote.get("bid") or c.get("bid"))
    ask = _num(last_quote.get("ask") or c.get("ask"))
    gamma = _num(greeks.get("gamma"))
    return {
        "type": typ, "strike": strike, "expiry": expiry, "oi": oi,
        "bid": bid, "ask": ask, "gamma": gamma
    }

def _within_window(strike: float, spot: float, win_pct: float) -> bool:
    if strike is None or spot is None:
        return False
    low, high = spot * (1 - win_pct), spot * (1 + win_pct)
    return low <= strike <= high

def _spread_ok(bid: float|None, ask: float|None, max_rel: float) -> bool:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return False
    mid = 0.5 * (bid + ask)
    rel = (ask - bid) / mid if mid > 0 else 1e9
    return rel <= max_rel

def compute_gex(
    chain: Dict[str, Any],
    spot: float,
    window_pct: float = 0.15,
    oi_min: int = 500,
    spread_max: float = 0.20,
) -> Dict[str, Any]:
    """
    Simplified GEX: sum(sign * gamma * OI * 100 * spot^2) over contracts within strike window.
    sign = +1 for CALL, -1 for PUT (SqueezeMetrics convention).
    Requires greeks.gamma in snapshot; contracts missing gamma are skipped.
    """
    items = _contract_iter(chain)
    call_sum = 0.0
    put_sum = 0.0
    per_strike = defaultdict(float)
    used = 0

    for raw in items:
        c = _extract_contract_fields(raw)
        if c["gamma"] is None or c["strike"] is None or c["oi"] is None:
            continue
        if not _within_window(c["strike"], spot, window_pct):
            continue
        if c["oi"] < oi_min:
            continue
        if not _spread_ok(c["bid"], c["ask"], spread_max):
            continue

        # contract GEX
        gex = c["gamma"] * c["oi"] * 100.0 * (spot ** 2)
        if c["type"] == "call":
            call_sum += gex
            per_strike[(c["strike"], "call")] += gex
        elif c["type"] == "put":
            put_sum += gex
            per_strike[(c["strike"], "put")] += gex
        else:
            continue
        used += 1

    total = call_sum - put_sum  # calls positive, puts negative
    # Peak strike by absolute exposure (use combined key)
    peak_key = None
    peak_val = 0.0
    for k, v in per_strike.items():
        if abs(v) > abs(peak_val):
            peak_key, peak_val = k, v

    peak_strike = peak_key[0] if peak_key else None
    peak_side = peak_key[1] if peak_key else None

    denom = abs(call_sum) + abs(put_sum) + 1e-9
    tilt = (call_sum - abs(put_sum)) / denom  # + = call heavy, - = put heavy

    return {
        "spot": spot,
        "window_pct": window_pct,
        "contracts_used": used,
        "gex_total": total,
        "gex_calls": call_sum,
        "gex_puts": put_sum,
        "gex_tilt": tilt,
        "gex_peak_strike": peak_strike,
        "gex_peak_side": peak_side,
        "gex_peak_value": peak_val,
    }

def predict_earnings_move(
    gex: Dict[str, Any],
    days_to_earnings: int | None = None,
) -> Dict[str, Any]:
    """
    Heuristic post-earnings direction:
      - Positive net GEX → dealers long gamma → pin/range more likely ("Pin").
      - Negative net GEX → short gamma → larger move; use tilt to bias direction:
          tilt >> 0 → upside bias; tilt << 0 → downside bias.
    Confidence grows with |tilt| and |total_gex|.
    """
    total = gex.get("gex_total", 0.0) or 0.0
    tilt = gex.get("gex_tilt", 0.0) or 0.0

    if total > 0:
        er_dir = "Pin"  # positive GEX tends to absorb shocks
    else:
        # short gamma → choose direction by tilt
        if tilt >= 0.2:
            er_dir = "Up"
        elif tilt <= -0.2:
            er_dir = "Down"
        else:
            er_dir = "Two-sided"

    # crude confidence: |tilt| drives most of it; days proximity gives a small boost
    base = min(1.0, abs(tilt))
    extra = 0.05 if (days_to_earnings is not None and 0 <= days_to_earnings <= 3) else 0.0
    conf = max(0.5, min(0.95, 0.55 + 0.4 * base + extra))  # 55–95%

    return {"er_dir": er_dir, "er_conf": conf}
