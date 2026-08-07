# backend/app/services/free_subscription.py

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
    hiddify_uuid = str(user["hiddify_uuid"]).strip().lower()
    user_id = user["user_id"]
    email = user.get("email", "")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=3)

    # 1. Создаём запись подписки
    sql_sub = """
        INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
        VALUES (:user_id, 'sub_free', 'provisioning', 'main', :starts, :expires, NOW(), NOW())
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
    await db.flush()

    # 2. Фиксируем запись подписки в БД ДО попытки provisioning
    await db.commit()

    # 3. Provisioning на HFM
    try:
        provisioner = HiddifyProvisioner()
        success = await provisioner.create_user(
            uuid=hiddify_uuid,
            name=email.split("@")[0][:30] if email else f"user_{user_id}"
        )

        if success:
            await db.execute(
                text("UPDATE subscriptions SET status = 'active', activated_at = NOW(), updated_at = NOW() WHERE id = :sub_id"),
                {"sub_id": sub_id}
            )
            await db.commit()
            logger.info(f"✅ [FREE SUB] sub_free успешно активирован для {email or user_id}")
        else:
            await db.execute(
                text("UPDATE subscriptions SET status = 'failed', provisioning_error = 'HFM API error', updated_at = NOW() WHERE id = :sub_id"),
                {"sub_id": sub_id}
            )
            await db.commit()
            raise RuntimeError("Hiddify API rejected user creation")

    except Exception as e:
        logger.error(f"❌ Фатальная ошибка интеграции Hiddify: {e}")
        try:
            await db.execute(
                text("UPDATE subscriptions SET status = 'failed', provisioning_error = :err, updated_at = NOW() WHERE id = :sub_id"),
                {"sub_id": sub_id, "err": str(e)[:200]}
            )
            await db.commit()
        except Exception as db_err:
            logger.error(f"❌ Не удалось записать ошибку провижна в СУБД: {db_err}")
            await db.rollback()
        raise RuntimeError(f"VPN Provisioning failed: {e}")

    # 4. Формируем ссылку
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    subscription_link = f"https://{domain}/subscription/{hiddify_uuid}/#Ulysses"

    return {
        "subscription_link": subscription_link,
        "expires_at": expires_at.isoformat(),
        "sub_id": sub_id
    }
