# app/ranking.py

def score(confluence: dict, bias: dict, atr_like: float, spread_ok: bool) -> float:
    """
    Simple 0–100 score combining ICT confluence + bias + basic liquidity.
    """
    s = 0.0
    # ICT confluences
    if confluence.get("bos"):  s += 20
    if confluence.get("fvg"):  s += 20
    if confluence.get("ob"):   s += 20
    if confluence.get("eq_liq"): s += 10

    # Bias
    ddoi = bias.get("ddoi")
    if ddoi == "pos": s += 10
    if ddoi == "neg": s -= 10
    if bias.get("opex_week"): s += 5
    if bias.get("earnings_soon"): s -= 20

    # Options liquidity proxy
    if spread_ok: s += 5

    # Normalize to [0,100]
    s = max(0.0, min(100.0, s))
    return float(s)
