import pandas as pd


def fvgs(df: pd.DataFrame, atr_mult: float = 0.1):
res = []
atr = (df['high']-df['low']).ewm(span=14, adjust=False).mean()
idxs = list(range(len(df)))
for i in idxs[2:]:
# bullish
if df['low'].iloc[i] > df['high'].iloc[i-2]:
gap = df['low'].iloc[i] - df['high'].iloc[i-2]
if gap >= atr.iloc[i]*atr_mult:
res.append({
'dir':'bull',
'ts': df.index[i],
'low': float(df['high'].iloc[i-2]),
'high': float(df['low'].iloc[i])
})
# bearish
if df['high'].iloc[i] < df['low'].iloc[i-2]:
gap = df['low'].iloc[i-2] - df['high'].iloc[i]
if gap >= atr.iloc[i]*atr_mult:
res.append({
'dir':'bear',
'ts': df.index[i],
'low': float(df['high'].iloc[i]),
'high': float(df['low'].iloc[i-2])
})
return res
