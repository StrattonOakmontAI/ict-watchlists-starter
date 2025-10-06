import pandas as pd
from .types import candle_types

def htf_bias(df: pd.DataFrame) -> str:
    """
    HTF bias from last closed bar:
      bull if last type is '2u' or (type '3' and close>open)
      bear if last type is '2d' or (type '3' and close<open)
      else 'flat'
    """
    if df is None or len(df) < 2:
        return "flat"
    typ = candle_types(df).iloc[-1]
    row = df.iloc[-1]
    if typ == "2u": return "bull"
    if typ == "2d": return "bear"
    if typ == "3":  return "bull" if row["close"] > row["open"] else "bear"
    return "flat"

def mtf_align(pattern_dir: str, bias_dir: str) -> bool:
    if pattern_dir not in ("bull","bear"): return False
    if bias_dir == "flat": return False
    return pattern_dir == bias_dir
