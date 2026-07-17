# ulysses-backend/app/routers/bot.py

import uuid as uuid_lib
from pydantic import BaseModel
from app.database import get_db

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
import logging

from app.database import get_db
from app.config import settings
# Импортируйте функцию get_message и другие хелперы, если они объявлены в app
from app.bot_messages import get_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot"])

# Создаем легкую изолированную схему без лишних полей
class BotRegisterSchema(BaseModel):
    tg_user_id: int
    tg_username: str


@router.get("/state")
async def get_bot_state(
    tg_user_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Возвращает состояние бота и приветственное сообщение."""
    result = await db.execute(text("""
        SELECT s.status, s.expires_at
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.tg_user_id = :tg_id
        ORDER BY s.expires_at DESC
        LIMIT 1
    """), {"tg_id": tg_user_id})
    row = result.fetchone()

    if not row:
        return {
            "state": "new",
            "message": get_message("welcome_new"),
            "keyboard": "tariffs"
        }

    db_status, db_expires_at = row
    now = datetime.utcnow()
    days_left = 0
    if db_expires_at:
        expires_naive = db_expires_at.replace(tzinfo=None) if db_expires_at.tzinfo else db_expires_at
        days_left = max(0, (expires_naive - now).days)

    is_active = db_status in ["active", "provisioning"] and days_left > 0

    if is_active and days_left > 5:
        return {
            "state": "active",
            "message": get_message("welcome_active"),
            "keyboard": "active"
        }

    if is_active and days_left == 0:
        return {
            "state": "expiring_today",
            "message": get_message("welcome_expiring_today"),
            "keyboard": "renew"
        }

    if is_active and days_left <= 5:
        return {
            "state": "expiring",
            "message": get_message("welcome_expiring", days=days_left),
            "keyboard": "renew"
        }

    return {
        "state": "expired",
        "message": get_message("welcome_expired"),
        "keyboard": "renew"
    }


@router.post("/action")
async def bot_action(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Единый эндпоинт для всех действий бота."""
    tg_user_id = payload.get("tg_user_id")
    action = payload.get("action")
    data = payload.get("payload", {})

    if not tg_user_id or not action:
        raise HTTPException(status_code=400, detail="tg_user_id and action required")

    #
    from app.services.provisioning_manager import (
        _action_buy_tariff,
        _action_check_balance,
        _action_show_about,
        _action_show_rules,
        _action_show_support
    )


    actions = {
        "buy_tariff": _action_buy_tariff,
        "check_balance": _action_check_balance,
        "show_about": _action_show_about,
        "show_rules": _action_show_rules,
        "show_support": _action_show_support,
    }

    handler = actions.get(action)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    return await handler(tg_user_id, data, db, background_tasks)

@router.post("/register")
async def bot_register_user(payload: BotRegisterSchema, db: AsyncSession = Depends(get_db)):
    """🌟 МЯГКАЯ РЕГИСТРАЦИЯ: Гарантирует наличие пользователя в БД без ошибок 400."""
    logger.info(f"👤 [API РЕГИСТРАЦИЯ] Получен запрос от бота для TG ID {payload.tg_user_id}")

    res = await db.execute(text("SELECT id FROM users WHERE tg_user_id = :tg_id"), {"tg_id": payload.tg_user_id})
    if not res.fetchone():
        new_uuid = uuid_lib.uuid4()
        sql_insert = """
            INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
            VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        await db.execute(text(sql_insert), {"tg_id": payload.tg_user_id, "username": payload.tg_username, "uuid": new_uuid})
        await db.commit()
        logger.info(f"👤 [API РЕГИСТРАЦИЯ] Пользователь {payload.tg_user_id} занесен в PostgreSQL.")
        return {"status": "registered", "created": True}

    return {"status": "exists", "created": False}
