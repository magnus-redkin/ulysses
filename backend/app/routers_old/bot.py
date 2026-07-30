# ulysses-backend/app/routers/bot.py (новый, упрощённый)
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging
import httpx
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.config import settings
from app.bot_messages import get_message

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/bot", tags=["bot"])
class BotRegisterSchema(BaseModel):
    tg_user_id: int
    tg_username: str

class BotActionSchema(BaseModel):
    tg_user_id: int
    action: str
    payload: Optional[dict] = None

@router.get("/state")
async def get_bot_state(
    tg_user_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Возвращает состояние бота и приветственное сообщение (без изменений)."""
    # ... оставляем текущую реализацию ...
    pass  # (здесь будет существующий код, который мы не меняем)

@router.post("/register")
async def bot_register_user(payload: BotRegisterSchema, db: AsyncSession = Depends(get_db)):
    # ... существующий код без изменений ...
    pass

@router.post("/action")
async def bot_action(
    payload: BotActionSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Проксирует действия бота к HTTP API бэкенда."""
    tg_user_id = payload.tg_user_id
    action = payload.action
    data = payload.payload or {}

    # --- Покупка тарифа ---
    if action == "buy_tariff":
        tariff_slug = data.get("tariff_slug")
        currency = data.get("currency", "RUB")
        if not tariff_slug:
            # Если тариф не указан, возвращаем список тарифов (как раньше)
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:8000/api/billing/tariffs")
                tariffs = resp.json()
                # Возвращаем state=tariffs, чтобы бот показал клавиатуру
                return {
                    "state": "tariffs",
                    "message": get_message("welcome_new"),
                    "keyboard": "tariffs",
                    "tariffs": [{"slug": k, "name_ru": v["name_ru"]} for k, v in tariffs.items()]
                }

        # Вызываем наш новый create-invoice
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://127.0.0.1:8000/api/billing/create-invoice",
                json={
                    "tg_user_id": tg_user_id,
                    "email": None,
                    "tariff_slug": tariff_slug,
                    "currency": currency
                }
            )
            if resp.status_code != 200:
                return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}

            result = resp.json()

        if result.get("status") == "free_tariff":
            # Бесплатный тариф активирован
            message = get_message("free_activated",
                                  subscription_link=result["subscription_link"],
                                  expires=result["expires_at"][:10])  # только дата
            return {"state": "info", "message": message, "keyboard": "back"}
        elif result.get("status") == "payment_required":
            # Платный тариф — возвращаем ссылку на оплату
            payment_url = result.get("payment_url")
            amount = result.get("amount", 0)
            currency = result.get("currency", "RUB")
            order_id = result.get("order_id", "")
            # Используем шаблон payment_pending с реальной суммой и валютой
            message = get_message("payment_pending",
                                  order_id=order_id,
                                  amount=amount,
                                  currency=currency)
            # Можно добавить кнопку "Оплатить" с ссылкой, но пока оставим просто сообщение
            return {"state": "payment_pending", "message": message, "keyboard": "back"}

            # payment_url = result["payment_url"]
            # message = get_message("payment_pending",
            #                       order_id=result.get("order_id", ""),
            #                       amount=data.get("tariff_slug"))  # временно
            # return {"state": "payment_pending", "message": message, "keyboard": "back"}
        else:
            # Ошибка (уже есть подписка, бесплатный уже использован и т.д.)
            return {"state": "error", "message": result.get("message", get_message("error_unknown")), "keyboard": "back"}

    # --- Проверка баланса ---
    elif action == "check_balance":
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:8000/api/user/balance?tg_user_id={tg_user_id}")
            if resp.status_code != 200:
                return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}
            balance_data = resp.json()

        # Форматируем ответ для бота (можно использовать format_balance_from_state из бота)
        from format_balance import format_balance_from_state  # или оставить в этом же файле
        message = format_balance_from_state(balance_data)
        return {"state": "balance", "message": message, "keyboard": "back"}

    # --- Остальные действия (about, rules, support) ---
    elif action in ("show_about", "show_rules", "show_support"):
        return {
            "state": "info",
            "message": get_message(action),
            "keyboard": "back"
        }

    return {"state": "error", "message": get_message("error_unknown"), "keyboard": "back"}
