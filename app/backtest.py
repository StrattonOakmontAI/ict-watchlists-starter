# app/backtest.py
import os
import sys
import csv
import math
import asyncio
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.polygon_client import Polygon
from app.config import settings
from app.notify import send_watchlist  # we'll reuse this to post a summary embed
# journal.csv path is consistent with app.journal
JOURNAL_PATH = os.getenv("JOURNAL_PATH", "/mnt/data/journal.csv")

# Defaults (can override via CLI flags or env vars)
DEF_DAYS = int(os.getenv("BACKTEST_DAYS", "5"))              # trading days to look forward
DEF_TF_MIN = int(os.getenv("BACKTEST_TF_MIN", "5"))          # minute bar size (1 or 5)
DEF_LIMIT = int(os.getenv("BACKTEST_LIMIT", "50"))           # max trades to test
DEF_CONC = int(os.getenv("BACKTEST_CONCURRENCY", "5"))       # API concurrency

PT = settings.tz  # America/Los_Angeles


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
    kind: str = "entry-test"  # free text

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


def _parse_row(row: dict) -> Trade | None:
    """
    Parse a journal CSV row into a Trade.
    Required columns: timestamp_pt, symbol, direction, entry, stop, t1..t4
    """
    try:
        ts = datetime.strptime(row["timestamp_pt"], "%Y-%m-%d %H:%M:%S PT").replace(tzinfo=PT)
        sym = row["symbol"].strip().upper()
        direction = row.get("direction", "").strip().lower()
        entry = float(row["entry"]); stop = float(row["stop"])
        t1 = float(row["t1"]); t2 = float(row["t2"]); t3 = float(row["t3"]); t4 = float(row["t4"])
        kind = row.get("kind", "entry")
        return Trade(ts=ts, symbol=sym, direction=direction, entry=entry, stop=stop,
                     t1=t1, t2=t2, t3=t3, t4=t4, kind=kind)
    except Exception:
        return None


