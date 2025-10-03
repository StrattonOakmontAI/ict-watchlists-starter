import math


def score(confluence: dict, bias: dict, atr: float, spread_ok: bool) -> float:
s = 0
s += 20 if confluence.get('bos') else 0
s += 20 if confluence.get('fvg') else 0
s += 20 if confluence.get('ob') else 0
s += 10 if confluence.get('eq_liq') else 0
# bias
s += 10 if bias.get('ddoi','') == 'pos' else 0
s -= 10 if bias.get('ddoi','') == 'neg' else 0
s += 5 if bias.get('opex_week') else 0
s -= 20 if bias.get('earnings_soon') else 0
# basic liquidity/vol fit
s += 5 if spread_ok else 0
# normalize
return float(max(0, min(100, s)))
