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
from app.services.email_service import email_service

from decimal import Decimal

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
    is_free_tariff = amount <= 0

    # 2. Пользователь
    user = await get_or_create_user(
        db,
        email=email,
        tg_user_id=tg_user_id
    )
    logger.info(f"DEBUG user from get_or_create_user: {user}")

    # 3. Проверяем состояние подписок
    sub_check = await get_or_create_subscription(db, user, tariff_slug)

    # ==================================================================
    # 4. БЕСПЛАТНЫЙ ТАРИФ — старая логика (один раз, только без активной)
    # ==================================================================
    if is_free_tariff:
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

        if sub_check["status"] == "free_available":
            result = await create_free_subscription(db, user)

            try:
                to_email = user.get("email")
                if to_email and "@" in to_email and not to_email.endswith(".internal"):
                    subject, html_body, text_body = email_service.get_welcome_email(
                        to_email, user["hiddify_uuid"]
                    )
                    sent = await email_service.send_email(to_email, subject, html_body, text_body)
                    if sent:
                        logger.info(f"📧 Приветственное письмо отправлено на {to_email}")
                    else:
                        logger.warning(f"⚠️ Не удалось отправить письмо на {to_email}")
                else:
                    logger.info(f"ℹ️ Пропуск отправки письма (email={to_email})")
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке приветственного письма: {e}")

            return {
                "status": "free_tariff",
                "hiddify_uuid": user["hiddify_uuid"],
                "simple_link": result["simple_link"],
                "advanced_link": result["advanced_link"],
                "expires_at": result["expires_at"],
                "order_id": None,
            }

        # На всякий случай
        return {
            "status": "error",
            "message": "Не удалось активировать бесплатный тариф"
        }

    # ==================================================================
    # 5. ПЛАТНЫЙ ТАРИФ — всегда создаём инвойс.
    #    Активная подписка (free или paid) НЕ блокирует оплату.
    #    Продление с накоплением срока делает обработчик успешной оплаты.
    # ==================================================================
    pay_service = PlategaPaymentService()

    # 🧪 Тестовый режим Platega: подменяем сумму ДО записи в БД,
    # чтобы вебхук Platega сошёлся с PaymentAttempt.amount.
    amount = pay_service.apply_test_amount(amount, tg_id=tg_user_id)

    logger.info(
        f"💳 Создание инвойса для user_id={user['user_id']}, "
        f"тариф={tariff_slug}, сумма={amount} {currency} "
        f"(sub_check={sub_check['status']})"
    )

    amount_decimal = Decimal(str(amount))

    new_attempt = PaymentAttempt(
        id=uuid.uuid4(),
        email=user.get("email") or f"tg_{tg_user_id}@ulysses.internal",
        tariff_slug=tariff_slug,
        amount=amount_decimal,
        status="pending",
        user_id=user["user_id"]
    )
    db.add(new_attempt)
    await db.commit()

    try:
        invoice_data = await pay_service.create_invoice_link(
            amount=amount,
            attempt_id=str(new_attempt.id),
            tariff_name=tariff_slug,
            currency=currency,
            user_telegram_id=tg_user_id
        )
        logger.info(f"Platega response (динамический шлюз): {invoice_data}")

        if not invoice_data or "url" not in invoice_data:
            raise RuntimeError("Platega returned no URL")

        payment_url = invoice_data["url"]

        # 🆕 Сохраняем Platega transactionId сразу, чтобы потом можно было опросить статус
        new_attempt.provider_tx_id = invoice_data.get("transactionId")
        await db.commit()

    except Exception as e:
            logger.error(f"❌ Platega error for {new_attempt.id}: {e}")
            new_attempt.status = "failed"
            await db.commit()
            raise RuntimeError("Platega unavailable")

    return {
        "status": "payment_required",
        "hiddify_uuid": user["hiddify_uuid"],
        "payment_url": payment_url,
        "order_id": str(new_attempt.id),
        "amount": amount
    }
