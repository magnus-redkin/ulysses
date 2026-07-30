from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging
import httpx
import uuid  # <-- ИСПРАВЛЕНО
from datetime import datetime, timezone  # <-- ИСПРАВЛЕНО
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.config import settings
from app.bot_messages import get_message
from app.dependencies import verify_api_key
from app.services.billing_service import create_invoice_logic  # <-- ДОБАВЛЕНО для оптимизации

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot"])

class BotRegisterSchema(BaseModel):
    tg_user_id: int
    tg_username: str

class BotActionSchema(BaseModel):
    tg_user_id: int
    action: str
    payload: Optional[dict] = None


def format_balance_from_state(balance: dict) -> str:
    """Форматирование баланса из данных бэкенда в чистый HTML."""
    t = balance.get("traffic", {})
    status = "🟢 Активна" if balance.get("is_active") else "🔴 Приостановлена"
    pct = t.get("percent", 0)
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    return (
        f"📊 <b>Статус подписки</b>\n\n"
        f"Статус: {status}\n"
        f"📧 <code>{balance.get('email', '')}</code>\n\n"
        f"📈 Трафик:\n<code>{bar}</code> {pct:.1f}%\n"
        f"• Использовано: <b>{t.get('used_gb', 0):.2f} ГБ</b>\n"
        f"• Осталось: <b>{t.get('remaining_gb', 0):.2f} ГБ</b>\n"
        f"• Всего: <b>{t.get('total_gb', 0):.1f} ГБ</b>\n\n"
        f"⏳ Дней осталось: <b>{balance.get('days_left', 0)}</b>"
    )


@router.get("/state")
async def get_bot_state(
    tg_user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Возвращает состояние бота и приветственное сообщение."""
    result = await db.execute(
        text("""
            SELECT s.status, s.expires_at
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id
            ORDER BY s.expires_at DESC
            LIMIT 1
        """),
        {"tg_id": tg_user_id}
    )
    row = result.fetchone()
    if not row:
        return {
            "state": "new",
            "message": get_message("welcome_new"),
            "keyboard": "tariffs"
        }

    db_status, db_expires_at = row
    # ИСПРАВЛЕНО: Безопасный datetime.now с таймзоной UTC
    now = datetime.now(timezone.utc)
    days_left = 0
    if db_expires_at:
        # Приводим к aware datetime для безопасного вычитания
        expires_aware = db_expires_at if db_expires_at.tzinfo else db_expires_at.replace(tzinfo=timezone.utc)
        days_left = max(0, (expires_aware - now).days)

    is_active = db_status in ["active", "provisioning"] and days_left > 0

    if is_active and days_left > 5:
        return {"state": "active", "message": get_message("welcome_active"), "keyboard": "active"}
    if is_active and days_left == 0:
        return {"state": "expiring_today", "message": get_message("welcome_expiring_today"), "keyboard": "renew"}
    if is_active and days_left <= 5:
        return {"state": "expiring", "message": get_message("welcome_expiring", days=days_left), "keyboard": "renew"}

    return {"state": "expired", "message": get_message("welcome_expired"), "keyboard": "renew"}


@router.post("/register")
async def bot_register_user(
    payload: BotRegisterSchema,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Мягкая регистрация пользователя в БД с автоматической генерацией UUID."""
    res = await db.execute(
        text("SELECT id FROM users WHERE tg_user_id = :tg_id"),
        {"tg_id": payload.tg_user_id}
    )
    if not res.fetchone():
        # ИСПРАВЛЕНО: Генерируем UUID прямо при первичной регистрации в Telegram боте!
        new_hiddify_uuid = str(uuid.uuid4())
        default_email = f"tg_{payload.tg_user_id}@ulysses.internal"

        await db.execute(
            text("""
                INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, email, created_at, updated_at)
                VALUES (:tg_id, :username, :uuid, :email, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "tg_id": payload.tg_user_id,
                "username": payload.tg_username.lstrip("@"),
                "uuid": new_hiddify_uuid,
                "email": default_email
            }
        )
        await db.commit()
        logger.info(f"👤 Зарегистрирован новый пользователь бота: {payload.tg_user_id} с UUID: {new_hiddify_uuid}")
        return {"status": "registered", "created": True}
    return {"status": "exists", "created": False}


@router.post("/action")
async def bot_action(
    payload: BotActionSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Проксирует действия бота к бизнес-логике."""
    tg_user_id = payload.tg_user_id
    action = payload.action
    data = payload.payload or {}

    if action == "buy_tariff":
        tariff_slug = data.get("tariff_slug")
        currency = data.get("currency", "RUB")

        if not tariff_slug:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "http://127.0.0.1:8000/api/billing/tariffs",
                    headers={"X-API-Key": settings.HOST_API_KEY}
                )
                if resp.status_code != 200:
                    return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}
                tariffs = resp.json()
            return {
                "state": "tariffs",
                "message": get_message("welcome_new"),
                "keyboard": "tariffs",
                "tariffs": [{"slug": k, "name_ru": v["name_ru"]} for k, v in tariffs.items()]
            }

        # ИСПРАВЛЕНО: Заменен внутренний HTTP запрос на вызов готовой функции create_invoice_logic
        try:
            result = await create_invoice_logic(
                db=db,
                email=None,
                tg_user_id=tg_user_id,
                tariff_slug=tariff_slug,
                currency=currency
            )
        except Exception as e:
            logger.error(f"❌ Ошибка вызова логики инвойса в боте: {e}")
            return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}

        if result.get("status") == "free_tariff":
            message = get_message(
                "free_activated",
                subscription_link=result["subscription_link"],
                expires=result["expires_at"][:10]
            )
            return {"state": "info", "message": message, "keyboard": "back"}

        elif result.get("status") == "payment_required":
            message = get_message(
                "payment_pending",
                order_id=result.get("order_id", ""),
                amount=result.get("amount", 0),
                currency=result.get("currency", "RUB")
            )
            return {"state": "payment_pending", "message": message, "keyboard": "back"}
        else:
            return {"state": "error", "message": result.get("message", get_message("error_unknown")), "keyboard": "back"}

    elif action == "check_balance":
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://127.0.0.1:8000/api/user/balance?tg_user_id={tg_user_id}",
                headers={"X-API-Key": settings.HOST_API_KEY}
            )
            if resp.status_code != 200:
                return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}
            balance_data = resp.json()
        message = format_balance_from_state(balance_data)
        return {"state": "balance", "message": message, "keyboard": "back"}

    elif action in ("show_about", "show_rules", "show_support"):
        return {"state": "info", "message": get_message(action), "keyboard": "back"}

    return {"state": "error", "message": get_message("error_unknown"), "keyboard": "back"}
