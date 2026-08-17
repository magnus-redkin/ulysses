"""
Единый сервис отправки сообщений: Telegram, email, broadcast.
"""
import logging
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings

logger = logging.getLogger(__name__)

BOT_TOKEN = settings.BOT_TOKEN
ADMIN_IDS = [int(x) for x in settings.ADMIN_IDS.split(",") if x.strip()] if settings.ADMIN_IDS else []


async def send_telegram_message(tg_id: int, text: str) -> bool:
    """Отправить сообщение пользователю через Telegram Bot API."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return False

    if not tg_id:
        logger.warning("tg_id is empty, skip sending")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
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
            elif resp.status_code == 403:
                logger.warning(f"User {tg_id} blocked the bot")
                return False
            elif resp.status_code == 429:
                logger.warning(f"Rate limit for {tg_id}, retry later")
                return False
            else:
                logger.error(f"Telegram API error for {tg_id}: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send message to {tg_id}: {e}")
        return False


async def send_admin_alert(text: str) -> bool:
    """Отправить алерт всем админам."""
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty, alert not sent")
        return False

    results = []
    for admin_id in ADMIN_IDS:
        result = await send_telegram_message(admin_id, f"🚨 {text}")
        results.append(result)
    return any(results)


async def send_subscription_expiry(tg_id: int, days_left: int, email: str = None) -> bool:
    """
    Отправить уведомление об истечении подписки.
    days_left: 3, 1, 0 (подписка истекла).
    """
    if not tg_id:
        logger.debug(f"No tg_id for {email}, skip expiry notification")
        return False

    if days_left == 3:
        text = (
            "⏳ <b>Подписка истекает через 3 дня</b>\n\n"
            "Чтобы не остаться без защиты, продлите подписку.\n"
            "🔗 https://ulysses.best"
        )
    elif days_left == 1:
        text = (
            "⚠️ <b>Остался 1 день подписки!</b>\n\n"
            "Продлите подписку, чтобы не потерять доступ.\n"
            "🔗 https://ulysses.best"
        )
    elif days_left == 0:
        text = (
            "🛑 <b>Подписка истекла</b>\n\n"
            "Доступ приостановлен. Продлите подписку для возобновления.\n"
            "🔗 https://ulysses.best"
        )
    else:
        return False

    return await send_telegram_message(tg_id, text)


async def broadcast_to_all(db: AsyncSession, text: str) -> dict:
    """
    Отправить сообщение всем пользователям с tg_user_id.
    Возвращает {"sent": N, "failed": M, "total": K}.
    """
    result = await db.execute(
        text("SELECT tg_user_id FROM users WHERE tg_user_id IS NOT NULL")
    )
    rows = result.fetchall()

    sent = 0
    failed = 0
    total = len(rows)

    for row in rows:
        tg_id = row[0]
        ok = await send_telegram_message(tg_id, text)
        if ok:
            sent += 1
        else:
            failed += 1

        # Небольшая задержка, чтобы не упереться в rate limit Telegram
        await asyncio.sleep(0.05)

    logger.info(f"Broadcast finished: sent={sent}, failed={failed}, total={total}")
    return {"sent": sent, "failed": failed, "total": total}


async def _get_all_tg_ids(db: AsyncSession) -> list[int]:
    """Получить все tg_user_id из БД."""
    result = await db.execute(
        text("SELECT tg_user_id FROM users WHERE tg_user_id IS NOT NULL")
    )
    return [row[0] for row in result.fetchall()]