def load_trades(limit: int | None = None) -> list[Trade]:
    if not os.path.exists(JOURNAL_PATH):
        print(f"Journal not found at {JOURNAL_PATH}")
        return []
    rows: list[Trade] = []
    with open(JOURNAL_PATH, "r", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            t = _parse_row(r)
            if t and t.risk_R > 0:
                rows.append(t)
    rows.sort(key=lambda x: x.ts)  # oldest first
    return rows[-limit:] if limit else rows


async def fetch_bars(p: Polygon, sym: str, start_dt: datetime, days: int, tf_min: int) -> pd.DataFrame:
    """
    Fetch minute aggregates for [start_dt.date(), start_dt.date()+days]
    Returns tz-aware PT DataFrame indexed by datetime with columns: open, high, low, close, volume
    """
    # we fetch a little before and after
    frm = (start_dt - timedelta(days=1)).date().isoformat()
    to = (start_dt + timedelta(days=days+1)).date().isoformat()
    df = await p.aggs(sym, tf_min, "minute", frm, to)
    if df.empty:
        return df
    # make tz-aware & PT
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert(PT)
    return df


def simulate_outcome(tr: Trade, df: pd.DataFrame) -> dict:
    """
    Walk bars forward from trade timestamp until window end.
    Rules:
      - Stop at 'stop'
      - 50% off at T1, 25% at T2, 25% at T3; if T4 hit, we count it as extra 25% (replaces T3 share)
      - After T1 hits, move stop to breakeven (entry) for remaining size
      - If nothing hits by window end, mark-to-close of last bar (remaining size)
    Returns dict with realized_R, hit_seq, stop_hit, last_dt
    """
    if df.empty:
        return {"realized_R": 0.0, "hit_seq": [], "stop_hit": False, "last_dt": None}

    # Only consider bars at/after the trade timestamp
    df = df[df.index >= tr.ts]

    R = tr.risk_R
    if R <= 0:  # safety
        return {"realized_R": 0.0, "hit_seq": [], "stop_hit": False, "last_dt": None}

    # Position slices: 0.5 at T1, 0.25 at T2, 0.25 at T3/T4
    remain = 1.0
    realized_R = 0.0
    hit_seq: list[str] = []
    stop_level = tr.stop
    moved_to_be = False

    t_levels = [("T1", tr.t1, 0.5), ("T2", tr.t2, 0.25), ("T3", tr.t3, 0.25), ("T4", tr.t4, 0.25)]
    # If T4 hits we will consume the remaining 0.25; otherwise T3 can consume it.

    def profit_R(price: float) -> float:
        move = (price - tr.entry) if tr.is_long else (tr.entry - price)
        return move / R

    stop_hit = False
    t_hit = {name: False for (name, _, _) in t_levels}

    for dt, row in df.iterrows():
        hi = float(row["high"]); lo = float(row["low"]); cl = float(row["close"])

        # Check stop first (path dependency)
        if tr.is_long:
            if lo <= stop_level:
                # stopped on remaining size
                loss_R = profit_R(stop_level) * remain
                realized_R += loss_R
                stop_hit = True
                return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": True, "last_dt": dt}
        else:
            if hi >= stop_level:
                loss_R = profit_R(stop_level) * remain
                realized_R += loss_R
                stop_hit = True
                return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": True, "last_dt": dt}

        # Check targets in order; they may all hit in the same bar
        for i, (name, level, slice_wt) in enumerate(t_levels):
            if t_hit[name]:
                continue
            if tr.is_long and hi >= level:
                realized_R += profit_R(level) * slice_wt
                remain -= slice_wt
                t_hit[name] = True
                hit_seq.append(name)
                if name == "T1" and not moved_to_be:
                    stop_level = tr.entry
                    moved_to_be = True
            elif tr.is_short and lo <= level:
                realized_R += profit_R(level) * slice_wt
                remain -= slice_wt
                t_hit[name] = True
                hit_seq.append(name)
                if name == "T1" and not moved_to_be:
                    stop_level = tr.entry
                    moved_to_be = True

        # early exit if fully exited
        if remain <= 1e-6:
            return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": False, "last_dt": dt}

    # If we reach here: window ended, mark remaining at last close
    if remain > 0:
        last_close = float(df["close"].iloc[-1])
        realized_R += profit_R(last_close) * remain

    return {"realized_R": realized_R, "hit_seq": hit_seq, "stop_hit": False, "last_dt": df.index[-1]}


async def backtest_once(days: int, tf_min: int, limit: int) -> dict:
    trades = load_trades(limit=limit)
    if not trades:
        print("No trades found in journal.")
        return {"count": 0, "results": [], "summary": {}}

    p = Polygon()
    sem = asyncio.Semaphore(DEF_CONC)
    out = []

    async def worker(tr: Trade):
        async with sem:
            try:
                df = await fetch_bars(p, tr.symbol, tr.ts, days, tf_min)
                sim = simulate_outcome(tr, df)
                res = {
                    "symbol": tr.symbol,
                    "direction": tr.direction,
                    "ts": tr.ts.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
                    "entry": tr.entry,
                    "stop": tr.stop,
                    "R": tr.risk_R,
                    "realized_R": round(sim["realized_R"], 3),
                    "hit_seq": sim["hit_seq"],
                    "stopped": bool(sim["stop_hit"]),
                }
                out.append(res)
            except Exception as e:
                out.append({"symbol": tr.symbol, "error": str(e)})

    await asyncio.gather(*(worker(t) for t in trades))
    await p.close()

    # Summary
    rs = [r for r in out if "realized_R" in r]
    wins = [r for r in rs if r["realized_R"] > 0]
    losses = [r for r in rs if r["realized_R"] < 0]
    flats = [r for r in rs if abs(r["realized_R"]) < 1e-9]
    total = len(rs)
    avg_R = round(sum(r["realized_R"] for r in rs) / total, 3) if total else 0.0
    winrate = round(100 * len(wins) / total, 1) if total else 0.0
    exp_R = avg_R  # expectancy per trade in R units

    # crude max drawdown on cumulative R
    cum = []
    s = 0.0
    for r in rs:
        s += r["realized_R"]
        cum.append(s)
    peak = -1e9
    mdd = 0.0
    for v in cum:
        peak = max(peak, v)
        mdd = min(mdd, v - peak)
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
    return {"count": len(out), "results": out, "summary": summary}


async def post_summary_to_discord(summary: dict, days: int, tf_min: int, limit: int):
    hdr = f"Backtest – {summary.get('trades',0)} trades (tf {tf_min}m, {days}d window, cap {limit})"
    fields = [
        f"Win rate: {summary['winrate_pct']}%",
        f"Avg R / trade: {summary['avg_R']}",
        f"Expectancy (R): {summary['expectancy_R']}",
        f"Max drawdown (R): {summary['max_drawdown_R']}",
        f"W/L/F: {summary['wins']}/{summary['losses']}/{summary['flats']}",
        "Not financial advice",
    ]
    await send_watchlist(hdr, fields)


def _print_table(rows: list[dict]):
    if not rows:
        print("No rows.")
        return
    cols = ["ts","symbol","direction","entry","stop","R","realized_R","hit_seq","stopped"]
    print("\t".join(cols))
    for r in rows[:100]:  # avoid spam
        vals = [str(r.get(c,"")) if c!="hit_seq" else ",".join(r.get("hit_seq",[])) for c in cols]
        print("\t".join(vals))
    if len(rows) > 100:
        print(f"... ({len(rows)-100} more)")


def main():
    ap = argparse.ArgumentParser(description="Journal backtester (Polygon-based)")
    sub = ap.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Run backtest and print summary")
    run.add_argument("--days", type=int, default=DEF_DAYS, help="Forward test window in trading days (default: env BACKTEST_DAYS or 5)")
    run.add_argument("--tf", type=int, default=DEF_TF_MIN, help="Minutes per bar (1 or 5, default env BACKTEST_TF_MIN or 5)")
    run.add_argument("--limit", type=int, default=DEF_LIMIT, help="Max trades to test (default: env BACKTEST_LIMIT or 50)")
    run.add_argument("--post", action="store_true", help="Post summary to Discord")

    dry = sub.add_parser("dry", help="Print parsed trades (no API calls)")
    dry.add_argument("--limit", type=int, default=10, help="How many last trades to show")

    args = ap.parse_args()

    if args.cmd == "dry":
        trades = load_trades(limit=args.limit)
        print(f"Loaded {len(trades)} trades")
        for t in trades:
            print(t.ts.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"), t.symbol, t.direction, t.entry, t.stop, t.t1, t.t2, t.t3, t.t4)
        return

    if args.cmd == "run":
        # guard: ensure Polygon key is configured
        if not os.getenv("POLYGON_API_KEY","").strip():
            print("POLYGON_API_KEY missing; set it in DO env and redeploy.")
            sys.exit(2)
        res = asyncio.run(backtest_once(args.days, args.tf, args.limit))
        print("== Summary ==")
        for k,v in res["summary"].items():
            print(f"{k}: {v}")
        print("\n== Sample rows ==")
        _print_table(res["results"])
        if args.post:
            asyncio.run(post_summary_to_discord(res["summary"], args.days, args.tf, args.limit))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
