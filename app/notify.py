# app/notify.py
# Discord webhook helpers for watchlists and entry alerts (env-read at call time)

import os
import httpx
import json

# Keep initial values as defaults; we'll read env at call time too.
WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "")
EN = os.getenv("DISCORD_WEBHOOK_ENTRIES", "") or WL


async def _post(webhook: str, payload: dict) -> None:
    """
    Post JSON to a Discord webhook. If the primary webhook fails (4xx/5xx) and
    a watchlist webhook is available, we fall back to WL to avoid losing alerts.
    """
    if not webhook:
        print("No webhook configured; skipping post")
        return
    async with httpx.AsyncClient(timeout=20) as x:
        r = await x.post(webhook, json=payload)
        try:
            r.raise_for_status()
            print("Sent")
        except httpx.HTTPStatusError as e:
            print("Primary webhook failed:", e)
            wl = os.getenv("DISCORD_WEBHOOK_WATCHLIST", WL)
            if webhook != wl and wl:
                r2 = await x.post(
                    wl,
                    json={
                        "username": payload.get("username", "ICT Bot"),
                        "content": "Entries webhook failed – posting to watchlist as fallback.",
                        "embeds": payload.get("embeds", []),
                    },
                )
                r2.raise_for_status()
                print("Sent (fallback)")
            else:
                raise


# --- Watchlist (text-only) -------------------------------------------------

async def send_watchlist(title: str, items: list[str]) -> None:
    """
    Post a clean watchlist embed (no placeholder text), reading WL from env now.
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
    wl = os.getenv("DISCORD_WEBHOOK_WATCHLIST", WL)
    await _post(wl, {"username": "ICT Watchlists 👀", "embeds": [embed]})


# --- Real entry alert (text-only) with Option & Projection ------------------

async def send_entry_detail(
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    targets: list[float],
    score: float,
    bias: dict | None = None,
    option: dict | None = None,
    proj_move_pct: float | None = None,
) -> None:
    """
    Detailed entry alert for 🚨entries. Reads EN from env at call time so updates
    take effect without code changes. Includes optional option line + projection.
    """
    bias = bias or {}
    r_val = abs(float(entry) - float(stop))
    t1, t2, t3, t4 = (targets + [None, None, None, None])[:4]
    bias_line = (
        f"DDOI {str(bias.get('ddoi','?')).upper()} • "
        f"OPEX {'Yes' if bias.get('opex_week') else 'No'} • "
        f"Earnings {'Soon' if bias.get('earnings_soon') else 'No'}"
    )

    fields = [
        {"name": "Entry / Stop / 1R", "value": f"{entry:.2f} / {stop:.2f} / {r_val:.2f}"},
        {"name": "Targets (T1–T4)", "value": f"{t1:.2f} | {t2:.2f} | {t3:.2f} | {t4:.2f}"},
        {"name": "Score", "value": f"{int(score)}"},
        {"name": "Bias", "value": bias_line},
    ]

    if option:
        opt_txt = (
            f"{option.get('type','?')} Δ{option.get('delta','?')} "
            f"{option.get('expiry','?')} {option.get('strike','?')} @ {option.get('premium','?')} "
            f"• ROI {option.get('roi_pct','?')}% • DTE {option.get('dte','?')} • Spread {option.get('spread','?')}"
        )
        fields.insert(1, {"name": "Option", "value": opt_txt})
    if proj_move_pct is not None:
        fields.insert(2, {"name": "Projection", "value": f"{proj_move_pct:.1f}%"})

    embed = {
        "title": f"ENTRY – {symbol} ({direction.upper()})",
        "fields": fields,
        "footer": {"text": "Scale: 50/25/15/10 at T1–T4 • Not financial advice"},
    }

    # Read EN at call time (falls back to WL if EN not set)
    en = os.getenv("DISCORD_WEBHOOK_ENTRIES", EN) or os.getenv("DISCORD_WEBHOOK_WATCHLIST", WL)
    await _post(en, {"username": "ICT Entries 🚨", "embeds": [embed]})


# --- Diagnostics ------------------------------------------------------------

def webhooks_diag() -> dict:
    """
    Return tails and flags so we can print in a one-liner from the console.
    """
    wl_env = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "")
    en_env = os.getenv("DISCORD_WEBHOOK_ENTRIES", "")
    def tail(u: str) -> str:
        return "" if not u else u[-40:]
    return {
        "WL_env_tail": tail(wl_env),
        "EN_env_tail": tail(en_env),
        "WL_mod_tail": tail(WL),
        "EN_mod_tail": tail(EN),
        "EN_starts_http": (en_env or EN).startswith("http"),
        "EN_has_space": any(c.isspace() for c in (en_env or EN)),
    }
