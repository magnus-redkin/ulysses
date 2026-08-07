# app/services/telegram_bot.py

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

BOT_TOKEN = settings.BOT_TOKEN
ADMIN_IDS = [int(x) for x in settings.ADMIN_IDS.split(",") if x.strip()] if settings.ADMIN_IDS else []

async def send_telegram_message(tg_id: int, text: str) -> bool:
    """Отправить сообщение пользователю через Telegram Bot API."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": tg_id,
                    "text": text,
                    "parse_mode": "HTML"
                }
            )
            if resp.status_code == 200:
                logger.info(f"Message sent to {tg_id}")
                return True
            else:
                logger.error(f"Telegram API error: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return False

async def send_admin_alert(text: str) -> bool:
    """Отправить алерт всем админам."""
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty, alert not sent")
        return False
    results = []
    for admin_id in ADMIN_IDS:
        result = await send_telegram_message(tg_id=admin_id, text=f"🚨 {text}")
        results.append(result)
    return any(results)
