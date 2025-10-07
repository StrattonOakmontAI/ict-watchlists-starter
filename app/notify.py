# app/notify.py
# Discord webhook helpers for watchlists and entry alerts (env-read + strip + fallback).

from __future__ import annotations
import os
import httpx

# Read once as defaults, but strip; we also strip again at call time.
WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "").strip()
EN = (os.getenv("DISCORD_WEBHOOK_ENTRIES", "") or WL).strip()


async def _post(webhook: str, payload: dict) -> None:
    webhook = (webhook or "").strip()  # <- strip every time
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
            # Fallback to WL if available (avoid losing alerts)
            wl = os.getenv("DISCORD_WEBHOOK_WATCHLIST", WL).strip()
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


# ------------------------- 👀 Watchlist -------------------------

async def send_watchlist(title: str, items: list[str]) -> None:
    fields = [{"name": f"{i+1}.", "value": v, "inline": False} for i, v in enumerate(items)]
    embed = {"title": title, "fields": fields, "footer": {"text": "Not financial advice"}}
    wl = os.getenv("DISCORD_WEBHOOK_WATCHLIST", WL).strip()
    await _post(wl, {"username": "ICT Watchlists 👀", "embeds": [embed]})


# ------------------------- 🚨 Entries (detailed) -------------------------

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

    # Earnings Read / GEX
    er_dir = bias.get("er_dir")
    er_conf = bias.get("er_conf")
    if er_dir:
        gpeak = ""
        if bias.get("gex_peak_strike") is not None and bias.get("gex_peak_side"):
            gpeak = f" @ {int(round(bias['gex_peak_strike']))}{bias['gex_peak_side'][0].upper()}"
        fields.insert(1, {"name": "Earnings Read", "value": f"{er_dir} {int(round(100*(er_conf or 0)))}%{gpeak}"})

    # Option line + Projection
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

    en = (os.getenv("DISCORD_WEBHOOK_ENTRIES", EN) or os.getenv("DISCORD_WEBHOOK_WATCHLIST", WL)).strip()
    await _post(en, {"username": "ICT Entries 🚨", "embeds": [embed]})


# ------------------------- Diagnostics -------------------------

def webhooks_diag() -> dict:
    wl_env = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "")
    en_env = os.getenv("DISCORD_WEBHOOK_ENTRIES", "")
    def tail(u: str) -> str: return "" if not u else u[-40:]
    eff = (en_env or EN).strip()
    return {
        "WL_env_tail": tail(wl_env),
        "EN_env_tail": tail(en_env),
        "WL_mod_tail": tail(WL),
        "EN_mod_tail": tail(EN),
        "EN_starts_http": (en_env or EN).startswith("http"),
        "EN_has_space": any(c.isspace() for c in (en_env or EN)),
        "EN_effective_tail": tail(eff),
        "EN_effective_has_space": any(c.isspace() for c in eff),
    }
