"""
Load .env for local/dev. On DigitalOcean, real env vars already exist and win.
Safe: if .env is missing, nothing breaks.
"""
from __future__ import annotations
from dotenv import load_dotenv, find_dotenv
load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=False)
