"""
Роутер для Telegram-бота.
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import verify_api_key
from app.services.bot_service import register_user, get_user_state, handle_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot"])


class BotRegisterSchema(BaseModel):
    tg_user_id: int = Field(..., description="Telegram ID пользователя")
    tg_username: str = Field(..., description="Юзернейм без @")
    hiddify_uuid: Optional[str] = None


class BotActionSchema(BaseModel):
    tg_user_id: int = Field(..., description="Telegram ID инициатора")
    action: str = Field(..., description="Тип действия")
    payload: Optional[dict] = Field(None, description="Дополнительные данные")


@router.get("/state")
async def bot_state(
    tg_user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Текущее состояние подписки пользователя."""
    return await get_user_state(db, tg_user_id)


@router.post("/register")
async def bot_register(
    payload: BotRegisterSchema,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Регистрация пользователя в боте."""
    return await register_user(
        db,
        tg_user_id=payload.tg_user_id,
        tg_username=payload.tg_username,
        hiddify_uuid=payload.hiddify_uuid
    )


@router.post("/action")
async def bot_action(
    payload: BotActionSchema,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Обработка действий пользователя."""
    return await handle_action(
        db,
        tg_user_id=payload.tg_user_id,
        action=payload.action,
        payload=payload.payload or {}
    )
