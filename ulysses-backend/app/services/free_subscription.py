"""
Логика активации бесплатного тарифа (sub_free).
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.hiddify_client import HiddifyProvisioner

logger = logging.getLogger(__name__)

async def create_free_subscription(
    db: AsyncSession,
    user: dict
) -> dict:
    """
    Активировать бесплатный тариф sub_free для пользователя.
    Создаёт запись подписки, делает provisioning на HFM.
    Возвращает словарь с subscription_link и expires_at.
    """
    hiddify_uuid = user["hiddify_uuid"]
    user_id = user["user_id"]
    email = user.get("email", "")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=3)

    # 1. Создаём запись подписки (Статус изначально 'provisioning')
    sql_sub = """
        INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
        VALUES (:user_id, 'sub_free', 'provisioning', 'main', :starts, :expires, :starts, :starts)
        RETURNING id
    """
    res_sub = await db.execute(
        text(sql_sub),
        {
            "user_id": user_id,
            "starts": now,
            "expires": expires_at
        }
    )
    sub_id = res_sub.scalar_one()

    # ИСПРАВЛЕНО: Используем flush вместо commit, чтобы получить id, но не закрывать транзакцию
    await db.flush()

    # 2. Provisioning на HFM
    try:
        provisioner = HiddifyProvisioner()
        success = await provisioner.create_user(
            uuid=hiddify_uuid,
            name=email.split("@")[0][:30] if email else f"user_{user_id}"
        )

        if success:
            await db.execute(
                text("UPDATE subscriptions SET status = 'active', activated_at = :now WHERE id = :sub_id"),
                {"now": now, "sub_id": sub_id}
            )
            logger.info(f"✅ sub_free активирован для {email or user_id}")
        else:
            # Ошибка логики API панели
            await db.execute(
                text("UPDATE subscriptions SET status = 'failed', provisioning_error = 'HFM API error' WHERE id = :sub_id"),
                {"sub_id": sub_id}
            )
            raise RuntimeError("Hiddify API rejected user creation")

    except Exception as e:
        logger.error(f"❌ Фатальная ошибка интеграции Hiddify: {e}")
        await db.execute(
            text("UPDATE subscriptions SET status = 'failed', provisioning_error = :err WHERE id = :sub_id"),
            {"sub_id": sub_id, "err": str(e)[:200]}
        )
        # ИСПРАВЛЕНО: Пробрасываем ошибку выше, чтобы сработал корректный rollback транзакции
        raise RuntimeError(f"VPN Provisioning failed: {e}")

    # 3. Формируем ссылку для подключения
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    subscription_link = f"https://{domain}/subscription/{hiddify_uuid}/#Ulysses"

    return {
        "subscription_link": subscription_link,
        "expires_at": expires_at.isoformat(),
        "sub_id": sub_id
    }
