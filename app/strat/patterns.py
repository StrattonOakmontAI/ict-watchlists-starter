import pandas as pd
from .types import candle_types

# Map of 2-bar and 3-bar combos to (name, direction)
# Direction: 'bull', 'bear', or 'neutral'
PAT2 = {
    ("2d","2u"): ("2-2 Reversal Up", "bull"),
    ("2u","2d"): ("2-2 Reversal Down", "bear"),
    ("2u","2u"): ("2-2 Continuation Up", "bull"),
    ("2d","2d"): ("2-2 Continuation Down", "bear"),
    ("1","2u"):  ("1-2 Upside Break", "bull"),
    ("1","2d"):  ("1-2 Downside Break", "bear"),
    ("3","2u"):  ("3-2 Upside", "bull"),
    ("3","2d"):  ("3-2 Downside", "bear"),
}

PAT3 = {
    ("2d","1","2u"): ("2-1-2 Up", "bull"),
    ("2u","1","2d"): ("2-1-2 Down", "bear"),
    ("1","1","2u"):  ("1-1-2 Up", "bull"),
    ("1","1","2d"):  ("1-1-2 Down", "bear"),
    ("3","1","2u"):  ("3-1-2 Up", "bull"),
    ("3","1","2d"):  ("3-1-2 Down", "bear"),
    # Optional: outside continuations
    ("3","2u","2u"): ("3-2-2 Up", "bull"),
    ("3","2d","2d"): ("3-2-2 Down", "bear"),
}

def detect_strat(df: pd.DataFrame) -> dict | None:
    """
    Return the most recent Strat pattern on the LAST CLOSED bar:
    { 'name': str, 'dir': 'bull'|'bear', 'types': ['2d','1','2u'] }
    """
    if len(df) < 3:  # need at least 3 bars to scan all patterns
        return None
    t = candle_types(df).tolist()

    # Use last 3 first, then last 2
    last3 = tuple(t[-3:])
    if last3 in PAT3:
        name, d = PAT3[last3]
        return {"name": name, "dir": d, "types": list(last3)}

    last2 = tuple(t[-2:])
    if last2 in PAT2:
        name, d = PAT2[last2]
        return {"name": name, "dir": d, "types": list(last2)}

    return None
