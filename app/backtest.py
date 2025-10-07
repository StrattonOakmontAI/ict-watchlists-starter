
code = r"""import os
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
DEF_DAYS = int(os.getenv("BACKTEST_DAYS", "5"))
DEF_TF_MIN = int(os.getenv("BACKTEST_TF_MIN", "5"))
DEF_LIMIT = int(os.getenv("BACKTEST_LIMIT", "50"))
DEF_CONC = int(os.getenv("BACKTEST_CONCURRENCY", "5"))

PT = settings.tz  # America/Los_Angeles tzinfo


def ensure_journal_local() -> bool:
    if os.path.exists(JOURNAL_PATH):
        return True
    repo = os.getenv('GH_REPO')
    tok  = os.getenv('GH_TOKEN')
    br   = os.getenv('GH_BRANCH', 'main')
    pth  = os.getenv('GH_PATH', 'journal/journal.csv')
    if not (repo and tok):
        return False
    try:
        import httpx, base64, pathlib
        url = f"https://api.github.com/repos/{repo}/contents/{pth}"
        hdr = {'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json'}
        r = httpx.get(url, headers=hdr, params={'ref': br}, timeout=20)
        r.raise_for_status()
        data = base64.b64decode(r.json()['content'])
        pathlib.Path(os.path.dirname(JOURNAL_PATH)).mkdir(parents=True, exist_ok=True)
        with open(JOURNAL_PATH, 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


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


def _parse_row(row: dict):
    n = { (k or "").strip().lower(): (v or "").strip() for k,v in row.items() }
    def pick(*names, default=None):
        for nm in names:
            if nm in n and n[nm] != "": return n[nm]
        return default
    ts_raw = pick("timestamp_pt","timestamp","time")
    sym    = (pick("symbol","ticker") or "").upper()
    direction = pick("direction","dir") or ""
    entry  = pick("entry"); stop = pick("stop")
    t1 = pick("t1","T1"); t2 = pick("t2","T2"); t3 = pick("t3","T3"); t4 = pick("t4","T4")
    kind = pick("kind","type", default="entry") or "entry"
    if not all([ts_raw,sym,direction,entry,stop,t1,t2,t3,t4]): return None
    try:
        entry=float(entry); stop=float(stop); t1=float(t1); t2=float(t2); t3=float(t3); t4=float(t4)
    except Exception:
        return None
    s = ts_raw.replace("  "," ").strip()
    ts = None
    fmts = ["%Y-%m-%d %H:%M:%S PT","%Y-%m-%d %H:%M PT","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M%z","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt.endswith("PT"):
                ts = dt.replace(tzinfo=PT)
            else:
                ts = dt if dt.tzinfo else dt.replace(tzinfo=PT)
                if ts.tzinfo != PT: ts = ts.astimezone(PT)
            break
        except Exception:
            pass
    if ts is None:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            ts = dt.replace(hour=6, minute=30, tzinfo=PT)
        except Exception:
            return None
    R = abs(entry - stop)
    if R <= 0: return None
    return Trade(ts=ts,symbol=sym,direction=direction,entry=entry,stop=stop,t1=t1,t2=t2,t3=t3,t4=t4,kind=kind)


def load_trades(limit=None):
    if not os.path.exists(JOURNAL_PATH):
        ensure_journal_local()
    if not os.path.exists(JOURNAL_PATH):
        print(f"Journal not found at {JOURNAL_PATH}")
        return []
    trades=[]
    with open(JOURNAL_PATH,"r",newline="") as f:
        rdr=csv.DictReader(f)
        for r in rdr:
            t=_parse_row(r)
            if t: trades.append(t)
    trades.sort(key=lambda x: x.ts)
    return trades[-limit:] if limit else trades


async def fetch_bars(p: Polygon, sym: str, start_dt: datetime, days: int, tf_min: int) -> pd.DataFrame:
    frm = (start_dt - timedelta(days=1)).date().isoformat()
    to  = (start_dt + timedelta(days=days + 1)).date().isoformat()
    df = await p.aggs(sym, tf_min, "minute", frm, to)
    if df.empty: return df
    if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    df = df.tz_convert(PT)
    df = df[df.index >= start_dt]
    return df


def simulate_outcome(tr: Trade, df: pd.DataFrame) -> dict:
    if df.empty:
        return {"realized_R":0.0,"hit_seq":[],"stop_hit":False,"last_dt":None}
    R = tr.risk_R
    remain = 1.0
    realized_R = 0.0
    hit_seq=[]
    stop_level = tr.stop
    moved_to_be=False
    t3_t4_left=0.25
    t3_t4_done=False
    def profit_R(price: float) -> float:
        mv = (price - tr.entry) if tr.is_long else (tr.entry - price)
        return mv / R if R>0 else 0.0
    for dt,row in df.iterrows():
        hi=float(row["high"]); lo=float(row["low"])
        # stop first
        if tr.is_long:
            if lo <= stop_level:
                realized_R += profit_R(stop_level)*remain
                return {"realized_R":realized_R,"hit_seq":hit_seq,"stop_hit":True,"last_dt":dt}
        else:
            if hi >= stop_level:
                realized_R += profit_R(stop_level)*remain
                return {"realized_R":realized_R,"hit_seq":hit_seq,"stop_hit":True,"last_dt":dt}
        # T1 (0.5)
        if remain>0 and ((tr.is_long and hi>=tr.t1) or (tr.is_short and lo<=tr.t1)):
            realized_R += profit_R(tr.t1)*0.5
            remain -= 0.5
            hit_seq.append("T1")
            if not moved_to_be:
                stop_level = tr.entry
                moved_to_be=True
        # T2 (0.25)
        if remain>0 and ((tr.is_long and hi>=tr.t2) or (tr.is_short and lo<=tr.t2)):
            realized_R += profit_R(tr.t2)*0.25
            remain -= 0.25
            hit_seq.append("T2")
        # T3 or T4 (0.25 first hit)
        if (not t3_t4_done) and t3_t4_left>0 and remain>0:
            hit_t3 = (tr.is_long and hi>=tr.t3) or (tr.is_short and lo<=tr.t3)
            hit_t4 = (tr.is_long and hi>=tr.t4) or (tr.is_short and lo<=tr.t4)
            if hit_t3 or hit_t4:
                lvl = tr.t4 if (hit_t4 and not hit_t3) else tr.t3
                realized_R += profit_R(lvl)*t3_t4_left
                remain -= t3_t4_left
                hit_seq.append("T4" if lvl==tr.t4 else "T3")
                t3_t4_left=0.0
                t3_t4_done=True
        if remain<=1e-6:
            return {"realized_R":realized_R,"hit_seq":hit_seq,"stop_hit":False,"last_dt":dt}
    last_close=float(df["close"].iloc[-1])
    realized_R += profit_R(last_close)*remain
    return {"realized_R":realized_R,"hit_seq":hit_seq,"stop_hit":False,"last_dt":df.index[-1]}


async def backtest_once(days:int, tf_min:int, limit:int)->dict:
    trades=load_trades(limit=limit)
    if not trades:
        return {"count":0,"results":[],"summary":{"trades":0}}
    p=Polygon()
    sem=asyncio.Semaphore(DEF_CONC)
    results=[]
    async def worker(tr:Trade):
        async with sem:
            try:
                df=await fetch_bars(p,tr.symbol,tr.ts,days,tf_min)
                sim=simulate_outcome(tr,df)
                results.append({
                    "ts": tr.ts.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"),
                    "symbol": tr.symbol,
                    "direction": tr.direction,
                    "entry": tr.entry,
                    "stop": tr.stop,
                    "R": tr.risk_R,
                    "realized_R": round(sim["realized_R"],3),
                    "hit_seq": sim["hit_seq"],
                    "stopped": bool(sim["stop_hit"]),
                })
            except Exception as e:
                results.append({"symbol":tr.symbol,"error":str(e)})
    await asyncio.gather(*(worker(t) for t in trades))
    await p.close()
    rs=[r for r in results if "realized_R" in r]
    total=len(rs)
    if total==0:
        return {"count":len(results),"results":results,"summary":{"trades":0}}
    wins=[r for r in rs if r["realized_R"]>0]
    losses=[r for r in rs if r["realized_R"]<0]
    flats=[r for r in rs if abs(r["realized_R"])<1e-9]
    avg_R=round(sum(r["realized_R"] for r in rs)/total,3)
    winrate=round(100*len(wins)/total,1)
    peak=0.0; mdd=0.0; s=0.0
    for r in rs:
        s+=r["realized_R"]; peak=max(peak,s); mdd=min(mdd, s-peak)
    mdd=round(mdd,3)
    summary={"trades":total,"winrate_pct":winrate,"avg_R":avg_R,"expectancy_R":avg_R,"max_drawdown_R":mdd,
             "wins":len(wins),"losses":len(losses),"flats":len(flats)}
    return {"count":len(results),"results":results,"summary":summary}


async def post_summary_to_discord(summary:dict, days:int, tf_min:int, limit:int):
    trades=summary.get("trades",0)
    hdr=f"Backtest – {trades} trades (tf {tf_min}m, {days}d window, cap {limit})"
    if trades==0:
        await send_watchlist(hdr,["No trades found in journal.","Not financial advice"]); return
    fields=[
        f"Win rate: {summary.get('winrate_pct',0)}%",
        f"Avg R / trade: {summary.get('avg_R',0)}",
        f"Expectancy (R): {summary.get('expectancy_R',0)}",
        f"Max drawdown (R): {summary.get('max_drawdown_R',0)}",
        f"W/L/F: {summary.get('wins',0)}/{summary.get('losses',0)}/{summary.get('flats',0)}",
        "Not financial advice",
    ]
    await send_watchlist(hdr, fields)


def _print_table(rows:list[dict]):
    if not rows: print("No rows."); return
    cols=["ts","symbol","direction","entry","stop","R","realized_R","hit_seq","stopped"]
    print("\t".join(cols))
    for r in rows[:100]:
        vals=[]
        for c in cols:
            if c=="hit_seq": vals.append(",".join(r.get("hit_seq",[])))
            else: vals.append(str(r.get(c,"")))
        print("\t".join(vals))
    if len(rows)>100: print(f"... ({len(rows)-100} more)")


def main():
    ap=argparse.ArgumentParser(description="Journal backtester (Polygon-based)")
    sub=ap.add_subparsers(dest="cmd")
    run=sub.add_parser("run", help="Run backtest and print summary")
    run.add_argument("--days", type=int, default=DEF_DAYS)
    run.add_argument("--tf", type=int, default=DEF_TF_MIN)
    run.add_argument("--limit", type=int, default=DEF_LIMIT)
    run.add_argument("--post", action="store_true")
    dry=sub.add_parser("dry", help="Print parsed trades (no API calls)")
    dry.add_argument("--limit", type=int, default=10)
    args=ap.parse_args()

    if args.cmd=="dry":
        trades=load_trades(limit=args.limit)
        print(f"Loaded {len(trades)} trades")
        for t in trades:
            print(t.ts.astimezone(PT).strftime("%Y-%m-%d %H:%M PT"), t.symbol, t.direction, t.entry, t.stop, t.t1, t.t2, t.t3, t.t4)
        return

    if args.cmd=="run":
        if not os.getenv("POLYGON_API_KEY","").strip():
            print("POLYGON_API_KEY missing; set it in DO env and redeploy."); sys.exit(2)
        res=asyncio.run(backtest_once(args.days, args.tf, args.limit))
        print("== Summary ==")
        for k,v in res["summary"].items(): print(f"{k}: {v}")
        print("\n== Sample rows =="); _print_table(res["results"])
        if args.post: asyncio.run(post_summary_to_discord(res["summary"], args.days, args.tf, args.limit))
        return

    ap.print_help()


if __name__=="__main__":
    main()
"""
open("app/backtest.py","w").write(code)
print("wrote app/backtest.py")
PY
