# backend/app/services/admin_service.py

"""
Сервисный слой административной диагностики и обслуживания.
Чистая бизнес-логика, не зависит от HTTP.
Используется роутером admin.py и, потенциально, CLI напрямую.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.hiddify_client import HiddifyProvisioner

from app.config import settings

logger = logging.getLogger(__name__)

async def get_diagnostics(db: AsyncSession, verbose: bool = False) -> dict:
    """
    Возвращает сводку аномалий и, при verbose=True, детальные списки.
    """
    # Устаревшие инвойсы (старше 48 часов — можно вынести в параметр)
    dirty = await db.execute(
            text("SELECT COUNT(*) FROM payment_attempts WHERE status IN ('pending', 'processing') AND created_at < NOW() - make_interval(hours := :hours)"), {"hours": settings.INVOICE_DIRTY_HOURS}
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
            WHERE status = 'pending' AND created_at < NOW() - make_interval(hours := :hours)
            ORDER BY created_at DESC
            """
            inv_res = await db.execute(text(inv_sql), {"hours": settings.INVOICE_DIRTY_HOURS})


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
    """
    Удалить 'pending'-инвойсы старше N часов.
    'processing'-зомби (те, что зависли на этапе активации) переводим
    в 'failed', чтобы сохранить историю — по ним могли пройти деньги.
    """
    # 1. pending старше порога — удаляем
    res = await db.execute(
        text("""
            DELETE FROM payment_attempts
            WHERE status = 'pending'
              AND created_at < NOW() - make_interval(hours := :hours)
        """),
        {"hours": settings.INVOICE_DIRTY_HOURS}
    )
    deleted = res.rowcount

    # 2. processing-зомби — помечаем failed, не удаляем
    upd = await db.execute(
        text("""
            UPDATE payment_attempts
            SET status = 'failed', updated_at = NOW()
            WHERE status = 'processing'
              AND updated_at < NOW() - make_interval(hours := :hours)
        """),
        {"hours": settings.INVOICE_DIRTY_HOURS}
    )
    failed_zombies = upd.rowcount

    await db.commit()

    if failed_zombies:
        logger.info(
            f"🧟 [CLEANUP] processing-зомби помечено failed: {failed_zombies}"
        )

    return deleted


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
    Возвращает зависшие подписки в очередь обработки:
    'provisioning_failed' и 'pending_payment' → 'provisioning'.
    Реальный provisioning выполнит фоновый воркер / повторный вызов Hiddify.
    """
    result = await db.execute(
        text("""
            UPDATE subscriptions
            SET status = 'provisioning',
                updated_at = NOW()
            WHERE id IN (
                SELECT id FROM subscriptions
                WHERE status IN ('provisioning_failed', 'pending_payment')
                ORDER BY id ASC
                LIMIT :limit
            )
            RETURNING id
        """),
        {"limit": limit}
    )
    ids = result.fetchall()
    await db.commit()
    return len(ids)

async def check_hiddify_sync(db: AsyncSession, limit: int = 1000) -> dict:
    """
    Сравнивает статусы пользователей в БД и на Hiddify.
    Проверяет только существование профилей (missing_in_hiddify).
    """
    provisioner = HiddifyProvisioner()
    mismatches = []
    anomalies = []

    # Выбираем пользователей с UUID, без JOIN — каждый пользователь один раз
    sql = text("""
        SELECT DISTINCT u.id, u.email, u.tg_user_id, u.hiddify_uuid
        FROM users u
        WHERE u.hiddify_uuid IS NOT NULL
        ORDER BY u.id
        LIMIT :limit
    """)
    result = await db.execute(sql, {"limit": limit})
    rows = result.fetchall()

    logger.info(f"🔄 Начинаем сверку {len(rows)} пользователей с Hiddify...")

    for r in rows:
        u_id, email, tg_id, uuid_val = r
        uuid_str = str(uuid_val)
        contact = email or f"TG:{tg_id}" or f"ID:{u_id}"

        try:
            exists = await provisioner.check_user_exists(uuid_str)
        except Exception as e:
            logger.warning(f"Ошибка проверки {uuid_str}: {e}")
            anomalies.append({
                "type": "api_error",
                "email": contact,
                "uuid": uuid_str,
                "details": f"Ошибка API при проверке: {str(e)[:200]}"
            })
            continue

        if not exists:
            anomalies.append({
                "type": "missing_in_hiddify",
                "email": contact,
                "uuid": uuid_str,
                "details": f"Пользователь {contact} есть в биллинге, но профиль отсутствует на Hiddify."
            })

    logger.info(f"✅ Сверка завершена. Расхождений: {len(mismatches)}, аномалий: {len(anomalies)}")
    return {
        "status_mismatches": mismatches,
        "anomalies": anomalies
    }

async def cleanup_inactive_users(db: AsyncSession, hours: int = 24) -> int:
    """
    Удаляет пользователей, у которых нет ни одной подписки и которые созданы более `hours` часов назад.
    Возвращает количество удалённых записей.
    """
    res = await db.execute(
        text("""
            DELETE FROM users u
            WHERE u.id IN (
                SELECT u2.id
                FROM users u2
                LEFT JOIN subscriptions s ON s.user_id = u2.id
                WHERE s.id IS NULL
                  AND u2.created_at < NOW() - make_interval(hours := :hours)
            )
        """),
        {"hours": hours}
    )
    await db.commit()
    return res.rowcount

# =====================================================================
# Автосверка зависших платежей с Platega API
# =====================================================================

async def sync_pending_payments(
    db: AsyncSession,
    min_age_minutes: int = 15,
    limit: int = 50,
) -> dict:
    """
    Подтягивает статусы 'pending'/'processing' платежей, по которым
    вебхук от Platega не пришёл.

    Для каждой попытки с сохранённым provider_tx_id опрашивает Platega API:
      • CONFIRMED  → активирует подписку через ту же логику, что и вебхук
      • CANCELED   → статус cancelled
      • DECLINED/EXPIRED → статус failed
      • PENDING    → оставляет как есть
    """
    # Импорт внутри функции — избегаем циклической зависимости при старте
    from app.platega.platega.platega import Platega
    from app.services.platega_webhook_handler import _activate_subscription

    result = {
        "checked": 0,
        "activated": 0,
        "cancelled": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "details": [],
    }

    rows = (await db.execute(text("""
        SELECT id, user_id, tariff_slug, amount, provider_tx_id, status, created_at
        FROM payment_attempts
        WHERE status IN ('pending', 'processing')
          AND provider_tx_id IS NOT NULL
          AND provider_tx_id <> 'webhook'
          AND created_at < NOW() - make_interval(mins => :mins)
        ORDER BY created_at ASC
        LIMIT :lim
    """), {"mins": min_age_minutes, "lim": limit})).fetchall()

    if not rows:
        logger.info("🔍 [SYNC] Зависших платежей с tx_id не найдено")
        return result

    logger.info(f"🔍 [SYNC] Проверяем {len(rows)} платежей через Platega API")

    client = Platega(
        merchant_id=settings.PLATEGA_MERCHANT_ID,
        secret=settings.PLATEGA_API,
    )

    for attempt_id, user_id, tariff_slug, amount, tx_id, status, created_at in rows:
        result["checked"] += 1
        detail = {
            "attempt_id": str(attempt_id),
            "provider_tx_id": tx_id,
            "local_status_before": status,
        }

        # 1. Опрос Platega
        try:
            payload = client.get_payment_status(tx_id)
        except Exception as e:
            logger.warning(f"⚠️ [SYNC] {attempt_id}: ошибка запроса к Platega: {e}")
            result["errors"] += 1
            detail["error"] = str(e)[:200]
            result["details"].append(detail)
            continue

        platega_status = (payload or {}).get("status", "UNKNOWN")
        detail["platega_status"] = platega_status

        # 2. Разбираем статус
        if platega_status in ("CONFIRMED", "success"):
            try:
                async with db.begin_nested():
                    await _activate_subscription(
                        db,
                        order_id=attempt_id,
                        user_id=user_id,
                        tariff_slug=tariff_slug,
                        provider_tx_id=tx_id,
                    )
                await db.commit()
                result["activated"] += 1
                detail["action"] = "activated"
                logger.info(
                    f"✅ [SYNC] {attempt_id}: активирован (user_id={user_id}, "
                    f"tariff={tariff_slug})"
                )
            except Exception as e:
                await db.rollback()
                result["errors"] += 1
                detail["error"] = str(e)[:200]
                logger.exception(f"💥 [SYNC] {attempt_id}: ошибка активации: {e}")
            result["details"].append(detail)
            continue

        if platega_status == "CANCELED":
            await db.execute(
                text("""
                    UPDATE payment_attempts
                    SET status = 'cancelled', updated_at = NOW()
                    WHERE id = :id AND status IN ('pending', 'processing')
                """),
                {"id": attempt_id}
            )
            result["cancelled"] += 1
            detail["action"] = "cancelled"
            logger.info(f"⚪ [SYNC] {attempt_id}: cancelled (Platega CANCELED)")
            result["details"].append(detail)
            continue

        if platega_status in ("FAILED", "DECLINED", "EXPIRED"):
            await db.execute(
                text("""
                    UPDATE payment_attempts
                    SET status = 'failed', updated_at = NOW()
                    WHERE id = :id AND status IN ('pending', 'processing')
                """),
                {"id": attempt_id}
            )
            result["failed"] += 1
            detail["action"] = "failed"
            logger.info(f"🔴 [SYNC] {attempt_id}: failed (Platega {platega_status})")
            result["details"].append(detail)
            continue

        # PENDING / UNKNOWN / иное — оставляем как есть
        result["skipped"] += 1
        detail["action"] = "skipped"
        logger.info(f"⏭ [SYNC] {attempt_id}: пропущен (Platega {platega_status})")
        result["details"].append(detail)

    await db.commit()
    logger.info(
        f"🏁 [SYNC] Итог: проверено={result['checked']}, "
        f"активировано={result['activated']}, "
        f"отменено={result['cancelled']}, "
        f"failed={result['failed']}, "
        f"пропущено={result['skipped']}, "
        f"ошибок={result['errors']}"
    )
    return result
