import pandas as pd


def bos(df: pd.DataFrame, swing_highs, swing_lows, atr_mult: float = 0.5):
# returns list of dicts: {ts, dir, ref, displacement}
out = []
# simple ATR proxy
atr = (df['high']-df['low']).ewm(span=14, adjust=False).mean()
last_dir = None
last_sw_hi = swing_highs[0] if swing_highs else None
last_sw_lo = swing_lows[0] if swing_lows else None
for ts, row in df.iterrows():
idx = df.index.get_loc(ts)
disp_up = last_sw_hi and row['close'] > df.loc[last_sw_hi,'high'] and (row['close']-df.loc[last_sw_hi,'high']) > atr.iloc[idx]*atr_mult
disp_dn = last_sw_lo and row['close'] < df.loc[last_sw_lo,'low'] and (df.loc[last_sw_lo,'low']-row['close']) > atr.iloc[idx]*atr_mult
if disp_up:
out.append({"ts": ts, "dir":"bull", "ref": last_sw_hi, "displacement": float(row['close']-df.loc[last_sw_hi,'high'])})
last_dir = "bull"
if disp_dn:
out.append({"ts": ts, "dir":"bear", "ref": last_sw_lo, "displacement": float(df.loc[last_sw_lo,'low']-row['close'])})
last_dir = "bear"
# update last swings as they occur
if ts in swing_highs: last_sw_hi = ts
if ts in swing_lows: last_sw_lo = ts
return out
