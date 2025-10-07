# app/backtest.py
# Minimal, robust journal backtester (Polygon-based)
# - Reads /mnt/data/journal.csv
# - Simulates entries with T1/T2/T3/T4, stop-first, move to BE after T1
# - Produces R-based stats and can post a summary to Discord

import os
import sys
import csv
import asyncio
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from app.polygon_client import Polygon
from app.config import settings
from app.notify import send_watchlist  # reuse for summary post

JOURNAL_PATH = os.getenv("JOURNAL_PATH", "/mnt/data/journal.csv")

# Defaults (override via env or CLI)
DEF_DAYS = int(os.getenv("BACKTEST_DAYS", "5"))           # forward window in trading days
DEF_TF_MIN = int(os.getenv("BACKTEST_TF_MIN", "5"))       # 1 or 5 minute bars
DEF_LIMIT = int(os.getenv("BACKTEST_LIMIT", "50"))        # max trades to test
DEF_CONC = int(os.getenv("BACKTEST_CONCURRENCY", "5"))    # API concurrency

PT = settings.tz  # America/Los_Angeles tzinfo


@dataclass
class Trade:
    ts: datetime
    symbol: str
    direction: str
    entry: float
    stop: float
    t1: float
    t2: float
    t3: float
    t4: float
    kind: str = "entry"

    @property
    def risk_R(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def is_long(self) -> bool:
        d = (self.direction or "").lower()
        return d in ("long", "bull", "bullish", "buy")

    @property
    def is_short(self) -> bool:
        return not self.is_long


# --- replace the existing _parse_row with this tolerant version ---
def _parse_row(row: dict) -> Trade | None:
    """
    Tolerant CSV row parser:
      - Accepts header aliases: timestamp_pt|timestamp|time, direction|dir,
        t1|T1, etc.
      - Accepts timestamps in:
          "YYYY-MM-DD HH:MM:SS PT"
          "YYYY-MM-DD HH:MM PT"
          ISO-like: "YYYY-MM-DDTHH:MM[:SS][.sss]Z" or with -07:00 offset
    """
    def pick(*names, default=None):
        for n in names:
            if n in row and row[n] not in (None, ""):
                return row[n]
        return default

    ts_raw = (pick("timestamp_pt", "timestamp", "time") or "").strip()
    sym    = (pick("symbol", "ticker") or "").strip().upper()
    direction = (pick("direction", "dir") or "").strip().lower()
    entry  = pick("entry")
    stop   = pick("stop")
    t1     = pick("t1", "T1")
    t2     = pick("t2", "T2")
    t3     = pick("t3", "T3")
    t4     = pick("t4", "T4")
    kind   = (pick("kind", "type", default="entry") or "entry").strip()

    # required fields present?
    need = [ts_raw, sym, direction, entry, stop, t1, t2, t3, t4]
    if any(v in (None, "") for v in need):
        return None

    # parse numbers
    try:
        entry = float(entry); stop = float(stop)
        t1 = float(t1); t2 = float(t2); t3 = float(t3); t4 = float(t4)
    except Exception:
        return None

    # parse timestamp with a few fallback formats
    from datetime import timezone
    PT = settings.tz
    ts = None
    fmts = [
        "%Y-%m-%d %H:%M:%S PT",
        "%Y-%m-%d %H:%M PT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]
    s = ts_raw.replace("  ", " ").strip()
    for fmt in fmts:
        try:
            if fmt.endswith("PT"):
                # assign PT tzinfo explicitly
                dt = datetime.strptime(s, fmt)
                ts = dt.replace(tzinfo=PT)
            else:
                dt = datetime.strptime(s, fmt)
                # if parsed as naive, assume PT; if offset aware, convert to PT
                ts = dt if dt.tzinfo else dt.replace(tzinfo=PT)
                if ts.tzinfo != PT:
                    ts = ts.astimezone(PT)
            break
        except Exception:
            continue
    if ts is None:
        # last resort: try simple date only
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            ts = dt.replace(hour=6, minute=30, tzinfo=PT)  # 6:30a PT as a default
        except Exception:
            return None

    tr = Trade(ts=ts, symbol=sym, direction=direction, entry=entry, stop=stop,
               t1=t1, t2=t2, t3=t3, t4=t4, kind=kind)
    return tr if tr.risk_R > 0 else None
# --- end replacement ---



def load_trades(limit: int | None = None) -> list[Trade]:
    if not os.path.exists(JOURNAL_PATH):
        print(f"Journal not found at {JOURNAL_PATH}")
        return []
    trades: list[Trade] = []
    with open(JOURNAL_PATH, "r", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            t = _parse_row(r)
            if t:
                trades.append(t)
    trades.sort(key=lambda x: x.ts)  # oldest first
    return trades[-limit:] if limit else trades


async def fetch_bars(p: Polygon, sym: str, start_dt: datetime, days: int, tf_min: int) -> pd.DataFrame:
    """Fetch minute aggregates spanning the forward window."""
    frm = (start_dt - timedelta(days=1)).date().isoformat()
    to = (start_dt + timedelta(days=days + 1)).date().isoformat()
    df = await p.aggs(sym, tf_min, "minute", frm, to)
    if df.empty:
        return df
    # Make tz-aware & convert to PT
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert(PT)
    # Only consider bars at/after trade time
    df = df[df.index >= start_dt]
    return df


def simulate_outcome(tr: Trade, df: pd.DataFrame) -> dict:
    """
    Simulate execution:
      - Stop checked first each bar
      - 50% @ T1, 25% @ T2, and 25% allocated to either T3 or T4 (whichever hits first)
      - Move stop to breakeven after T1 for remaining size
      - If window ends, mark remaining at last close
    Returns: dict(realized_R, hit_seq, stop_hit, last_dt)
    """
    if df.empty:
        return {"realized_R": 0.0, "hit_seq": [], "stop_hit": False, "last_dt": None}

    R = tr.risk_R
    remain = 1.0
    realized_R = 0.0
    hit_seq: list[str] = []
    stop_level = tr.stop
    moved_to_be = False
    t3_or_t4_left = 0.25
    t3_t4_done = False

    def profit_R(price: float) -> float:
        mv = (price - tr.entry) if tr.is_long else (tr.entry - price)
        return mv / R if R > 0 else 0.0

    stop_hit = False

    for dt, row in df.iterrows():
        hi = float(row["high"]); lo = float(row["low"]); cl = float(row["close"])

        # 1) Stop first
        if tr.is_long:
            if lo <= stop_level:
                realized_R += profit_R(stop_level) * remain
                return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": True, "last_dt": dt}
        else:
            if hi >= stop_level:
                realized_R += profit_R(stop_level) * remain
                return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": True, "last_dt": dt}

        # 2) Targets in order: T1, T2, then either T3 or T4
        # T1 (0.5)
        if remain > 0 and (
            (tr.is_long and hi >= tr.t1) or
            (tr.is_short and lo <= tr.t1)
        ):
            realized_R += profit_R(tr.t1) * 0.5
            remain -= 0.5
            hit_seq.append("T1")
            if not moved_to_be:
                stop_level = tr.entry
                moved_to_be = True

        # T2 (0.25)
        if remain > 0 and (
            (tr.is_long and hi >= tr.t2) or
            (tr.is_short and lo <= tr.t2)
        ):
            realized_R += profit_R(tr.t2) * 0.25
            remain -= 0.25
            hit_seq.append("T2")

        # T3 or T4 (consume remaining 0.25 at first to hit)
        if (not t3_t4_done) and t3_or_t4_left > 0 and remain > 0:
            hit_t3 = (tr.is_long and hi >= tr.t3) or (tr.is_short and lo <= tr.t3)
            hit_t4 = (tr.is_long and hi >= tr.t4) or (tr.is_short and lo <= tr.t4)
            if hit_t3 or hit_t4:
                lvl = tr.t4 if (hit_t4 and (not hit_t3)) else tr.t3
                realized_R += profit_R(lvl) * t3_or_t4_left
                remain -= t3_or_t4_left
                hit_seq.append("T4" if lvl == tr.t4 else "T3")
                t3_or_t4_left = 0.0
                t3_t4_done = True

        # 3) Exit early if fully out
        if remain <= 1e-6:
            return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": False, "last_dt": dt}

    # 4) Window ended → mark remaining at last close
    if remain > 0:
        last_close = float(df["close"].iloc[-1])
        realized_R += profit_R(last_close) * remain

    return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": False, "last_dt": df.index[-1]}


async def backtest_once(days: int, tf_min: int, limit: int) -> dict:
    trades = load_trades(limit=limit)
    if not trades:
        return {"count": 0, "results": [], "summary": {"trades": 0}}

    p = Polygon()
    sem = asyncio.Semaphore(DEF_CONC)
    results: list[dict] = []

    async def worker(tr: Trade):
        async with sem:
            try:
                df = await fetch_bars(p, tr.symbol, tr.ts, days, tf_min)
                sim = simulate_outcome(tr, df)
                results.append({
                    "ts": tr.ts.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
                    "symbol": tr.symbol,
                    "direction": tr.direction,
                    "entry": tr.entry,
                    "stop": tr.stop,
                    "R": tr.risk_R,
                    "realized_R": round(sim["realized_R"], 3),
                    "hit_seq": sim["hit_seq"],
                    "stopped": bool(sim["stop_hit"]),
                })
            except Exception as e:
                results.append({"symbol": tr.symbol, "error": str(e)})

    await asyncio.gather(*(worker(t) for t in trades))
    await p.close()

    rs = [r for r in results if "realized_R" in r]
    total = len(rs)
    if total == 0:
        summary = {"trades": 0}
        return {"count": len(results), "results": results, "summary": summary}

    wins = [r for r in rs if r["realized_R"] > 0]
    losses = [r for r in rs if r["realized_R"] < 0]
    flats = [r for r in rs if abs(r["realized_R"]) < 1e-9]
    avg_R = round(sum(r["realized_R"] for r in rs) / total, 3)
    winrate = round(100 * len(wins) / total, 1)

    # Max drawdown on cumulative R
    peak = 0.0
    mdd = 0.0
    s = 0.0
    for r in rs:
        s += r["realized_R"]
        peak = max(peak, s)
        mdd = min(mdd, s - peak)
    mdd = round(mdd, 3)

    summary = {
        "trades": total,
        "winrate_pct": winrate,
        "avg_R": avg_R,
        "expectancy_R": avg_R,
        "max_drawdown_R": mdd,
        "wins": len(wins),
        "losses": len(losses),
        "flats": len(flats),
    }
    return {"count": len(results), "results": results, "summary": summary}


async def post_summary_to_discord(summary: dict, days: int, tf_min: int, limit: int):
    trades = summary.get("trades", 0)
    hdr = f"Backtest – {trades} trades (tf {tf_min}m, {days}d window, cap {limit})"
    if trades == 0:
        await send_watchlist(hdr, ["No trades found in journal.", "Not financial advice"])
        return
    fields = [
        f"Win rate: {summary.get('winrate_pct', 0)}%",
        f"Avg R / trade: {summary.get('avg_R', 0)}",
        f"Expectancy (R): {summary.get('expectancy_R', 0)}",
        f"Max drawdown (R): {summary.get('max_drawdown_R', 0)}",
        f"W/L/F: {summary.get('wins',0)}/{summary.get('losses',0)}/{summary.get('flats',0)}",
        "Not financial advice",
    ]
    await send_watchlist(hdr, fields)


def _print_table(rows: list[dict]):
    if not rows:
        print("No rows.")
        return
    cols = ["ts", "symbol", "direction", "entry", "stop", "R", "realized_R", "hit_seq", "stopped"]
    print("\t".join(cols))
    for r in rows[:100]:
        vals = []
        for c in cols:
            if c == "hit_seq":
                vals.append(",".join(r.get("hit_seq", [])))
            else:
                vals.append(str(r.get(c, "")))
        print("\t".join(vals))
    if len(rows) > 100:
        print(f"... ({len(rows) - 100} more)")


def main():
    ap = argparse.ArgumentParser(description="Journal backtester (Polygon-based)")
    sub = ap.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Run backtest and print summary")
    run.add_argument("--days", type=int, default=DEF_DAYS, help="Forward test window in trading days")
    run.add_argument("--tf", type=int, default=DEF_TF_MIN, help="Minutes per bar (1 or 5)")
    run.add_argument("--limit", type=int, default=DEF_LIMIT, help="Max trades to test")
    run.add_argument("--post", action="store_true", help="Post summary to Discord")

    dry = sub.add_parser("dry", help="Print parsed trades (no API calls)")
    dry.add_argument("--limit", type=int, default=10, help="How many last trades to show")

    args = ap.parse_args()

    if args.cmd == "dry":
        trades = load_trades(limit=args.limit)
        print(f"Loaded {len(trades)} trades")
        for t in trades:
            print(t.ts.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
                  t.symbol, t.direction, t.entry, t.stop, t.t1, t.t2, t.t3, t.t4)
        return

    if args.cmd == "run":
        if not os.getenv("POLYGON_API_KEY", "").strip():
            print("POLYGON_API_KEY missing; set it in DO env and redeploy.")
            sys.exit(2)
        res = asyncio.run(backtest_once(args.days, args.tf, args.limit))
        print("== Summary ==")
        for k, v in res["summary"].items():
            print(f"{k}: {v}")
        print("\n== Sample rows ==")
        _print_table(res["results"])
        if args.post:
            asyncio.run(post_summary_to_discord(res["summary"], args.days, args.tf, args.limit))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
