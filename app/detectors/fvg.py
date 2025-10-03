import pandas as pd

def fvgs(df: pd.DataFrame, atr_mult: float = 0.1) -> list[dict]:
    """
    Find 3-candle Fair Value Gaps.
    Bullish: low[i] > high[i-2] with minimum gap vs ATR-like.
    Bearish: high[i] < low[i-2] with minimum gap vs ATR-like.
    """
    res: list[dict] = []
    if len(df) < 3:
        return res
    atr_like = (df["high"] - df["low"]).ewm(span=14, adjust=False).mean()
    for i in range(2, len(df)):
        # bullish FVG
        if df["low"].iloc[i] > df["high"].iloc[i - 2]:
            gap = df["low"].iloc[i] - df["high"].iloc[i - 2]
            if gap >= atr_like.iloc[i] * atr_mult:
                res.append({
                    "dir": "bull",
                    "ts": df.index[i],
                    "low": float(df["high"].iloc[i - 2]),
                    "high": float(df["low"].iloc[i]),
                })
        # bearish FVG
        if df["high"].iloc[i] < df["low"].iloc[i - 2]:
            gap = df["low"].iloc[i - 2] - df["high"].iloc[i]
            if gap >= atr_like.iloc[i] * atr_mult:
                res.append({
                    "dir": "bear",
                    "ts": df.index[i],
                    "low": float(df["high"].iloc[i]),
                    "high": float(df["low"].iloc[i - 2]),
                })
    return res
