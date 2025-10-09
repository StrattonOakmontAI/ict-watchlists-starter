from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

@dataclass(frozen=True)
class Trade:
    symbol: str
    direction: str  # "long" or "short"
    entry: float
    stop: float
    targets: Sequence[float]

@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float

def _validate_trade(t: Trade) -> None:
    if t.entry <= 0 or t.stop <= 0:
        raise ValueError("entry/stop must be > 0")
    if t.direction not in ("long", "short"):
        raise ValueError("direction must be 'long' or 'short'")
    if not t.targets:
        raise ValueError("at least one target is required")

def _hit(level: float, c: Candle, *, is_long: bool) -> bool:
    # Why: conservative execution — require intrabar touch.
    return (c.low <= level <= c.high) if is_long else (c.low <= level <= c.high)

def run_backtest(
    trades: Iterable[Trade],
    candles: Iterable[Candle],
) -> List[Tuple[Trade, str, Optional[float]]]:
    """
    Extremely simple placeholder backtest:
    - Fills at entry on first candle that touches entry.
    - If stop touched before any target → 'stopped'.
    - Else first touched target → 'target', return that price.
    This is ONLY a stub to keep the project runnable.
    """
    results: List[Tuple[Trade, str, Optional[float]]] = []
    cds = list(candles)

    for t in trades:
        _validate_trade(t)
        is_long = t.direction == "long"

        filled_idx: Optional[int] = None
        for i, c in enumerate(cds):
            if _hit(t.entry, c, is_long=is_long):
                filled_idx = i
                break

        if filled_idx is None:
            results.append((t, "no-fill", None))
            continue

        # After fill, walk forward for stop/targets
        hit_level: Optional[float] = None
        status = "no-out"
        ordered_targets = list(t.targets) if is_long else list(t.targets)
        for c in cds[filled_idx:]:
            # stop first
            if _hit(t.stop, c, is_long=is_long):
                status = "stopped"
                hit_level = t.stop
                break
            # then earliest target
            for target in ordered_targets:
                if _hit(target, c, is_long=is_long):
                    status = "target"
                    hit_level = target
                    break
            if status == "target":
                break

        results.append((t, status, hit_level))
    return results
