import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.config import settings
from app.bot_messages import get_message
from app.dependencies import verify_api_key
from app.services.billing_service import create_invoice_logic
from app.services.activation_manager import get_tariffs

from app.services.user_service import get_user_balance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot"])

# ============================================================
# PYDANTIC МОДЕЛИ ВАЛИДАЦИИ ВХОДЯЩИХ ДАННЫХ ОТ БОТА
# ============================================================

class BotRegisterSchema(BaseModel):
    tg_user_id: int = Field(..., description="Уникальный Telegram ID пользователя")
    tg_username: str = Field(..., description="Юзернейм пользователя без символа @")
    hiddify_uuid: Optional[str] = None

class BotActionSchema(BaseModel):
    tg_user_id: int = Field(..., description="Telegram ID инициатора действия")
    action: str = Field(..., description="Тип действия (buy_tariff, check_balance и т.д.)")
    payload: Optional[dict] = Field(None, description="Дополнительные мета-данные запроса")


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕУТИЛИТЫ ФОРМАТИРОВАНИЯ ИНТЕРФЕЙСА
# ============================================================

def format_balance_from_state(balance: dict) -> str:
    """Форматирование телеметрии и баланса трафика из бэкенда в чистый HTML для Telegram."""
    t = balance.get("traffic", {})
    status = "🟢 Активна" if balance.get("is_active") else "🔴 Приостановлена"
    pct = t.get("percent", 0)

    # Визуальный индикатор остатка трафика (Progress Bar)
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


# ============================================================
# ЭНДПОИНТЫ УПРАВЛЕНИЯ СОСТОЯНИЕМ ТЕЛЕГРАМ-БОТА
# ============================================================

