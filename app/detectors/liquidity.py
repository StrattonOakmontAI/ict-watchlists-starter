import pandas as pd


def equal_highs_lows(df: pd.DataFrame, tol: float = 0.001):
# tolerance in fractional price (0.1%)
eqh, eql = [], []
H, L = df['high'], df['low']
for i in range(2, len(df)):
if abs(H.iloc[i]-H.iloc[i-1])/H.iloc[i] <= tol:
eqh.append(float(max(H.iloc[i], H.iloc[i-1])))
if abs(L.iloc[i]-L.iloc[i-1])/L.iloc[i] <= tol:
eql.append(float(min(L.iloc[i], L.iloc[i-1])))
return sorted(set(eqh)), sorted(set(eql))
