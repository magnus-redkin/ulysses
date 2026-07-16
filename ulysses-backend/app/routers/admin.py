# ulysses-backend/app/routers/admin.py
# ============================================================
# ЧАСТЬ 1: ИМПОРТЫ И ДИАГНОСТИЧЕСКИЕ МЕТОДЫ
# ============================================================

import os
import logging
import httpx
import uuid
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import text, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.models import User, Subscription, PaymentAttempt

from app.services.provisioning_manager import ProvisioningManager
from app.services.hiddify_client import HiddifyProvisioner

from app.system_info import collect_system_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _classify_anomaly(db_row, hiddify_data) -> Optional[str]:
    """Внутренний хелпер: определяет тип аномалии профиля."""
    if db_row and not hiddify_data:
        return "missing_in_hiddify"
    elif not db_row and hiddify_data:
        return "unknown_in_db"
    elif db_row and hiddify_data:
        db_status = db_row
        hd_enabled = hiddify_data.get("enabled", False)
        if db_status == "active" and not hd_enabled:
            return "should_be_enabled"
        elif db_status != "active" and hd_enabled:
            return "should_be_disabled"
    return None


async def _get_status_mismatches(db: AsyncSession) -> list:
    """Внутренняя функция: сканирует расхождения тумблеров активности с Hiddify."""
    status_mismatches = []
    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                hiddify_users = response.json()
                hiddify_map = {str(u.get("uuid", "")).lower(): u for u in hiddify_users}

                db_data_result = await db.execute(text("""
                    SELECT DISTINCT ON (u.id) u.hiddify_uuid, u.email, s.status, s.expires_at
                    FROM users u
                    LEFT JOIN subscriptions s ON s.user_id = u.id
                    ORDER BY u.id, s.expires_at DESC
                """))

                now = datetime.utcnow()
                for row in db_data_result.fetchall():
                    uuid_raw, email, db_status, expires_at = row
                    if not uuid_raw:
                        continue

                    uuid_str = str(uuid_raw).lower()
                    if uuid_str not in hiddify_map:
                        continue

                    hd_user = hiddify_map[uuid_str]
                    hd_enabled = hd_user.get("enable", False)

                    expires_naive = expires_at.replace(tzinfo=None) if expires_at and expires_at.tzinfo else expires_at
                    db_is_active = db_status == "active" and expires_naive and expires_naive > now

                    if db_is_active and not hd_enabled:
                        status_mismatches.append({
                            "uuid": uuid_str, "email": email or "—",
                            "issue": "Должен быть включен, но выключен в Hiddify", "action": "enable"
                        })
                    elif not db_is_active and hd_enabled:
                        status_mismatches.append({
                            "uuid": uuid_str, "email": email or "—",
                            "issue": "Должен быть выключен (истек), но активен в Hiddify", "action": "disable"
                        })
    except Exception as e:
        logger.error(f"Ошибка в _get_status_mismatches: {e}")
    return status_mismatches


