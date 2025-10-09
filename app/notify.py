from __future__ import annotations
import os, asyncio
from typing import Any, Dict, List, Optional
import httpx

WL = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "").strip()
EN = (os.getenv("DISCORD_WEBHOOK_ENTRIES", "") or WL).strip()
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

async def _post(webhook: str, payload: Dict[str, Any]) -> None:
    webhook = (webhook or "").strip()
    if not webhook:
        print("notify: no webhook configured; skipping")  # Why: friendly first-run behavior
        return
    async with httpx.AsyncClient(timeout=_TIMEOUT) as x:
        while True:
            r = await x.post(webhook, json=payload)
            if r.status_code == 204:
                return
            if r.status_code == 429:  # Why: respect rate limits
                retry_after = float(r.headers.get("Retry-After", "1"))
                await asyncio.sleep(retry_after)
                continue
            r.raise_for_status()

def _lines_to_embed(title: str, lines: List[str]) -> Dict[str, Any]:
    desc = "\n".join(line for line in lines if line)
    return {"embeds": [{"title": title, "description": desc, "type": "rich"}]}

async def send_watchlist(title: str, lines: List[str], webhook: Optional[str] = None) -> None:
    payload = {"username": "ICT Watchlist", **_lines_to_embed(title, lines)}
    await _post(webhook or WL, payload)

async def send_entry_detail(
    *, symbol: str, direction: str, entry: float, stop: float,
    targets: List[float], score: float, bias: Dict[str, Any] | None = None,
    option: Dict[str, Any] | None = None, proj_move_pct: float | None = None,
    webhook: Optional[str] = None,
) -> None:
    fields: List[Dict[str, Any]] = [
        {"name": "Symbol", "value": symbol, "inline": True},
        {"name": "Direction", "value": direction.upper(), "inline": True},
        {"name": "Entry / Stop", "value": f"{entry} / {stop}", "inline": True},
        {"name": "Targets", "value": " / ".join(str(t) for t in targets[:4]) or "n/a", "inline": False},
        {"name": "Score", "value": str(int(round(score))), "inline": True},
    ]
    if proj_move_pct is not None:
        fields.append({"name": "Projected Move", "value": f"{proj_move_pct}%", "inline": True})
    if bias:
        fields.append({"name": "Bias", "value": ", ".join(f"{k}:{v}" for k, v in bias.items()) or "n/a", "inline": False})
    if option:
        opt_txt = ", ".join(f"{k}:{v}" for k, v in option.items())
        fields.append({"name": "Option", "value": opt_txt or "n/a", "inline": False})

    payload = {
        "username": "ICT Entry 🚨",
        "embeds": [{
            "title": f"{symbol} {direction.upper()}",
            "type": "rich",
            "fields": fields,
            "footer": {"text": "Not financial advice"},
        }],
    }
    await _post(webhook or EN, payload)

def env_diagnostics() -> Dict[str, Any]:
    wl_env = os.getenv("DISCORD_WEBHOOK_WATCHLIST", "")
    en_env = os.getenv("DISCORD_WEBHOOK_ENTRIES", "")
    def tail(u: str) -> str: return "" if not u else u[-40:]
    eff_en = (en_env or EN).strip()
    return {
        "WL_env_tail": tail(wl_env),
        "EN_env_tail": tail(en_env),
        "WL_default_tail": tail(WL),
        "EN_default_tail": tail(EN),
        "EN_effective_tail": tail(eff_en),
        "EN_effective_has_space": any(c.isspace() for c in eff_en),
    }
