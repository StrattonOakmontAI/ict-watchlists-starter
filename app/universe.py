# app/universe.py
# Loads your custom ticker list if present; otherwise falls back to a safe default.
from pathlib import Path

DEFAULT_UNIVERSE = [
    "SPY","QQQ","IWM",
    "AAPL","MSFT","NVDA","AMZN","META","TSLA","GOOGL",
    "AMD","NFLX","BA","JPM","INTC"
]

def load_universe() -> list[str]:
    """
    Return a list of tickers (uppercase, de-duplicated, order preserved).
    If app/data/universe/Heatseeker_WL.txt exists, use that; else use DEFAULT_UNIVERSE.
    Lines starting with '#' are ignored as comments.
    """
    p = Path("app/data/universe/Heatseeker_WL.txt")
    if p.exists():
        lines = p.read_text(encoding="utf-8").splitlines()
        raw = [
            s.strip().upper()
            for s in lines
            if s.strip() and not s.strip().startswith("#")
        ]
        seen = set()
        out: list[str] = []
        for s in raw:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out
    return DEFAULT_UNIVERSE