async def _check_entity(query: str, db: AsyncSession) -> dict:
    """Детализация по конкретной сущности (UUID, email, tg_id, username, имя в Hiddify)."""
    clean_query = str(query).strip().lower()
    clean_query_no_at = clean_query.replace("@", "")

    result = await db.execute(text("""
        SELECT u.hiddify_uuid, u.email, u.tg_user_id, u.tg_username, u.id,
               s.status, s.expires_at, s.tariff_slug, s.id as sub_id
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE CAST(u.hiddify_uuid AS TEXT) = :q
           OR LOWER(u.email) = :q
           OR CAST(u.tg_user_id AS TEXT) = :q
           OR LOWER(u.tg_username) = :q_no_at
        ORDER BY s.expires_at DESC LIMIT 1
    """), {"q": clean_query, "q_no_at": clean_query_no_at})
    row = result.fetchone()

    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    hiddify_data = None

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                hiddify_users = response.json()
                for u in hiddify_users:
                    if str(u.get("uuid", "")).lower() == clean_query or u.get("name", "").lower() == clean_query:
                        hiddify_data = {
                            "uuid": u.get("uuid"), "name": u.get("name"), "enabled": u.get("enable"),
                            "usage_gb": u.get("current_usage_GB", 0), "limit_gb": u.get("usage_limit_GB", 0),
                            "days_left": u.get("remaining_days", 0)
                        }
                        break

                if not hiddify_data and row and row[0]:
                    db_uuid = str(row[0]).lower()
                    for u in hiddify_users:
                        if str(u.get("uuid", "")).lower() == db_uuid:
                            hiddify_data = {
                                "uuid": u.get("uuid"), "name": u.get("name"), "enabled": u.get("enable"),
                                "usage_gb": u.get("current_usage_GB", 0), "limit_gb": u.get("usage_limit_GB", 0),
                                "days_left": u.get("remaining_days", 0)
                            }
                            break
    except Exception as e:
        logger.error(f"Ошибка запроса Hiddify в _check_entity: {e}")

    if not row and hiddify_data:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, u.tg_user_id, u.tg_username, u.id,
                   s.status, s.expires_at, s.tariff_slug, s.id as sub_id
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE CAST(u.hiddify_uuid AS TEXT) = :q
            ORDER BY s.expires_at DESC LIMIT 1
        """), {"q": hiddify_data["uuid"].lower()})
        row = result.fetchone()

    if not row and not hiddify_data:
        raise HTTPException(status_code=404, detail="Сущность не найдена ни в биллинге, ни в Hiddify")

    return {
        "found_in_db": row is not None,
        "found_in_hiddify": hiddify_data is not None,
        "account": {
            "id": row[4] if row else None,
            "email": row[1] if row else ("Бот (без почты)" if row and row[2] and not row[1] else "—"),
            "tg_user_id": row[2] if row else None,
            "tg_username": row[3] if row else None,
            "hiddify_uuid": str(row[0]) if row else None
        } if row else None,
        "subscription": {
            "id": row[8] if row else None,
            "status": row[5] if row else None,
            "expires_at": row[6].isoformat() if row and row[6] else None,
            "tariff_slug": row[7] if row else None
        } if row else None,
        "hiddify_profile": hiddify_data,
        "anomaly": _classify_anomaly(row, hiddify_data)
    }
# ============================================================
# ЧАСТЬ 2: ОСНОВНЫЕ АДМИН-РОУТЫ FASTAPI
# ============================================================

@router.get("/stats")
async def get_admin_stats(
    include_users: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Эндпоинт для администратора: получение общей статистики системы."""
    total_users_result = await db.execute(select(func.count()).select_from(User))
    total_users = total_users_result.scalar_one()

    active_subs_result = await db.execute(
        select(func.count()).select_from(Subscription).where(Subscription.status == 'active')
    )
    active_subs = active_subs_result.scalar_one()

    pending_subs_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status.in_(['pending_payment', 'provisioning'])
        )
    )
    pending_subs = pending_subs_result.scalar_one()

    response_data = {
        "total_users": total_users,
        "active_subscriptions": active_subs,
        "pending_subscriptions": pending_subs
    }

    if include_users:
        users_result = await db.execute(select(User))
        users_rows = users_result.scalars().all()

        users_list = []
        for u in users_rows:
            users_list.append({
                "tg_user_id": getattr(u, "tg_user_id", None),
                "email": getattr(u, "email", None),
                "status": getattr(u, "status", "active")
            })
        response_data["users"] = users_list

    return response_data


@router.get("/system")
async def get_backend_system_status():
    """Эндпоинт системного мониторинга: возвращает JSON для uadmin CLI system."""
    metrics = await collect_system_metrics()
    return metrics


