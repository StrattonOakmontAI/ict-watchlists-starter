# Starter Repo – ICT Watchlists (No‑Code Friendly Bootstrap)

This starter lets a non‑developer get the **Discord delivery pipeline** running on **DigitalOcean App Platform**. It posts sample embeds to your two channels (👀watchlist, 🚨entries). Once live, your contractors can drop in the real detectors from the SPEC.

---

## 1) File Tree

```
repo/
  app/
    __init__.py
    cli.py
    notify.py
  requirements.txt
  Dockerfile
  README.md
```

---

## 2) README.md (copy into repo/README.md)

### What this does

* Provides two commands to send **test** messages to Discord using your webhooks.
* Deploys on **DigitalOcean App Platform** as a Worker with **Scheduled Jobs** (you’ll add schedules after testing).

### Prereqs

* Two Discord webhooks (👀watchlist and 🚨entries)
* DigitalOcean account

### Local quick test (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_WEBHOOK_WATCHLIST="https://discord.com/api/webhooks/..."
export DISCORD_WEBHOOK_ENTRIES="https://discord.com/api/webhooks/..."
python -m app.cli test-watchlist
python -m app.cli test-entry
```

If both messages arrive in your channels, you’re ready to deploy.

### Deploy to DigitalOcean App Platform

1. Push this folder to a new **GitHub repo**.
2. In DigitalOcean → **Apps → Create App** → Connect to your GitHub repo.
3. Component = **Worker**. Build command: *(leave default)*. Run command: `python -m app.cli run-once`.
4. **Environment Variables** (Add):

   * `DISCORD_WEBHOOK_WATCHLIST = <your watchlist webhook>`
   * `DISCORD_WEBHOOK_ENTRIES = <your entries webhook>`
   * `TZ = America/Los_Angeles`
5. Click **Deploy** → verify logs show “ready”.
6. Click **Console → Run Command** and test:

   * `python -m app.cli test-watchlist`
   * `python -m app.cli test-entry`
7. Add **Scheduled Jobs** (you can rename later):

   * Weekly (Sun 16:00 UTC) → `python -m app.cli weekly`
   * Pre‑market (13:00 or 14:00 UTC depending on DST) → `python -m app.cli premarket`
   * Evening (00:30 or 01:30 UTC) → `python -m app.cli evening`

> When you’re ready for the full MVP, replace the CLI stubs with the real jobs from the SPEC (same command names).

---

## 3) requirements.txt

```
httpx==0.27.2
pytz==2024.1
APScheduler==3.10.4
python-dotenv==1.0.1
rich==13.8.1
```

---

## 4) Dockerfile

```
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["python","-m","app.cli","run-once"]
```

---

## 5) app/**init**.py

```
__all__ = []
```

---

## 6) app/notify.py

```
import os, json, asyncio
import httpx
from rich import print

WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST")
EN = os.getenv("DISCORD_WEBHOOK_ENTRIES") or WL

async def _post(webhook: str, payload: dict):
    async with httpx.AsyncClient(timeout=20) as x:
        r = await x.post(webhook, json=payload)
        r.raise_for_status()
        print("[green]Sent[/]")

async def send_watchlist(title: str, items: list[str]):
    embed = {
        "title": title,
        "description": "Starter watchlist message (replace with real data during MVP)",
        "fields": [{"name": f"{i+1}.", "value": v} for i, v in enumerate(items)],
        "footer": {"text": "Not financial advice"}
    }
    await _post(WL, {"username": "ICT Watchlists 👀", "embeds": [embed]})

async def send_entry(symbol: str):
    embed = {
        "title": f"ENTRY – {symbol} (demo)",
        "fields": [
            {"name": "Entry/Stop", "value": "123.45 / 122.90 (1R=0.55)"},
            {"name": "Targets", "value": "T1 124.00 | T2 124.55 | T3 125.10 | T4 125.65"},
            {"name": "Confluence", "value": "BOS + FVG + OB (demo)"}
        ],
        "footer": {"text": "Scale: 50/25/15/10 at T1–T4"}
    }
    await _post(EN, {"username": "ICT Entries 🚨", "embeds": [embed]})
```

---

## 7) app/cli.py

```
import asyncio, argparse
from datetime import datetime
import pytz
from app.notify import send_watchlist, send_entry

