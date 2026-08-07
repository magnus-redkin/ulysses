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

    # 1. Сначала ищем существующего пользователя по tg_user_id или email
    row = None
    if tg_user_id:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE tg_user_id = :tg_id"),
            {"tg_id": tg_user_id}
        )
        row = res.fetchone()

    if not row and email:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE email = :email"),
            {"email": email}
        )
        row = res.fetchone()

    # Если нашли — проверяем/исправляем UUID
    if row:
        user_id, hiddify_uuid, current_email, current_tg_id = row

        if not hiddify_uuid:
            new_uuid = str(uuid_lib.uuid4())
            logger.warning(f"⚠️ У пользователя ID {user_id} отсутствует UUID. Исправляем на: {new_uuid}")
            await db.execute(
                text("UPDATE users SET hiddify_uuid = :uuid, updated_at = NOW() WHERE id = :uid"),
                {"uuid": new_uuid, "uid": user_id}
            )
            await db.flush()
            hiddify_uuid = new_uuid

        return {
            "user_id": user_id,
            "hiddify_uuid": hiddify_uuid,
            "email": current_email,
            "tg_user_id": current_tg_id
        }

    # 2. Пользователь не найден — создаём нового через UPSERT
    new_uuid = str(uuid_lib.uuid4())
    if not email and tg_user_id:
        email = f"tg_{tg_user_id}@ulysses.internal"
    elif not email:
        email = f"user_{new_uuid[:8]}@ulysses.internal"

    # Атомарный upsert: если за время поиска другой поток уже вставил такой email,
    # мы обновим tg_user_id и получим существующую запись без ошибки IntegrityError.
    sql_upsert = """
        INSERT INTO users (email, hiddify_uuid, tg_user_id, created_at, updated_at)
        VALUES (:email, :uuid, :tg_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (email) DO UPDATE
            SET tg_user_id = COALESCE(users.tg_user_id, EXCLUDED.tg_user_id),
                updated_at = CASE
                    WHEN users.tg_user_id IS NULL AND EXCLUDED.tg_user_id IS NOT NULL
                    THEN CURRENT_TIMESTAMP
                    ELSE users.updated_at
                END
        RETURNING id, hiddify_uuid, email, tg_user_id
    """
    res = await db.execute(
        text(sql_upsert),
        {"email": email, "uuid": new_uuid, "tg_id": tg_user_id}
    )
    user_id, hiddify_uuid, current_email, current_tg_id = res.fetchone()

    logger.info(f"👤 Пользователь upsert: id={user_id}, uuid={hiddify_uuid}")
    return {
        "user_id": user_id,
        "hiddify_uuid": hiddify_uuid,
        "email": current_email,
        "tg_user_id": current_tg_id
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
