import importlib
import os

import pytest
import respx
from httpx import Response

@pytest.mark.asyncio
async def test_send_watchlist_204(monkeypatch):
    url = "https://discord.com/api/webhooks/TEST/WL"
    monkeypatch.setenv("DISCORD_WEBHOOK_WATCHLIST", url)
    monkeypatch.delenv("DISCORD_WEBHOOK_ENTRIES", raising=False)

    notify = importlib.import_module("app.notify")
    importlib.reload(notify)

    with respx.mock(base_url="https://discord.com") as router:
        router.post("/api/webhooks/TEST/WL").mock(return_value=Response(204))
        await notify.send_watchlist("Title", ["line 1", "line 2"])

@pytest.mark.asyncio
async def test_send_entry_429_then_204(monkeypatch):
    wl = "https://discord.com/api/webhooks/TEST/WL"
    en = "https://discord.com/api/webhooks/TEST/EN"
    monkeypatch.setenv("DISCORD_WEBHOOK_WATCHLIST", wl)
    monkeypatch.setenv("DISCORD_WEBHOOK_ENTRIES", en)

    notify = importlib.import_module("app.notify")
    importlib.reload(notify)

    with respx.mock(base_url="https://discord.com") as router:
        route = router.post("/api/webhooks/TEST/EN")
        route.side_effect = [
            Response(429, headers={"Retry-After": "0"}),
            Response(204),
        ]
        await notify.send_entry_detail(
            symbol="AAPL", direction="long", entry=1.0, stop=0.5,
            targets=[1.1, 1.2], score=90,
        )