PT = pytz.timezone("America/Los_Angeles")

def now_pt():
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S %Z")

async def weekly():
    await send_watchlist(f"Weekly Watchlist (Sun 08:00 PT) – {now_pt()}", ["AAPL 15m Long – demo","MSFT 5m Short – demo"])

async def premarket():
    await send_watchlist(f"Pre‑Market Watchlist (06:00 PT) – {now_pt()}", ["SPY – demo","TSLA – demo"])

async def evening():
    await send_watchlist(f"Evening Watchlist (17:30 PT) – {now_pt()}", ["NVDA – demo","AMZN – demo"])

async def test_watchlist():
    await premarket()

async def test_entry():
    await send_entry("AAPL")

async def run_once():
    print("Container up; use DigitalOcean Console → Run Command to invoke jobs.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?", default="run-once",
                   choices=["run-once","weekly","premarket","evening","test-watchlist","test-entry"])
    args = p.parse_args()
    asyncio.run(globals()[args.cmd.replace('-', '_')]())
```

---

## 8) DigitalOcean signup + GitHub connect (click-by-click)

### A) Create a GitHub repo (no coding, just copy/paste)

1. Go to **github.com → Sign up** (if you don’t have one).
2. Click **New repository** → name it `ict-watchlists-starter` → **Public** → **Create repository**.
3. Add files via the web:

   * Click **Add file → Create new file**
   * **Path**: `requirements.txt` → paste the content from the canvas → **Commit**.
   * Repeat for **Dockerfile**.
   * Click **Add file → Create new file** → **Path**: `app/notify.py` → paste → **Commit**.
   * Repeat for `app/cli.py` and `app/__init__.py`.
   * Finally add **README.md** (from the canvas) and **Commit**.

> Tip: To make folders in GitHub web, type the folder name like `app/notify.py` in the filename box.

### B) Create a DigitalOcean account and link GitHub

1. Go to **digitalocean.com → Sign up** (choose Starter plan; you can upgrade later).
2. In the top nav, click **Apps** → **Create App**.
3. Choose **GitHub** and authorize DigitalOcean to access your repo. Select `ict-watchlists-starter` and **Next**.
4. Component type: **Worker** (not Web Service).
5. **Environment Variables** → **Add**:

   * `DISCORD_WEBHOOK_WATCHLIST = <paste your 👀watchlist webhook>`
   * `DISCORD_WEBHOOK_ENTRIES = <paste your 🚨entries webhook>`
   * `TZ = America/Los_Angeles`
6. Leave the run command as default for now (`python -m app.cli run-once` from Dockerfile).
7. Click **Deploy**. Wait until status is **Active**.
8. Test from the App page → **Console → Run Command**:

   * `python -m app.cli test-watchlist` → check 👀watchlist
   * `python -m app.cli test-entry` → check 🚨entries

### C) Add the schedules (automation)

1. App → **Settings → Scheduled Jobs → Add Job**

   * **Weekly**: Command `python -m app.cli weekly`, UTC time **16:00 Sun**
   * **Pre‑market**: `python -m app.cli premarket`, UTC **13:00 or 14:00** (DST shifts)
   * **Evening**: `python -m app.cli evening`, UTC **00:30 or 01:30** (DST shifts)

> These send **demo** messages on your schedule. When contractors add the real logic, the commands stay the same.

## 9) Security note – rotate your webhook

Because a webhook URL was shared in chat earlier, **create new Discord webhooks** and use those in DigitalOcean. Delete/disable the old ones in Discord → Channel → **Integrations**.

## 10) Do I need a Traderlink account?

**No for the MVP.** The design uses **Polygon.io** for market/option data. You only need:

* Discord (you have it)
* DigitalOcean (for hosting)
* **Polygon.io** (for real data once the MVP logic is added)

When you’re ready to add real data:

1. Sign up at Polygon.io and get your **API key**.
2. In DigitalOcean App → **Settings → Environment Variables** add `POLYGON_API_KEY = <your key>`.
3. Contractors will switch the demo jobs to use the Polygon API.

## 11) What’s Next

* Once tests post to Discord, your pipeline is working. Share the **SPEC** and this starter repo with your contractor.
* They will replace the demo code with the ICT logic, options/DDOI, Plotly charts, and Postgres per the SPEC — no platform changes for you.
