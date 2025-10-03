import math


def ddoi_from_chain(chain_json: dict) -> dict:
# very lightweight proxy using sum(gamma * OI) and sum(delta * OI)
# expects polygon options chain snapshot payload
results = chain_json.get('results', []) or chain_json.get('options', []) or []
gex = 0.0
ndelta = 0.0
for opt in results:
greeks = opt.get('greeks') or {}
oi = opt.get('open_interest') or 0
gamma = greeks.get('gamma') or 0
delta = greeks.get('delta') or 0
# calls positive, puts negative sign on delta as proxy
sym = (opt.get('details') or {}).get('contract_type','') or opt.get('contract_type','')
sgn = 1 if sym.upper().startswith('C') else -1
gex += (gamma or 0) * (oi or 0) * sgn
ndelta += (delta or 0) * (oi or 0) * sgn
return {"net_gex": gex, "net_delta": ndelta}
