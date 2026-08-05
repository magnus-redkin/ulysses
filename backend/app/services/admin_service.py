"""
Сервисный слой административной диагностики и обслуживания.
Чистая бизнес-логика, не зависит от HTTP.
Используется роутером admin.py и, потенциально, CLI напрямую.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.hiddify_client import HiddifyProvisioner

logger = logging.getLogger(__name__)


async def get_diagnostics(db: AsyncSession, verbose: bool = False) -> dict:
    """
    Возвращает сводку аномалий и, при verbose=True, детальные списки.
    """
    # Устаревшие инвойсы (старше 48 часов — можно вынести в параметр)
    dirty = await db.execute(
        text("SELECT COUNT(*) FROM payment_attempts WHERE status = 'pending' AND created_at < NOW() - INTERVAL '2 days'")
    )
    dirty_count = dirty.scalar()

    # Зависшие активации
    failed = await db.execute(
        text("SELECT COUNT(*) FROM subscriptions WHERE status IN ('provisioning_failed', 'provisioning')")
    )
    failed_count = failed.scalar()

    summary = {
        "dirty_invoices_count": dirty_count,
        "failed_provisioning_count": failed_count,
        "status_mismatches_count": 0,  # заглушка до интеграции Hiddify
        "hiddify_anomalies_count": 0
    }

    result = {
        "summary": summary,
        "dirty_invoices": [],
        "failed_provisioning_list": [],
        "status_mismatches": [],
        "anomalies": []
    }

    if verbose:
        if dirty_count > 0:
            inv_sql = """
                SELECT id, email, tariff_slug, amount, created_at
                FROM payment_attempts
                WHERE status = 'pending' AND created_at < NOW() - INTERVAL '2 days'
                ORDER BY created_at DESC
            """
            inv_res = await db.execute(text(inv_sql))
            inv_rows = inv_res.fetchall()
            result["dirty_invoices"] = [
                {
                    "id": str(r[0]),
                    "email": r[1],
                    "tariff_slug": r[2],
                    "amount": r[3],
                    "created_at": r[4].strftime("%Y-%m-%d %H:%M") if r[4] else None
                }
                for r in inv_rows
            ]

        if failed_count > 0:
            sub_sql = """
                SELECT s.id, u.tg_user_id, u.email, s.tariff_slug,
                       s.provisioning_attempts, s.provisioning_error
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status IN ('provisioning_failed', 'provisioning')
                ORDER BY s.id DESC
            """
            sub_res = await db.execute(text(sub_sql))
            sub_rows = sub_res.fetchall()
            result["failed_provisioning_list"] = [
                {
                    "subscription_id": r[0],
                    "tg_user_id": r[1],
                    "email": r[2],
                    "tariff_slug": r[3],
                    "attempts": r[4],
                    "last_error": r[5] or "Ожидает повтора"
                }
                for r in sub_rows
            ]

    return result


async def cleanup_invoices(db: AsyncSession) -> int:
    """Удалить pending инвойсы старше 24 часов, вернуть количество удалённых."""
    res = await db.execute(
        text("DELETE FROM payment_attempts WHERE status = 'pending' AND created_at < NOW() - INTERVAL '24 hours'")
    )
    await db.commit()
    return res.rowcount

async def get_stats(db: AsyncSession, verbose: bool = False) -> dict:
    """Базовая статистика и, при verbose=True, список зависших подписок."""
    # Количество пользователей и подписок
    users_res = await db.execute(text("SELECT COUNT(*) FROM users"))
    active_res = await db.execute(text("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'"))
    pending_res = await db.execute(
        text("SELECT COUNT(*) FROM subscriptions WHERE status IN ('provisioning', 'pending_payment')")
    )

    stats = {
        "total_users": users_res.scalar(),
        "active_subscriptions": active_res.scalar(),
        "pending_subscriptions": pending_res.scalar(),
    }

    result = {"stats": stats}
    if verbose and stats["pending_subscriptions"] > 0:
        sql = """
            SELECT s.id, u.id, u.email, u.tg_user_id, s.tariff_slug, s.status,
                   s.provisioning_attempts, s.provisioning_error,
                   s.last_provisioning_at
            FROM subscriptions s
            JOIN users u ON s.user_id = u.id
            WHERE s.status IN ('provisioning', 'pending_payment')
            ORDER BY s.id DESC
        """
        rows = (await db.execute(text(sql))).fetchall()
        pending_details = []
        for r in rows:
            s_id, u_id, email, tg_id, tariff, status, attempts, last_error, last_at = r
            pending_details.append({
                "subscription_id": s_id,
                "user_id": u_id,
                "email": email,
                "tg_user_id": tg_id,
                "tariff_slug": tariff,
                "status": status,
                "attempts": attempts or 0,
                "last_error": last_error or "",
                "last_attempt_at": last_at.strftime("%Y-%m-%d %H:%M UTC") if last_at else None
            })
        result["pending_details"] = pending_details
    return result

async def process_pending_provisioning(db: AsyncSession, limit: int = 50) -> int:
    """
    Возвращает зависшие подписки в очередь обработки.
    Меняет статус на 'provisioning' и возвращает количество затронутых записей.
    """
    result = await db.execute(
        text("""
            UPDATE subscriptions
            SET status = 'provisioning'
            WHERE id IN (
                SELECT id FROM subscriptions
                WHERE status IN ('provisioning_failed', 'pending_payment')
                LIMIT :limit
            )
            RETURNING id
        """),
        {"limit": limit}
    )
    await db.commit()
    return len(result.fetchall())

async def check_hiddify_sync(db: AsyncSession) -> dict:
    """
    Сравнивает статусы пользователей в БД и на Hiddify.
    Возвращает словарь с ключами:
        - status_mismatches: список расхождений активен/неактивен
        - anomalies: список критических аномалий (профиль отсутствует и т.п.)
    """
    provisioner = HiddifyProvisioner()
    mismatches = []
    anomalies = []

    # Выбираем пользователей, у которых есть UUID и хоть одна подписка (любая)
    sql = text("""
        SELECT u.id, u.email, u.tg_user_id, u.hiddify_uuid,
               s.status as sub_status
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.hiddify_uuid IS NOT NULL
        ORDER BY u.id
    """)
    result = await db.execute(sql)
    rows = result.fetchall()

    logger.info(f"🔄 Начинаем сверку {len(rows)} пользователей с Hiddify...")

    for r in rows:
        u_id, email, tg_id, uuid, sub_status = r
        uuid_str = str(uuid)
        contact = email or f"TG:{tg_id}" or f"ID:{u_id}"

        try:
            exists = await provisioner.check_user_exists(uuid_str)
        except Exception as e:
            logger.warning(f"Ошибка проверки {uuid_str}: {e}")
            # Можно добавить в anomalies как "API error"
            continue

        # Логика сравнения
        if not exists:
            # Профиль отсутствует в Hiddify, но в БД есть UUID
            anomalies.append({
                "type": "missing_in_hiddify",
                "email": contact,
                "uuid": uuid_str,
                "details": f"Пользователь {contact} есть в биллинге, но профиль отсутствует на Hiddify.",
                "subscription_status": sub_status or "no_subscription"
            })
        else:
            # Здесь можно было бы получить детали профиля (enabled/disabled),
            # но check_user_exists возвращает только bool.
            # Для более детальной сверки нужен метод get_user_info.
            # Пока мы можем только фиксировать факт существования.
            # Предположим, что если подписка active, а профиль существует — ОК.
            # Если подписка не active (expired/cancelled), а профиль существует — аномалия?
            # Пока оставим только missing_in_hiddify.
            pass

    logger.info(f"✅ Сверка завершена. Расхождений: {len(mismatches)}, аномалий: {len(anomalies)}")
    return {
        "status_mismatches": mismatches,
        "anomalies": anomalies
    }
