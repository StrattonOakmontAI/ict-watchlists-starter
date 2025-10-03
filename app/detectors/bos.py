import pandas as pd

def bos(
    df: pd.DataFrame,
    swing_highs: list[pd.Timestamp],
    swing_lows: list[pd.Timestamp],
    atr_mult: float = 0.5,
) -> list[dict]:
    """
    Detect simple Break of Structure (BOS) with displacement vs last swing.
    Returns dicts: {'ts', 'dir', 'ref', 'displacement'}
    """
    out: list[dict] = []
    if df.empty:
        return out
    atr_like = (df["high"] - df["low"]).ewm(span=14, adjust=False).mean()
    last_sw_hi = swing_highs[0] if swing_highs else None
    last_sw_lo = swing_lows[0] if swing_lows else None

    for ts, row in df.iterrows():
        idx = df.index.get_loc(ts)

        disp_up = False
        if last_sw_hi is not None:
            ref_hi = df.loc[last_sw_hi, "high"]
            disp_up = (row["close"] > ref_hi) and ((row["close"] - ref_hi) > atr_like.iloc[idx] * atr_mult)

        disp_dn = False
        if last_sw_lo is not None:
            ref_lo = df.loc[last_sw_lo, "low"]
            disp_dn = (row["close"] < ref_lo) and ((ref_lo - row["close"]) > atr_like.iloc[idx] * atr_mult)

        if disp_up:
            out.append({"ts": ts, "dir": "bull", "ref": last_sw_hi, "displacement": float(row["close"] - ref_hi)})
        if disp_dn:
            out.append({"ts": ts, "dir": "bear", "ref": last_sw_lo, "displacement": float(ref_lo - row["close"])})

        # update references when a new swing is reached
        if last_sw_hi is None or (ts in swing_highs):
            last_sw_hi = ts if ts in swing_highs else last_sw_hi
        if last_sw_lo is None or (ts in swing_lows):
            last_sw_lo = ts if ts in swing_lows else last_sw_lo

    return out
