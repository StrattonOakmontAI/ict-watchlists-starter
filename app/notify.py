# app/notify.py
# Discord webhook helpers for watchlists and entry alerts.

import os
import httpx

WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "")
EN = os.getenv("DISCORD_WEBHOOK_ENTRIES", "") or WL


async def _post(webhook: str, payload: dict) -> None:
    if not webhook:
        print("No webhook configured; skipping post")
        return
    async with httpx.AsyncClient(timeout=20) as x:
        r = await x.post(webhook, json=payload)
        r.raise_for_status()
        print("Sent")


async def send_watchlist(title: str, items: list[str]) -> None:
    """
    Post a clean watchlist embed (no placeholder text).
    """
    fields = [
        {"name": f"{i+1}.", "value": v, "inline": False}
        for i, v in enumerate(items)
    ]
    embed = {
        "title": title,
        "fields": fields,
        "footer": {"text": "Not financial advice"},
    }
    await _post(WL, {"username": "ICT Watchlists 👀", "embeds": [embed]})


# --- Real entry alert with entry/stop/T1–T4 ------------------------------

async def send_entry_detail(
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    targets: list[float],
    score: float,
    bias: dict | None = None,
) -> None:
    """
    Post a detailed entry alert to the 🚨entries webhook with entry/stop/T1–T4.
    """
    bias = bias or {}
    r_val = abs(float(entry) - float(stop))
    t1, t2, t3, t4 = (targets + [None, None, None, None])[:4]
    bias_line = (
        f"DDOI {str(bias.get('ddoi','?')).upper()} • "
        f"OPEX {'Yes' if bias.get('opex_week') else 'No'} • "
        f"Earnings {'Soon' if bias.get('earnings_soon') else 'No'}"
    )
    embed = {
        "title": f"ENTRY – {symbol} ({direction.upper()})",
        "fields": [
            {"name": "Entry / Stop / 1R", "value": f"{entry:.2f} / {stop:.2f} / {r_val:.2f}"},
            {"name": "Targets (T1–T4)", "value": f"{t1:.2f} | {t2:.2f} | {t3:.2f} | {t4:.2f}"},
            {"name": "Score", "value": f"{int(score)}"},
            {"name": "Bias", "value": bias_line},
        ],
        "footer": {"text": "Scale: 50/25/15/10 at T1–T4 • Not financial advice"},
    }
    await _post(EN, {"username": "ICT Entries 🚨", "embeds": [embed]})


# --- Keep the simple demo call for backward compatibility ----------------

async def send_entry(symbol: str) -> None:
    embed = {
        "title": f"ENTRY – {symbol} (demo)",
        "fields": [
            {"name": "Entry/Stop", "value": "123.45 / 122.90 (1R=0.55)"},
            {"name": "Targets", "value": "T1 124.00 | T2 124.55 | T3 125.10 | T4 125.65"},
            {"name": "Confluence", "value": "BOS + FVG + OB (demo)"},
        ],
        "footer": {"text": "Scale: 50/25/15/10 at T1–T4"},
    }
    await _post(EN, {"username": "ICT Entries 🚨", "embeds": [embed]})
