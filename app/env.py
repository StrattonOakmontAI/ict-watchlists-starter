from __future__ import annotations
# Load .env for local/dev only; on servers, real env vars win.
from dotenv import load_dotenv, find_dotenv
load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=False)
