import pandas as pd

def swings(df: pd.DataFrame, n: int = 3) -> tuple[list[pd.Timestamp], list[pd.Timestamp]]:
    """
    Return indices (timestamps) of swing highs and swing lows using a simple fractal rule.
    A swing-high at i if high[i] is the max of window i-n..i+n and higher than immediate neighbors.
    """
    highs: list[pd.Timestamp] = []
    lows: list[pd.Timestamp] = []
    H, L = df["high"], df["low"]
    length = len(df)
    if length == 0:
        return highs, lows
    for i in range(n, length - n):
        windowH = H.iloc[i - n : i + n + 1]
        windowL = L.iloc[i - n : i + n + 1]
        if H.iloc[i] == windowH.max() and H.iloc[i] > H.iloc[i - 1] and H.iloc[i] > H.iloc[i + 1]:
            highs.append(df.index[i])
        if L.iloc[i] == windowL.min() and L.iloc[i] < L.iloc[i - 1] and L.iloc[i] < L.iloc[i + 1]:
            lows.append(df.index[i])
    return highs, lows
