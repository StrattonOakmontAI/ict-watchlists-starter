python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_WEBHOOK_WATCHLIST="https://discord.com/api/webhooks/..."
export DISCORD_WEBHOOK_ENTRIES="https://discord.com/api/webhooks/..."
python -m app.cli test-watchlist
python -m app.cli test-entry
