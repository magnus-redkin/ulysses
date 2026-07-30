# app/services/billing_service.py
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import PaymentAttempt
from app.services.activation_manager import get_or_create_user, get_or_create_subscription, get_tariffs
from app.services.free_subscription import create_free_subscription
from app.platega.platega_service import PlategaPaymentService

logger = logging.getLogger(__name__)

async def create_invoice_logic(
    db: AsyncSession,
    email: str | None,
    tg_user_id: int | None,
    tariff_slug: str,
    currency: str | None = None
) -> dict:
    """Бизнес-логика создания инвойса (общая для бота и веба)."""
    tariffs = get_tariffs()
    tariff_config = tariffs.get(tariff_slug)
    if not tariff_config:
        raise ValueError("Tariff not found")

    amount = float(tariff_config["price"])
    currency = currency or "RUB"

    # 2. Пользователь
    user = await get_or_create_user(
        db,
        email=email,
        tg_user_id=tg_user_id
    )

    logger.info(f"DEBUG user from get_or_create_user 1: {user}")

    # 3. Проверяем возможность активации
    sub_check = await get_or_create_subscription(db, user, tariff_slug)

    if sub_check["status"] == "already_active":
        return {
            "status": "error",
            "message": "У вас уже есть активная подписка",
            "expires_at": sub_check["subscription"]["expires_at"]
        }

    if sub_check["status"] == "free_already_used":
        return {
            "status": "error",
            "message": "Бесплатный тариф можно активировать только один раз"
        }

    # 4. Бесплатный тариф – активация
    if sub_check["status"] == "free_available":
        logger.info(f"DEBUG user from get_or_create_user 2: {user}")

        result = await create_free_subscription(db, user)
        return {
            "status": "free_tariff",
            "subscription_link": result["subscription_link"],
            "expires_at": result["expires_at"],
            "order_id": None
        }


    # 5. Платный тариф – создаём инвойс и ссылку на оплату
    if sub_check["status"] == "requires_payment":
        logger.info(f"💳 Создание инвойса для user_id={user['user_id']}, тариф={tariff_slug}, сумма={amount} {currency}")

        from decimal import Decimal
        amount_decimal = Decimal(str(tariff_config["price"]))

        # 🌟 1. МАТРИЦА СИНХРОНИЗАЦИИ ШЛЮЗОВ PLATEGA
        VALUTA_METHOD_MAP = {
            "RUB": 2,          # СБП QR
            "USD": 12,         # Международный эквайринг
            "EUR": 12,         # Международный эквайринг
            "USDT": 13,        # Криптовалюта
        }

        # Нормализуем входящую строку валюты от бота
        clean_currency = str(currency).upper().strip() if currency else "RUB"

        # Вычисляем целевой ID метода Platega (если пусто или сбой, откатываемся на СБП = 2)
        selected_method = VALUTA_METHOD_MAP.get(clean_currency, 2)
        logger.info(f"🎯 Вычислен метод процессинга Platega: №{selected_method} для валюты {clean_currency}")

        new_attempt = PaymentAttempt(
            id=uuid.uuid4(),
            email=user.get("email") or f"tg_{tg_user_id}@ulysses.internal",
            tariff_slug=tariff_slug,
            amount=amount_decimal,
            currency=clean_currency,
            status="pending",
            user_id=user["user_id"]
        )
        db.add(new_attempt)
        await db.commit()

        # 🌟 2. ИСПРАВЛЕНО: Передаем currency и method в SDK Platega!
        pay_service = PlategaPaymentService()
        invoice_data = await pay_service.create_invoice_link(
            amount=amount,
            attempt_id=str(new_attempt.id),
            tariff_name=tariff_slug,
            currency=clean_currency,  # Пробрасываем вычисленную валюту
            method=selected_method    # Пробрасываем точный ID шлюза (2, 12 или 13)
        )
        logger.info(f"Platega response (динамический шлюз): {invoice_data}")

        if invoice_data and "redirect" in invoice_data:
            payment_url = invoice_data["redirect"]
        else:
            logger.error(f"❌ Platega не вернул ссылку для {new_attempt.id}")
            raise RuntimeError("Platega unavailable")

        return {
            "status": "payment_required",
            "payment_url": payment_url,
            "order_id": str(new_attempt.id),
            "amount": amount,
            "currency": clean_currency
        }
