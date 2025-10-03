import pandas as pd

def order_blocks(df: pd.DataFrame, bos_list: list[dict]) -> list[dict]:
    """
    For each BOS, pick the last opposite-color candle body before the BOS bar as an OB zone.
    Returns dicts: {'dir','ts','low','high'}
    """
    res: list[dict] = []
    for b in bos_list:
        ts = b["ts"]
        i = df.index.get_loc(ts)
        j = max(0, i - 10)  # lookback window
        segment = df.iloc[j:i]
        if b["dir"] == "bull":
            down = segment[segment["close"] < segment["open"]]
            if not down.empty:
                c = down.iloc[-1]
                low = float(min(c["open"], c["close"]))
                high = float(max(c["open"], c["close"]))
                res.append({"dir": "bull", "ts": ts, "low": low, "high": high})
        else:
            up = segment[segment["close"] > segment["open"]]
            if not up.empty:
                c = up.iloc[-1]
                low = float(min(c["open"], c["close"]))
                high = float(max(c["open"], c["close"]))
                res.append({"dir": "bear", "ts": ts, "low": low, "high": high})
    return res
