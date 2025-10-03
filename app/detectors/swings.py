import pandas as pd


def swings(df: pd.DataFrame, n: int = 3):
# returns indices of swing highs/lows
highs, lows = [], []
H, L = df["high"], df["low"]
for i in range(n, len(df)-n):
if H.iloc[i] == H.iloc[i-n:i+n+1].max() and H.iloc[i] > H.iloc[i-1] and H.iloc[i] > H.iloc[i+1]:
highs.append(df.index[i])
if L.iloc[i] == L.iloc[i-n:i+n+1].min() and L.iloc[i] < L.iloc[i-1] and L.iloc[i] < L.iloc[i+1]:
lows.append(df.index[i])
return highs, lows
