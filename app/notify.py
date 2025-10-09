import os, importlib
import pytest
import respx
from httpx import Response

@pytest.mark.asyncio
async def test_send_watchlist_success(monkeypatch):
    # Set env before import; reload module to pick up env
    url = "https://discord.com/api/webhooks/TEST/WL"
    monkeypatch.setenv("DISCORD_WEBHOOK_WATCHLIST", url)
    monkeypatch.delenv("DISCORD_WEBHOOK_ENTRIES", raising=False)
    notify = importlib.import_module("app.notify")
    importlib.reload(notify)

    with respx.mock(base_url="https://discord.com") as router:
        router.post("/api/webhooks/TEST/WL").mock(return_value=Response(204))
        await notify.send_watchlist("Title", ["line 1", "line 2"])

@pytest.mark.asyncio
async def test_send_entry_rate_limit_then_success(monkeypatch):
    wl = "https://discord.com/api/webhooks/TEST/WL"
    en = "https://discord.com/api/webhooks/TEST/EN"
    monkeypatch.setenv("DISCORD_WEBHOOK_WATCHLIST", wl)
    monkeypatch.setenv("DISCORD_WEBHOOK_ENTRIES", en)
    notify = importlib.import_module("app.notify")
    importlib.reload(notify)

    with respx.mock(base_url="https://discord.com") as router:
        # First 429 with Retry-After: 0; then success 204
        route = router.post("/api/webhooks/TEST/EN")
        route.side_effect = [
            Response(429, headers={"Retry-After": "0"}),
            Response(204),
        ]
        await notify.send_entry_detail(
            symbol="AAPL", direction="long", entry=1.0, stop=0.5,
            targets=[1.1, 1.2], score=90,
        )


# .github/workflows/ci.yml
name: ci
on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: |
          python -m pip install -U pip
          pip install -r requirements.txt
          pip install pytest pytest-asyncio respx
      - name: Compile sources
        run: python -m compileall -q app
      - name: Run tests
        run: pytest -q
