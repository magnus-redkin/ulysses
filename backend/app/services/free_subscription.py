# backend/app/services/free_subscription.py

"""
Логика активации бесплатного тарифа (sub_free).
Поддерживает создание пользователя на нескольких HFM нодах.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.hiddify_client import HiddifyProvisioner
from app.services.node_manager import node_manager

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

    # 1. Создаём запись подписки в БД
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

    # 3. Provisioning на всех HFM нодах
    nodes = node_manager.get_hfm_nodes()
    if not nodes:
        logger.error("❌ Нет доступных HFM нод для provisioning")
        await db.execute(
            text("UPDATE subscriptions SET status = 'provisioning_failed', provisioning_error = 'No HFM nodes configured', updated_at = NOW() WHERE id = :sub_id"),
            {"sub_id": sub_id}
        )
        await db.commit()
        raise RuntimeError("No HFM nodes configured")

    success_count = 0
    failed_nodes = []

    for node in nodes:
        node_id = node.get("id", "unknown")
        node_ip = node.get("ip", "")
        node_domain = node.get("domain", "")
        admin_path = node.get("admin_path", "")
        api_key = node.get("api_key", "")

        if not admin_path or not api_key:
            logger.error(f"❌ Нода {node_id}: не хватает admin_path или api_key")
            failed_nodes.append(node_id)
            continue

        # Формируем API URL для текущей ноды
        base_host = node_domain or node_ip
        api_url = f"https://{base_host}/{admin_path}"

        try:
            provisioner = HiddifyProvisioner(api_url=api_url, api_key=api_key)
            success = await provisioner.create_user(
                uuid=hiddify_uuid,
                name=email.split("@")[0][:30] if email else f"user_{user_id}"
            )

            if success:
                success_count += 1
                logger.info(f"✅ [FREE SUB] Пользователь создан на ноде {node_id} ({base_host})")
            else:
                logger.error(f"❌ [FREE SUB] Не удалось создать на ноде {node_id}")
                failed_nodes.append(node_id)

        except Exception as e:
            logger.error(f"❌ [FREE SUB] Ошибка при создании на ноде {node_id}: {e}")
            failed_nodes.append(node_id)

    # 4. Определяем итоговый статус
    if success_count == 0:
        # Все ноды не приняли пользователя
        error_msg = f"All HFM nodes failed: {', '.join(failed_nodes)}"
        await db.execute(
            text("UPDATE subscriptions SET status = 'provisioning_failed', provisioning_error = :err, updated_at = NOW() WHERE id = :sub_id"),
            {"sub_id": sub_id, "err": error_msg[:200]}
        )
        await db.commit()
        raise RuntimeError(f"VPN Provisioning failed: {error_msg}")

    # Если хотя бы одна нода успешна, считаем активацию успешной
    await db.execute(
        text("UPDATE subscriptions SET status = 'active', activated_at = NOW(), updated_at = NOW() WHERE id = :sub_id"),
        {"sub_id": sub_id}
    )
    await db.commit()

    logger.info(f"✅ [FREE SUB] sub_free активирован для {email or user_id} на {success_count}/{len(nodes)} нодах")

    # 5. Формируем ссылку на агрегатор подписок
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    subscription_link = f"https://{domain}/subscription/{hiddify_uuid}"

    return {
        "subscription_link": subscription_link,
        "expires_at": expires_at.isoformat(),
        "sub_id": sub_id,
        "success_nodes": success_count,
        "total_nodes": len(nodes)
    }
