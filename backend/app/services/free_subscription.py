# backend/app/services/free_subscription.py

"""
Логика активации бесплатного тарифа (sub_free).
Provisioning выполняется на всех активных HFM нодах.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.hiddify_client import HiddifyProvisioner
from app.services.node_manager import node_manager
from app.services.subscription_links import build_subscription_links

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

    # 1. Запись подписки в БД
    sql_sub = """
        INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
        VALUES (:user_id, 'sub_free', 'provisioning', 'main', :starts, :expires, NOW(), NOW())
        RETURNING id
    """
    res_sub = await db.execute(
        text(sql_sub),
        {"user_id": user_id, "starts": now, "expires": expires_at}
    )
    sub_id = res_sub.scalar_one()
    await db.flush()
    await db.commit()

    # 2. Provisioning на всех активных HFM нодах
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        logger.error("❌ Нет доступных HFM нод для provisioning")
        await db.execute(
            text("UPDATE subscriptions SET status = 'provisioning_failed', provisioning_error = 'No HFM nodes configured', updated_at = NOW() WHERE id = :sub_id"),
            {"sub_id": sub_id}
        )
        await db.commit()
        raise RuntimeError("No HFM nodes configured")

    provisioner = HiddifyProvisioner()
    success = await provisioner.create_user(
        uuid=hiddify_uuid,
        name=email.split("@")[0][:30] if email else f"user_{user_id}"
    )

    if not success:
        await db.execute(
            text("UPDATE subscriptions SET status = 'provisioning_failed', provisioning_error = 'All HFM nodes failed', updated_at = NOW() WHERE id = :sub_id"),
            {"sub_id": sub_id}
        )
        await db.commit()
        raise RuntimeError("VPN Provisioning failed: All HFM nodes failed")

    # 3. Активируем подписку
    await db.execute(
        text("UPDATE subscriptions SET status = 'active', activated_at = NOW(), updated_at = NOW() WHERE id = :sub_id"),
        {"sub_id": sub_id}
    )
    await db.commit()

    logger.info(f"✅ [FREE SUB] sub_free активирован для {email or user_id}")

    # 3.5. Пуш UUID на RF-ноду (best-effort, не ломает активацию)
    from app.services.rf_node_client import add_user as rf_add_user
    await rf_add_user(str(hiddify_uuid))

    # 4. Ссылка на агрегатор подписок
    links = build_subscription_links(hiddify_uuid)
    return {
        "simple_link": links["simple_link"],
        "advanced_link": links["advanced_link"],
        "expires_at": expires_at.isoformat(),
        "sub_id": sub_id,
        "success_nodes": len(nodes),
        "total_nodes": len(nodes),
    }
