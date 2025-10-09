# file: app/env.py
# Why: load .env in local/dev; on DigitalOcean real env vars already exist and win.
from __future__ import annotations
from dotenv import load_dotenv, find_dotenv

load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=False)
