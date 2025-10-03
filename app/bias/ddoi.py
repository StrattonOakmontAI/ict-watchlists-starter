# app/bias/ddoi.py
# Lightweight Dealer-Directional Positioning proxy from Polygon options snapshot.

def ddoi_from_chain(chain_json: dict) -> dict:
    """
    Compute a very simple proxy:
      - net_gex  = sum(gamma * OI * sign(call=+1, put=-1))
      - net_delta = sum(delta * OI * sign(call=+1, put=-1))
    Works with Polygon /v3/snapshot/options payloads.
    Returns {'net_gex': float, 'net_delta': float}
    """
    results = (
        chain_json.get("results")
        or chain_json.get("options")
        or []
    )
    gex = 0.0
    ndelta = 0.0

    for opt in results:
        greeks = opt.get("greeks") or {}
        oi = opt.get("open_interest") or 0
        gamma = greeks.get("gamma") or 0.0
        delta = greeks.get("delta") or 0.0

        # contract type: try nested 'details' first, then top-level
        details = opt.get("details") or {}
        ctype = (details.get("contract_type") or opt.get("contract_type") or "").upper()
        sgn = 1 if ctype.startswith("C") else -1  # calls +1, puts -1

        gex += float(gamma) * float(oi) * sgn
        ndelta += float(delta) * float(oi) * sgn

    return {"net_gex": float(gex), "net_delta": float(ndelta)}
