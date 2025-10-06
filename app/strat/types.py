import pandas as pd

def candle_types(df: pd.DataFrame) -> pd.Series:
    """
    Classify each bar as The Strat type:
      '1'  = inside bar
      '2u' = directional up (took out prior high only)
      '2d' = directional down (took out prior low only)
      '3'  = outside bar (took out both sides)
    """
    hi, lo = df["high"], df["low"]
    phi, plo = hi.shift(1), lo.shift(1)

    is_inside  = (hi <= phi) & (lo >= plo)
    is_outside = (hi >  phi) & (lo <  plo)
    is_2u      = (~is_inside & ~is_outside & (hi > phi))
    is_2d      = (~is_inside & ~is_outside & (lo < plo))

    s = pd.Series(index=df.index, dtype="object")
    s[is_inside]  = "1"
    s[is_outside] = "3"
    s[is_2u]      = "2u"
    s[is_2d]      = "2d"
    s = s.fillna("1")
    return s
