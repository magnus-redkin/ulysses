"""
Фоновая проверка истекающих подписок.
Вызывается из lifespan.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services.sender import send_subscription_expiry

logger = logging.getLogger(__name__)


async def check_expiring_subscriptions():
    """
    Проверить подписки, истекающие через 3 дня, 1 день и истёкшие.
    Отправить уведомления пользователям.
    """
    now = datetime.now(timezone.utc)
    threshold_3d = now + timedelta(days=3)
    threshold_1d = now + timedelta(days=1)

    async with AsyncSessionLocal() as session:
        # Истекающие через 3 дня (от 2.5 до 3.5 дней)
        res_3d = await session.execute(
            text("""
                SELECT u.tg_user_id, u.email
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status = 'active'
                  AND s.expires_at BETWEEN :now AND :threshold_3d
                  AND s.notified_3d = FALSE
            """),
            {"now": now, "threshold_3d": threshold_3d}
        )
        for row in res_3d.fetchall():
            tg_id, email = row
            sent = await send_subscription_expiry(tg_id, 3, email)
            if sent:
                await session.execute(
                    text("UPDATE subscriptions SET notified_3d = TRUE WHERE id IN (SELECT id FROM subscriptions WHERE user_id = (SELECT id FROM users WHERE tg_user_id = :tg_id))"),
                    {"tg_id": tg_id}
                )
                await session.commit()
                logger.info(f"3-day reminder sent to {tg_id}")

        # Истекающие через 1 день (от 0.5 до 1.5 дней)
        res_1d = await session.execute(
            text("""
                SELECT u.tg_user_id, u.email
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status = 'active'
                  AND s.expires_at BETWEEN :now AND :threshold_1d
                  AND s.notified_1d = FALSE
            """),
            {"now": now, "threshold_1d": threshold_1d}
        )
        for row in res_1d.fetchall():
            tg_id, email = row
            sent = await send_subscription_expiry(tg_id, 1, email)
            if sent:
                await session.execute(
                    text("UPDATE subscriptions SET notified_1d = TRUE WHERE id IN (SELECT id FROM subscriptions WHERE user_id = (SELECT id FROM users WHERE tg_user_id = :tg_id))"),
                    {"tg_id": tg_id}
                )
                await session.commit()
                logger.info(f"1-day reminder sent to {tg_id}")

        # Истёкшие (expires_at < now, но status ещё active)
        res_expired = await session.execute(
            text("""
                SELECT u.tg_user_id, u.email
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status = 'active'
                  AND s.expires_at < :now
                  AND s.notified_expired = FALSE
            """),
            {"now": now}
        )
        for row in res_expired.fetchall():
            tg_id, email = row
            sent = await send_subscription_expiry(tg_id, 0, email)
            if sent:
                await session.execute(
                    text("""
                        UPDATE subscriptions SET notified_expired = TRUE, status = 'expired'
                        WHERE id IN (
                            SELECT s.id FROM subscriptions s
                            JOIN users u ON s.user_id = u.id
                            WHERE u.tg_user_id = :tg_id
                        )
                    """),
                    {"tg_id": tg_id}
                )
                await session.commit()
                logger.info(f"Expired notification sent to {tg_id}, subscription marked as expired")
