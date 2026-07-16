# ulysses-backend/app/routers/user.py

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
import httpx
import logging
from typing import Optional

from app.database import get_db
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])

# ============================================================
# PYDANTIC МОДЕЛИ (Перенесены из main.py для изоляции)
# ============================================================

class TelegramLinkPayload(BaseModel):
    uuid: UUID = Field(..., description="Hiddify UUID подписки пользователя")
    tg_user_id: int = Field(..., description="Telegram User ID")
    tg_username: Optional[str] = Field(None, description="Telegram никнейм без @")

class LinkTelegramRequest(BaseModel):
    tg_user_id: int = Field(..., description="Telegram User ID для разлогина")
    uuid: Optional[str] = Field(None, description="Резервное поле")


# ============================================================
# ЭНДПОИНТЫ ПРОФИЛЯ И БАЛАНСА
# ============================================================

@router.get("/balance")
async def get_user_balance(
    tg_user_id: int = Query(None, description="Telegram user ID"),
    hiddify_uuid: str = Query(None, description="Hiddify UUID"),
    email: str = Query(None, description="User email"),
    username: str = Query(None, description="Telegram username"),
    db: AsyncSession = Depends(get_db)
):
    uuid = None
    email_db = None
    db_expires_at = None
    db_status = None
    user_id = None
    tg_id_db = None
    tg_username_db = None

    # 1. Поиск по Telegram Username
    if username:
        clean_username = str(username).lower().replace("@", "").strip()
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE LOWER(u.tg_username) = :username
            ORDER BY s.expires_at DESC LIMIT 1
        """), {"username": clean_username})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]) if row[0] else None, row[1], row[2], row[3], row[4], row[5], row[6]

    # 2. Поиск по email
    elif email:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE LOWER(u.email) = :email
            ORDER BY s.expires_at DESC LIMIT 1
        """), {"email": str(email).lower().strip()})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]) if row[0] else None, row[1], row[2], row[3], row[4], row[5], row[6]

    # 3. Поиск по hiddify_uuid
    elif hiddify_uuid:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE CAST(u.hiddify_uuid AS TEXT) = :uuid
            ORDER BY s.expires_at DESC LIMIT 1
        """), {"uuid": str(hiddify_uuid).lower().strip()})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]) if row[0] else None, row[1], row[2], row[3], row[4], row[5], row[6]

    # 4. Поиск по tg_user_id
    elif tg_user_id:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id
            ORDER BY s.expires_at DESC LIMIT 1
        """), {"tg_id": tg_user_id})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]) if row[0] else None, row[1], row[2], row[3], row[4], row[5], row[6]

    if not uuid:
        raise HTTPException(status_code=404, detail="Subscription not found")

    now = datetime.utcnow()
    days_left = 0
    if db_expires_at:
        expires_naive = db_expires_at.replace(tzinfo=None) if db_expires_at.tzinfo else db_expires_at
        days_left = max(0, (expires_naive - now).days)

    traffic_data = {"used_gb": 0.0, "total_gb": 0.0, "remaining_gb": 0.0, "percent": 0.0}
    is_active = (db_status in ["active", "provisioning"]) and days_left > 0

    # Запрос живых данных из Hiddify API
    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                for u in response.json():
                    if str(u.get("uuid", "")).lower() == uuid.lower():
                        usage = float(u.get("current_usage_GB", 0))
                        total = float(u.get("usage_limit_GB", 0))
                        is_active = bool(u.get("enable", True)) and days_left > 0
                        traffic_data = {
                            "used_gb": round(usage, 2),
                            "total_gb": round(total, 2),
                            "remaining_gb": round(max(0.0, total - usage), 2),
                            "percent": round((usage / total * 100) if total > 0 else 0, 1)
                        }
                        break
    except Exception as e:
        logger.error(f"❌ Hiddify API Error in user/balance: {e}")

    return {
        "status": "active" if is_active else "disabled",
        "email": email_db if email_db else "Бот (Без почты)",
        "uuid": uuid, "traffic": traffic_data, "days_left": days_left, "is_active": is_active,
        "admin_info": {"id": user_id, "tg_user_id": tg_id_db, "tg_username": tg_username_db}
    }


@router.post("/link-telegram")
async def link_telegram_account(
    payload: TelegramLinkPayload,
    db: AsyncSession = Depends(get_db)
):
    """Привязка Telegram аккаунта к пользователю на основе UUID его подписки."""
    sub_result = await db.execute(text("""
        SELECT u.id AS user_id, s.id AS sub_id, s.status
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE CAST(u.hiddify_uuid AS TEXT) = :uuid
        ORDER BY s.created_at DESC LIMIT 1
    """), {"uuid": str(payload.uuid).lower()})
    sub_row = sub_result.fetchone()

    if not sub_row:
        raise HTTPException(status_code=404, detail="User with this VPN token not found")

    user_id, sub_id, current_status = sub_row[0], sub_row[1], sub_row[2]

    # Сбрасываем этот tg_user_id у других записей, если он был занят
    await db.execute(text("""
        UPDATE users SET tg_user_id = NULL, tg_username = NULL WHERE tg_user_id = :tg_id AND id != :user_id
    """), {"tg_id": payload.tg_user_id, "user_id": user_id})

    # Привязываем Telegram данные к целевому пользователю
    await db.execute(text("""
        UPDATE users SET tg_user_id = :tg_id, tg_username = :tg_username WHERE id = :user_id
    """), {"tg_id": payload.tg_user_id, "tg_username": payload.tg_username, "user_id": user_id})

    # Если подписка в статусе provisioning — переводим в active
    if sub_id and current_status == "provisioning":
        await db.execute(text("UPDATE subscriptions SET status = 'active' WHERE id = :sub_id"), {"sub_id": sub_id})

    await db.commit()
    logger.info(f"✅ Telegram ID {payload.tg_user_id} успешно привязан к user_id {user_id}")
    return {"status": "success", "message": "Telegram account linked successfully"}


@router.post("/unlink-telegram")
async def unlink_telegram_account(
    payload: LinkTelegramRequest,
    db: AsyncSession = Depends(get_db)
):
    """Удаление привязки Telegram-аккаунта (разлогин из бота)."""
    logger.info(f"🚪 [LOGOUT] Запрос на отвязку Telegram ID: {payload.tg_user_id}")
    await db.execute(text("""
        UPDATE users SET tg_user_id = NULL, tg_username = NULL WHERE tg_user_id = :tg_id
    """), {"tg_id": payload.tg_user_id})
    await db.commit()
    logger.info(f"✅ Telegram ID {payload.tg_user_id} успешно отвязан от всех профилей.")
    return {"status": "success", "message": "Logged out successfully"}
