from __future__ import annotations
import logging
import os

def setup_logging() -> None:
    """Configure root logging once with timestamps & levels."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s %(levelname)s %(name)s - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S %Z"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)
