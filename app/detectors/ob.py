import pandas as pd


def order_blocks(df: pd.DataFrame, bos_list: list[dict]):
# last opposite candle body before each BOS
res = []
for b in bos_list:
ts = b['ts']
i = df.index.get_loc(ts)
if b['dir'] == 'bull':
# find last down candle before BOS
j = max(0, i-10)
segment = df.iloc[j:i]
down = segment[segment['close'] < segment['open']]
if not down.empty:
c = down.iloc[-1]
res.append({'dir':'bull','ts':ts,'low':float(min(c['open'],c['close'])),'high':float(max(c['open'],c['close']))})
else:
j = max(0, i-10)
segment = df.iloc[j:i]
up = segment[segment['close'] > segment['open']]
if not up.empty:
c = up.iloc[-1]
res.append({'dir':'bear','ts':ts,'low':float(min(c['open'],c['close'])),'high':float(max(c['open'],c['close']))})
return res
