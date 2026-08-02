# app/services/activation_manager.py

"""
Менеджер активации — единая точка работы с пользователями и подписками.
"""
import uuid as uuid_lib
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config import settings

import json
from pathlib import Path


logger = logging.getLogger(__name__)

async def get_or_create_user(
    db: AsyncSession,
    email: str = None,
    tg_user_id: int = None
) -> dict:
    if not email and not tg_user_id:
        raise ValueError("Необходимо указать email или tg_user_id")

    row = None
    # 1. Ищем по tg_user_id
    if tg_user_id:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE tg_user_id = :tg_id"),
            {"tg_id": tg_user_id}
        )
        row = res.fetchone()

    # 2. Ищем по email (если по tg_id не нашли)
    if not row and email:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE email = :email"),
            {"email": email}
        )
        row = res.fetchone()

    # ИСПРАВЛЕНО: Если пользователь есть, но у него БИТЫЙ/ПУСТОЙ UUID (как у нашего голубчика)
    if row:
        user_id, hiddify_uuid, current_email, current_tg_id = row

        if not hiddify_uuid:
            new_uuid = str(uuid_lib.uuid4())
            logger.warning(f"⚠️ У пользователя ID {user_id} отсутствует UUID. Исправляем на: {new_uuid}")
            await db.execute(
                text("UPDATE users SET hiddify_uuid = :uuid, updated_at = NOW() WHERE id = :uid"),
                {"uuid": new_uuid, "uid": user_id}
            )
            await db.flush() # Синхронизируем изменения без закрытия транзакции
            hiddify_uuid = new_uuid

        return {
            "user_id": user_id,
            "hiddify_uuid": hiddify_uuid,
            "email": current_email,
            "tg_user_id": current_tg_id
        }

    # 3. Создаем абсолютно нового, если не нашли вообще (код остается прежним)
    new_uuid = str(uuid_lib.uuid4())
    if not email and tg_user_id:
        email = f"tg_{tg_user_id}@ulysses.internal"
    elif not email:
        email = f"user_{new_uuid[:8]}@ulysses.internal"

    try:
        sql_user = """
            INSERT INTO users (email, hiddify_uuid, tg_user_id, created_at, updated_at)
            VALUES (:email, :uuid, :tg_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """
        res_user = await db.execute(
            text(sql_user),
            {"email": email, "uuid": new_uuid, "tg_id": tg_user_id}
        )
        user_id = res_user.scalar_one()
        # await db.commit()
        await db.flush()
        logger.info(f"👤 Создан новый пользователь: id={user_id}, uuid={new_uuid}")
        return {
            "user_id": user_id,
            "hiddify_uuid": new_uuid,
            "email": email,
            "tg_user_id": tg_user_id
        }
    except IntegrityError:
        await db.rollback()
        # Email уже существует – находим существующего и обновляем tg_user_id
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE email = :email"),
            {"email": email}
        )
        row = res.fetchone()
        if not row:
            raise RuntimeError(f"Unexpected IntegrityError for {email}")
        if tg_user_id and not row[3]:
            await db.execute(
                text("UPDATE users SET tg_user_id = :tg_id, updated_at = CURRENT_TIMESTAMP WHERE id = :uid"),
                {"tg_id": tg_user_id, "uid": row[0]}
            )
            await db.commit()
        return {
            "user_id": row[0],
            "hiddify_uuid": row[1],
            "email": email,
            "tg_user_id": tg_user_id or row[3]
        }

async def get_or_create_subscription(
    db: AsyncSession,
    user: dict,
    tariff_slug: str
) -> dict:
    """
    Проверить возможность активации тарифа для пользователя.
    Возвращает словарь со статусом:
      - already_active: есть активная подписка (любая)
      - free_available: можно активировать sub_free (первая подписка)
      - free_already_used: sub_free уже использован или есть другие подписки
      - requires_payment: требуется оплата (платный тариф)
    """
    user_id = user["user_id"]

    # 1. Проверяем, есть ли активная подписка (любая)
    active_sub = await db.execute(
        text("""
            SELECT id, tariff_slug, expires_at FROM subscriptions
            WHERE user_id = :uid AND status = 'active' AND expires_at > NOW()
            ORDER BY expires_at DESC LIMIT 1
        """),
        {"uid": user_id}
    )
    active_row = active_sub.fetchone()
    if active_row:
        return {
            "status": "already_active",
            "subscription": {
                "id": active_row[0],
                "tariff_slug": active_row[1],
                "expires_at": active_row[2].isoformat() if active_row[2] else None
            }
        }

    # 2. Для sub_free: проверяем, была ли у пользователя хоть одна подписка
    if tariff_slug == "sub_free":
        any_sub = await db.execute(
            text("""
                SELECT id FROM subscriptions WHERE user_id = :uid LIMIT 1
            """),
            {"uid": user_id}
        )
        if any_sub.fetchone():
            return {"status": "free_already_used"}
        else:
            return {"status": "free_available"}

    # 3. Платный тариф — требуется оплата
    return {"status": "requires_payment"}


def get_tariffs():
    """Кеширующее чтение тарифов из JSON-конфига."""
    if not hasattr(get_tariffs, "_cache"):
        tariffs_path = Path(__file__).parent.parent / "tariffs.json"
        with open(tariffs_path, "r", encoding="utf-8") as f:
            get_tariffs._cache = json.load(f)
    return get_tariffs._cache
