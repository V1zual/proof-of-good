"""Messages to volunteers and donors in Telegram. The bot sets `bot` at start-up; without it, messages are skipped."""
import logging

from . import config

log = logging.getLogger("pog.notify")
bot = None  # telegram.Bot, set by pog.bot


async def send(chat_id: int | None, text: str, photo: str | None = None) -> None:
    if not bot or not chat_id:
        return
    try:
        if photo:
            with open(config.UPLOAD_DIR / photo, "rb") as f:
                await bot.send_photo(chat_id, f, caption=text[:1024], parse_mode="HTML")
        else:
            await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        log.exception("telegram send to %s", chat_id)