@router.get("/check")
async def check_system(
    query: str = Query(None, description="UUID, email, tg_id или username для детализации"),
    db: AsyncSession = Depends(get_db)
):
    """Проверка аномалий системы: расхождения с Hiddify, зависшие подписки, мусор."""
    if query:
        return await _check_entity(query, db)

    dirty_invoices_result = await db.execute(text("""
        SELECT COUNT(*) FROM payment_attempts
        WHERE status = 'pending' AND created_at < NOW() - INTERVAL '48 hours'
    """))
    dirty_invoices = dirty_invoices_result.scalar_one()

    failed_provisioning_result = await db.execute(text("""
        SELECT u.email, u.tg_username, s.id, s.tariff_slug, s.provisioning_error
        FROM subscriptions s JOIN users u ON s.user_id = u.id
        WHERE s.status = 'provisioning_failed'
    """))
    failed_subs = [
        {"email": r, "tg": r, "sub_id": r, "tariff": r, "error": r}
        for r in failed_provisioning_result.fetchall()
    ]

    status_mismatches = await _get_status_mismatches(db)
    hiddify_anomalies = []

    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                hiddify_users = response.json()
                hiddify_map = {str(u.get("uuid", "")).lower(): u for u in hiddify_users}

                db_data_result = await db.execute(text("""
                    SELECT DISTINCT ON (u.id) u.hiddify_uuid, u.email, s.status, s.expires_at, u.id
                    FROM users u LEFT JOIN subscriptions s ON s.user_id = u.id
                    ORDER BY u.id, s.expires_at DESC
                """))

                now = datetime.utcnow()

                for row in db_data_result.fetchall():
                    uuid_raw, email, db_status, expires_at, user_id = row
                    if not uuid_raw:
                        continue

                    uuid_str = str(uuid_raw).lower()
                    in_hiddify = uuid_str in hiddify_map

                    if not in_hiddify:
                        expires_naive = expires_at.replace(tzinfo=None) if expires_at and expires_at.tzinfo else expires_at
                        db_is_active = db_status == "active" and expires_naive and expires_naive > now

                        if db_is_active:
                            hiddify_anomalies.append({
                                "type": "missing_in_hiddify",
                                "uuid": uuid_str,
                                "email": email or f"User {user_id}",
                                "details": "Активен в биллинге, но отсутствует профиль в Hiddify"
                            })

                db_uuids = {str(r).lower() for r in await db.execute(select(User.hiddify_uuid)) if r}
                for hu_uuid in hiddify_map:
                    if hu_uuid not in db_uuids:
                        hd_user = hiddify_map[hu_uuid]
                        hiddify_anomalies.append({
                            "type": "unknown_in_db",
                            "uuid": hu_uuid,
                            "email": hd_user.get("name", "Unknown"),
                            "details": "Создан в Hiddify, отсутствует в биллинге",
                            "hiddify_info": {
                                "usage_gb": hd_user.get("current_usage_GB", 0),
                                "limit_gb": hd_user.get("usage_limit_GB", 0),
                                "enabled": hd_user.get("enable", False)
                            }
                        })
    except Exception as e:
        logger.error(f"🔴 Ошибка сканирования Hiddify: {e}")

    return {
        "summary": {
            "dirty_invoices_count": dirty_invoices,
            "failed_provisioning_count": len(failed_subs),
            "hiddify_anomalies_count": len(hiddify_anomalies),
            "status_mismatches_count": len(status_mismatches)
        },
        "failed_subscriptions": failed_subs,
        "anomalies": hiddify_anomalies,
        "status_mismatches": status_mismatches
    }
# ============================================================
# ЧАСТЬ 3: УПРАВЛЕНИЕ АККАУНТАМИ И КРОН-ФИКСЫ (CRON)
# ============================================================

@router.delete("/account")
async def delete_account(
    tg_user_id: int = Query(None),
    email: str = Query(None),
    uuid_str: str = Query(None, alias="uuid"),
    target: str = Query("all"),
    db: AsyncSession = Depends(get_db)
):
    """Полное каскадное удаление аккаунта из биллинга и Hiddify."""
    hiddify_uuid = uuid_str
    user_id = None

    if not hiddify_uuid:
        if tg_user_id:
            result = await db.execute(text("SELECT id, hiddify_uuid FROM users WHERE tg_user_id = :id"), {"id": tg_user_id})
        elif email:
            result = await db.execute(text("SELECT id, hiddify_uuid FROM users WHERE email = :e"), {"e": email})
        else:
            raise HTTPException(status_code=400, detail="tg_user_id, email or uuid required")

        row = result.fetchone()
        if row:
            user_id = row[0]
            hiddify_uuid = str(row[1]) if row[1] else None

    deleted_db = False
    deleted_hf = False

    if target in ("all", "hiddify") and hiddify_uuid:
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.post(
                    settings.HIDDIFY_API_URL,
                    headers={"Hiddify-API-Key": settings.HIDDIFY_API_KEY, "Content-Type": "application/json"},
                    json={"action": "delete", "uuid": hiddify_uuid}
                )
                deleted_hf = resp.status_code == 200
        except Exception as e:
            logger.error(f"Ошибка удаления из Hiddify: {e}")

    if target in ("all", "db") and tg_user_id:
        # Чистим инвойсы всегда
        bot_email_alias = f"tg_bot_{tg_user_id}@ulysses.internal"
        invoice_res = await db.execute(text("""
            DELETE FROM payment_attempts WHERE email = :bot_email
        """), {"bot_email": bot_email_alias})

        # Чистим юзера
        result = await db.execute(text("DELETE FROM users WHERE tg_user_id = :id RETURNING id"), {"id": tg_user_id})
        deleted_db = (result.rowcount > 0) or (invoice_res.rowcount > 0)
        await db.commit()

    return {"status": "deleted", "user_id": user_id, "deleted_db": deleted_db, "deleted_hiddify": deleted_hf}


