"""Starts the website (and the Telegram bot inside it)."""
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import uvicorn  # noqa: E402

from pog import config  # noqa: E402

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run("pog.web:app", host="0.0.0.0", port=config.PORT, log_level="info")
