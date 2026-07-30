import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [int(x) for x in os.getenv("TG_ADMIN", "").split(",") if x.strip()]

async def send_telegram_message(tg_id: int, text: str) -> bool:
    """Отправить сообщение пользователю через Telegram Bot API."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return False

    try:
        import httpx
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
    results = []
    for admin_id in ADMIN_IDS:
        result = await send_telegram_message(tg_id=admin_id, text=f"🚨 {text}")
        results.append(result)
    return any(results)
