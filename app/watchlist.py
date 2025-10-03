import asyncio


entry=None; stop=None; zones=[]; direction=None
if long_bias:
# pick last bull FVG or OB
cand = None
bull_zones = [z for z in fvg_list if z['dir']=='bull'] + [z for z in ob_list if z['dir']=='bull']
if bull_zones:
cand = bull_zones[-1]
if cand:
entry = (cand['low']+cand['high'])/2
stop = cand['low']
direction='long'
zones.append({'low':cand['low'],'high':cand['high']})
elif short_bias:
bear_zones = [z for z in fvg_list if z['dir']=='bear'] + [z for z in ob_list if z['dir']=='bear']
cand = bear_zones[-1] if bear_zones else None
if cand:
entry = (cand['low']+cand['high'])/2
stop = cand['high']
direction='short'
zones.append({'low':cand['low'],'high':cand['high']})


if not entry or not stop or not direction:
return None


# options/chain snapshot → DDOI + basic liquidity check
chain = await p.options_chain_snapshot(sym)
ddoi = ddoi_from_chain(chain)
bias = {
'opex_week': is_opex_week(datetime.utcnow().date()),
'earnings_soon': False, # earnings integration stubbed for MVP
'ddoi': 'pos' if ddoi.get('net_delta',0) > 0 else ('neg' if ddoi.get('net_delta',0) < 0 else 'flat')
}
# spread proxy: require at least some options present
spread_ok = bool(chain.get('results') or chain.get('options'))


conf = {
'bos': bool(bos_list),
'fvg': any(True for z in fvg_list),
'ob' : any(True for z in ob_list),
'eq_liq': bool(eqh or eql)
}


sc = score(conf, bias, float((df['high']-df['low']).tail(14).mean()), spread_ok)
if sc < settings.min_score:
return None


liq = sorted(set(eqh+eql))
targets = _targets_from_R(entry, stop, liq)


return {
'symbol': sym,
'direction': direction,
'entry': round(entry,2),
'stop': round(stop,2),
'targets': targets,
'score': sc,
'zones': zones,
'bias': bias
}


async def generate(kind: str) -> list[dict]:
syms = load_universe()
p = Polygon()
try:
tasks = [analyze_symbol(p, s) for s in syms]
rows = [r for r in await asyncio.gather(*tasks) if r]
rows.sort(key=lambda x: x['score'], reverse=True)
return rows
finally:
await p.close()


async def post_watchlist(kind: str):
rows = await generate(kind)
if not rows:
await send_watchlist(f"{kind.title()} – No Setups (min score {settings.min_score})", [])
return
fields = [f"{r['symbol']} {r['direction'].upper()} – Entry {r['entry']} | Stop {r['stop']} | T1 {r['targets'][0]} | Score {int(r['score'])}" for r in rows[:20]]
await send_watchlist(f"{kind.title()} Watchlist – {datetime.now().strftime('%Y-%m-%d %H:%M PT')}", fields)
# also send individual entry alerts (first 5 to keep noise low)
for r in rows[:5]:
t1,t2,t3,t4 = r['targets']
# NOTE: For MVP we don't render PNG to Spaces to simplify. Add charts later.
await send_entry(r['symbol'])
