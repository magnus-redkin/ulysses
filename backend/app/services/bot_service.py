# backend/app/services/bot_service.py
"""
Бизнес-логика для Telegram-бота: регистрация, состояние, действия.
"""
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.activation_manager import get_tariffs, get_or_create_user
from app.services.billing_service import create_invoice_logic
from app.services.user_service import get_user_balance

logger = logging.getLogger(__name__)


async def register_user(
    db: AsyncSession,
    tg_user_id: int,
    tg_username: str | None,
    hiddify_uuid: str = None
) -> dict:
    """
    Регистрация пользователя в боте с поддержкой deep linking.
    Если передан UUID — привязать Telegram к существующему профилю.
    """
    # Нормализация username: None / "" / "unknown" / "-" → NULL
    clean_username: str | None = None
    if tg_username:
        candidate = str(tg_username).lstrip("@").strip()
        if candidate and candidate.lower() not in ("unknown", "-"):
            clean_username = candidate

    # 1. Deep link: привязка к существующему профилю по UUID
    if hiddify_uuid:
        clean_uuid = str(hiddify_uuid).strip().lower()
        result = await db.execute(
            text("SELECT id FROM users WHERE hiddify_uuid = :uuid AND tg_user_id IS NULL"),
            {"uuid": clean_uuid}
        )
        existing = result.fetchone()

        if existing:
            await db.execute(
                text("""
                    UPDATE users
                    SET tg_user_id = :tg_id, tg_username = :username, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :db_id
                """),
                {"tg_id": tg_user_id, "username": clean_username, "db_id": existing[0]}
            )
            await db.commit()
            logger.info(f"Linked TG {tg_user_id} to existing user {existing[0]}")
            return {"status": "linked", "created": False}

    # 2. Проверка: существует ли пользователь с таким tg_user_id
    result = await db.execute(
        text("SELECT id FROM users WHERE tg_user_id = :tg_id"),
        {"tg_id": tg_user_id}
    )
    if result.fetchone():
        return {"status": "exists", "created": False}

    # 3. Создание нового пользователя
    new_uuid = str(uuid.uuid4())
    default_email = f"tg_{tg_user_id}@ulysses.internal"

    await db.execute(
        text("""
            INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, email, created_at, updated_at)
            VALUES (:tg_id, :username, :uuid, :email, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """),
        {"tg_id": tg_user_id, "username": clean_username, "uuid": new_uuid, "email": default_email}
    )
    await db.commit()
    logger.info(
        f"Created new user {tg_user_id} with UUID {new_uuid}, "
        f"username={clean_username or 'null'}"
    )
    return {"status": "registered", "created": True}


async def get_user_state(db: AsyncSession, tg_user_id: int) -> dict:
    """
    Возвращает текущее состояние подписки пользователя для бота.
    """
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
            "message": "👋 Добро пожаловать! Выберите тариф.",
            "keyboard": "tariffs"
        }

    db_status, db_expires_at = row
    now = datetime.now(timezone.utc)
    days_left = 0

    if db_expires_at:
        expires_aware = db_expires_at if db_expires_at.tzinfo else db_expires_at.replace(tzinfo=timezone.utc)
        days_left = max(0, (expires_aware - now).days)

    is_active = db_status in ["active", "provisioning"] and days_left > 0

    if is_active and days_left > 5:
        return {
            "state": "active",
            "message": "✅ Ваша подписка активна.",
            "keyboard": "active"
        }
    if is_active and days_left <= 5:
        return {
            "state": "expiring",
            "message": f"⏳ Подписка истекает через {days_left} дн.",
            "keyboard": "renew"
        }

    return {
        "state": "expired",
        "message": "🛑 Подписка истекла. Продлите для возобновления.",
        "keyboard": "renew"
    }


async def handle_action(db: AsyncSession, tg_user_id: int, action: str, payload: dict) -> dict:
    """
    Обработка действий пользователя: buy_tariff, check_balance.
    """
    if action == "buy_tariff":
        tariff_slug = payload.get("tariff_slug")
        payment_type = payload.get("payment_type")

        if not tariff_slug:
            tariffs = get_tariffs()
            return {
                "state": "tariffs",
                "message": "Выберите тариф:",
                "keyboard": "tariffs",
                "tariffs": [{"slug": k, "name_ru": v.get("name_ru", k)} for k, v in tariffs.items()]
            }

        if not payment_type:
            return {
                "state": "select_payment_type",
                "message": "💳 Выберите способ оплаты:",
                "keyboard": "inline",
                "buttons": [
                    {"text": "🇷🇺 Карты РФ / СБП", "action": "buy_tariff", "payload": {"tariff_slug": tariff_slug, "payment_type": "rub"}},
                    {"text": "🇪🇺 Зарубежные карты", "action": "buy_tariff", "payload": {"tariff_slug": tariff_slug, "payment_type": "valuta"}},
                    {"text": "🪙 Криптовалюта", "action": "buy_tariff", "payload": {"tariff_slug": tariff_slug, "payment_type": "crypto"}}
                ]
            }

        currency_map = {"rub": "RUB", "valuta": "USD", "crypto": "USDT"}
        selected_currency = currency_map.get(payment_type, "RUB")

        try:
            result = await create_invoice_logic(
                db=db,
                email=None,
                tg_user_id=tg_user_id,
                tariff_slug=tariff_slug,
                currency=selected_currency
            )
        except Exception as e:
            logger.error(f"create_invoice_logic error: {e}")
            await db.rollback()
            return {"state": "error", "message": "Ошибка создания инвойса", "keyboard": "back"}

        if result.get("status") == "free_tariff":
            return {
                "state": "info",
                "message": "🎉 Бесплатный тариф активирован!",
                "keyboard": "back"
            }
        elif result.get("status") == "payment_required":
            return {
                "state": "payment_pending",
                "message": f"💳 К оплате: {result.get('amount')} {result.get('currency')}",
                "keyboard": "inline",
                "buttons": [
                    {"text": "Перейти к оплате", "url": result.get("payment_url")},
                    {"text": "⬅️ Назад", "action": "buy_tariff", "payload": {}}
                ]
            }
        else:
            return {
                "state": "error",
                "message": result.get("message", "Неизвестная ошибка"),
                "keyboard": "back"
            }

    elif action == "check_balance":
        balance = await get_user_balance(db, tg_user_id=tg_user_id)
        if not balance:
            return {"state": "error", "message": "Ошибка получения баланса", "keyboard": "back"}

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

    return {"state": "error", "message": "Неизвестное действие", "keyboard": "back"}
