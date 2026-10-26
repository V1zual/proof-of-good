"""Settings. Each secret comes from an environment variable (hosting) or a local .secrets/*.txt file (dev PC)."""
import os
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The second folder is the shared secrets folder one level up on the dev PC (the Gemini key lives there).
SECRET_DIRS = [ROOT / ".secrets", ROOT.parent / ".secrets"]

PAYPAL_API = os.environ.get("PAYPAL_API", "https://api-m.sandbox.paypal.com")
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
# 3.5 Flash answers in a few seconds; the newest Flash took over a minute on the free tier (25.10.2026).
GEMINI_MODELS = os.environ.get("GEMINI_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite").split(",")
NBU_API = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"

DATA_DIR = Path(os.environ.get("POG_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "pog.db"
UPLOAD_DIR = DATA_DIR / "uploads"
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
PORT = int(os.environ.get("PORT", "8000"))

# A receipt may differ from the planned tranche amount by this share (prices change, exchange rates move).
AMOUNT_TOLERANCE = float(os.environ.get("AMOUNT_TOLERANCE", "0.15"))
# Perceptual-hash distance under which two photos count as the same picture (reused proof).
PHASH_SAME = int(os.environ.get("PHASH_SAME", "6"))
# Demo deadline: a campaign with no verified proof this many minutes after its first donation is refunded.
DEMO_REFUND_MINUTES = float(os.environ.get("DEMO_REFUND_MINUTES", "0"))

_FILES = {
    "PAYPAL_CLIENT_ID": "paypal_client_id.txt",
    "PAYPAL_CLIENT_SECRET": "paypal_client_secret.txt",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token.txt",
    "GEMINI_API_KEY": "gemini_key.txt",
}


@cache
def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    for folder in SECRET_DIRS:
        if value:
            break
        path = folder / _FILES[name]
        if path.exists():
            value = path.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise RuntimeError(f"Missing secret {name}: set the env var or put it into .secrets/{_FILES[name]}")
    return value