@router.get("/pay/info/{order_id}")
async def admin_pay_info(order_id: str, db: AsyncSession = Depends(get_db)):
    """Получить детальный статус инвойса из абстрактной платежной системы."""
    result = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == order_id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Инвойс не найден")

    invoice_info = {
        "order_id": str(payment.id),
        "gateway_status": payment.status,
        "local_status": payment.status,
        "local_amount": payment.amount,
        "email": payment.email,
        "tariff_slug": payment.tariff_slug,
        "checked_at": datetime.utcnow().isoformat()
    }
    return invoice_info


@router.post("/fix/sync")
async def fix_sync_hiddify(db: AsyncSession = Depends(get_db)):
    """Синхронизация статусов с Hiddify: исправление расхождений тумблеров."""
    provisioner = HiddifyProvisioner()
    mismatches = await _get_status_mismatches(db)

    fixed = 0
    for m in mismatches:
        if m["action"] == "enable":
            success = await provisioner.enable_user(m["uuid"])
        else:
            success = await provisioner.disable_user(m["uuid"])
        if success:
            fixed += 1
    return {"status": "success", "fixed_hiddify_statuses": fixed}


@router.post("/fix/process-pending")
async def fix_process_pending(db: AsyncSession = Depends(get_db)):
    """Фоновая обработка очереди зависших provisioning подписок."""
    manager = ProvisioningManager(db)
    processed = await manager.process_pending_provisioning(limit=20)
    return {"status": "ok", "processed": processed}


@router.post("/fix/cleanup-invoices")
async def fix_cleanup_invoices(db: AsyncSession = Depends(get_db)):
    """Очистка старых неоплаченных инвойсов старше 48 часов (для cron)."""
    result = await db.execute(text("""
        DELETE FROM payment_attempts
        WHERE status = 'pending' AND created_at < NOW() - INTERVAL '48 hours'
    """))
    await db.commit()
    return {"status": "ok", "deleted": result.rowcount}


@router.post("/notify-expiring")
async def notify_expiring_subscriptions(db: AsyncSession = Depends(get_db)):
    """Отправляет уведомления пользователям с истекающей подпиской (1-3 дня)."""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    for days in range(1, 4):
        target_date = datetime.utcnow() + timedelta(days=days)
        result = await db.execute(text("""
            SELECT u.tg_user_id, u.tg_username, s.expires_at, s.tariff_slug
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id IS NOT NULL
              AND s.status = 'active'
              AND DATE(s.expires_at) = DATE(:target_date)
        """), {"target_date": target_date})

        for row in result.fetchall():
            tg_id, username, expires_at, tariff = row
            expires_str = expires_at.strftime("%d.%m.%Y") if expires_at else "N/A"

            msg_text = None
            if days == 1:
                msg_text = f"🔴 *Подписка истекает завтра!*\n\n📅 Дата: {expires_str}\n⚠️ Продлите доступ, чтобы не потерять соединение."
            elif days == 2:
                msg_text = f"🟡 *Подписка истекает через 2 дня*\n\n📅 Дата: {expires_str}\n🔔 Рекомендуем продлить доступ."
            else:
                msg_text = f"🟢 *Подписка истекает через 3 дня*\n\n📅 Дата: {expires_str}\n💡 Ещё есть время продлить."

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(f"https://telegram.org{bot_token}/sendMessage", json={
                        "chat_id": tg_id,
                        "text": msg_text,
                        "parse_mode": "Markdown"
                    })
                logger.info(f"✅ Уведомление отправлено tg_id={tg_id} (истекает через {days} дн.)")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки tg_id={tg_id}: {e}")

    return {"status": "ok", "message": "Expiring notifications sent"}
