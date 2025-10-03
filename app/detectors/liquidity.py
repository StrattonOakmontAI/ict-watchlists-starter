import pandas as pd

def equal_highs_lows(df: pd.DataFrame, tol: float = 0.001) -> tuple[list[float], list[float]]:
    """
    Detect equal highs/lows (within tolerance) as simple liquidity pools.
    tol is fraction (0.001 = 0.1%)
    """
    eqh: list[float] = []
    eql: list[float] = []
    H, L = df["high"], df["low"]
    for i in range(1, len(df)):
        if H.iloc[i] and H.iloc[i - 1]:
            if abs(H.iloc[i] - H.iloc[i - 1]) / H.iloc[i] <= tol:
                eqh.append(float(max(H.iloc[i], H.iloc[i - 1])))
        if L.iloc[i] and L.iloc[i - 1]:
            if abs(L.iloc[i] - L.iloc[i - 1]) / L.iloc[i] <= tol:
                eql.append(float(min(L.iloc[i], L.iloc[i - 1])))
    # de-duplicate and sort
    return sorted(set(eqh)), sorted(set(eql))