@router.get("/state")
async def get_bot_state(
    tg_user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Возвращает текущую фазу жизненного цикла подписки пользователя для переключения экранов меню."""
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
    now = datetime.now(timezone.utc)
    days_left = 0

    if db_expires_at:
        # Приведение даты из БД к формату aware datetime с таймзоной UTC для безопасного вычитания
        expires_aware = db_expires_at if db_expires_at.tzinfo else db_expires_at.replace(tzinfo=timezone.utc)
        days_left = max(0, (expires_aware - now).days)

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

@router.post("/register")
async def bot_register_user(
    payload: BotRegisterSchema,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Регистрация пользователя в боте с поддержкой глубокого связывания (Deep Linking).
    Приоритет 1: Если передан UUID, связываем ТГ-аккаунт с сайтовым профилем.
    """
    clean_username = payload.tg_username.lstrip("@").strip()

    # 1. Сначала проверяем, передал ли бот UUID из ссылки в письме
    if hasattr(payload, "hiddify_uuid") and payload.hiddify_uuid:
        clean_uuid = str(payload.hiddify_uuid).strip().lower()

        # Ищем в БД сайтовую запись по UUID, у которой еще нет привязанного Telegram ID
        check_uuid_res = await db.execute(
            text("SELECT id FROM users WHERE hiddify_uuid = :uuid AND tg_user_id IS NULL"),
            {"uuid": clean_uuid}
        )
        existing_profile = check_uuid_res.fetchone()

        if existing_profile:
            db_id = existing_profile[0]

            # Привязываем ваш Telegram ID прямо в эту сайтовую запись
            await db.execute(
                text("""
                    UPDATE users
                    SET tg_user_id = :tg_id, tg_username = :username, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :db_id
                """),
                {
                    "tg_id": payload.tg_user_id,
                    "username": clean_username,
                    "db_id": db_id
                }
            )
            await db.commit()
            logger.info(f"🔗 [УСПЕХ] Профили соединены! Telegram {payload.tg_user_id} связан с сайтовой записью ID {db_id}")
            return {"status": "linked", "created": False}

    # 2. Стандартный сценарий (обычный старт бота в поиске без реферального UUID)
    res = await db.execute(
        text("SELECT id FROM users WHERE tg_user_id = :tg_id"),
        {"tg_id": payload.tg_user_id}
    )

    if not res.fetchone():
        # Если пользователя вообще нет – создаем автономный ТГ-профиль
        new_hiddify_uuid = str(uuid.uuid4())
        default_email = f"tg_{payload.tg_user_id}@ulysses.internal"

        await db.execute(
            text("""
                INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, email, created_at, updated_at)
                VALUES (:tg_id, :username, :uuid, :email, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "tg_id": payload.tg_user_id,
                "username": clean_username,
                "uuid": new_hiddify_uuid,
                "email": default_email
            }
        )
        await db.commit()
        logger.info(f"👤 Создан новый автономный пользователь бота: {payload.tg_user_id} с UUID: {new_hiddify_uuid}")
        return {"status": "registered", "created": True}

    return {"status": "exists", "created": False}


@router.post("/action")
async def bot_action(
    payload: BotActionSchema,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Диспетчер обработки интерактивных кнопок и команд главного меню бота."""
    tg_user_id = payload.tg_user_id
    action = payload.action
    data = payload.payload or {}

    # --- Сценарий покупки / Продления тарифа ---
    if action == "buy_tariff":
        tariff_slug = data.get("tariff_slug")
        payment_type = data.get("payment_type") # rub, valuta, crypto

        # Если слаг тарифа отсутствует, отдаем структурированный список доступных планов
        if not tariff_slug:
            tariffs = get_tariffs()
            return {
                "state": "tariffs",
                "message": get_message("welcome_new"),
                "keyboard": "tariffs",
                "tariffs": [{"slug": k, "name_ru": v["name_ru"]} for k, v in tariffs.items()]
            }

        # Шаг А: Сценарий разводки платежных шлюзов (если способ оплаты еще не выбран)
        if not payment_type:
            return {
                "state": "select_payment_type",
                "message": "💳 <b>Выберите удобный способ оплаты:</b>\n\n<i>Для карт банков РФ и СБП выбирайте рубли. Для зарубежных карт или криптовалют — соответствующие шлюзы.</i>",
                "keyboard": "inline",
                "buttons": [
                    {"text": "🇷🇺 Карты РФ / СБП (RUB)", "action": "buy_tariff", "payload": {"tariff_slug": tariff_slug, "payment_type": "rub"}},
                    {"text": "🇪🇺 Зарубежные карты (USD/EUR)", "action": "buy_tariff", "payload": {"tariff_slug": tariff_slug, "payment_type": "valuta"}},
                    {"text": "🪙 Криптовалюта (USDT/TON)", "action": "buy_tariff", "payload": {"tariff_slug": tariff_slug, "payment_type": "crypto"}}
                ]
            }

        # Шаг Б: Преобразование пользовательского выбора в строковую валюту биллинга
        currency_map = {
            "rub": "RUB",
            "valuta": "USD",
            "crypto": "USDT"
        }
        selected_currency = currency_map.get(payment_type, "RUB")

        # Прямой асинхронный вызов логики биллинга без паразитного HTTP-трафика на localhost
        try:
            result = await create_invoice_logic(
                db=db,
                email=None,
                tg_user_id=tg_user_id,
                tariff_slug=tariff_slug,
                currency=selected_currency
            )
        except Exception as e:
            logger.error(f"❌ Критический сбой при вызове create_invoice_logic внутри роутера бота: {e}")
            return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}

        # Шаг В: Обработка результатов расчета тарификации

        if result.get("status") == "free_tariff":
            # Активирован бесплатный тариф (sub_free), выдаем готовую ссылку VPN
            message = get_message(
                "free_activated",
                subscription_link=result["subscription_link"],
                expires=result["expires_at"][:10] if result.get("expires_at") else ""
            )
            return {
                "state": "info",
                "message": message,
                "keyboard": "back"
            }

        elif result.get("status") == "payment_required":
            # Требуется оплата платного тарифа через один из шлюзов Platega
            payment_url = result.get("payment_url")
            amount = result.get("amount", 0)
            currency_label = result.get("currency", "RUB")
            order_id = result.get("order_id", "")

            # Генерируем локализованный текст для пользователя в зависимости от валюты шлюза
            if currency_label == "USDT":
                gateway_desc = "🪙 Криптовалютный инвойс (USDT TRC-20)"
            elif currency_label in ("USD", "EUR"):
                gateway_desc = "🇪🇺 Форма оплаты международной картой (Visa/Mastercard)"
            else:
                gateway_desc = "🇷🇺 Система Быстрых Платежей (СБП) / Карта РФ"

            message = get_message(
                "payment_pending",
                order_id=str(order_id),
                amount=f"{amount:.2f}",
                currency=currency_label
            )

            # Дописываем к дефолтному сообщению тип выбранного шлюза для прозрачности интерфейса
            message += f"\n\n<b>Шлюз процессинга:</b> {gateway_desc}"

            return {
                "state": "payment_pending",
                "message": message,
                "keyboard": "inline",
                "buttons": [
                    {"text": "💳 Перейти к оплате", "url": payment_url},
                    {"text": "⬅️ Назад в меню", "action": "buy_tariff", "payload": {}}
                ]
            }

        else:
            # Неизвестный или ошибочный статус из недр биллинга
            error_msg = result.get("message") or get_message("error_unknown")
            return {
                "state": "error",
                "message": f"❌ {error_msg}",
                "keyboard": "back"
            }

    # ============================================================
    # 🌟 ПРОСМОТР БАЛАНСА И ТРАФИКА
    # ============================================================

    elif action == "check_balance":
        logger.info(f"📊 [БЭКЕНД] Запрос баланса для tg_user_id={tg_user_id}")
        balance = await get_user_balance(db, tg_user_id=tg_user_id)
        if not balance:
            return {"state": "error", "message": get_message("error_api"), "keyboard": "back"}

        return {
            "state": "balance",
            "balance": {
                "is_active": balance["is_active"],
                "email": balance["email"],
                "days_left": balance["days_left"],
                "traffic": balance["traffic"]
            },
            "keyboard": "back"
        }
