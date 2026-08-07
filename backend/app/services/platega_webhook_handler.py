import json
import logging
import uuid  # <-- ДОБАВЛЕНО для PostgreSQL совместимости
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from fastapi import Response, status

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.hiddify_client import HiddifyProvisioner
from app.platega.platega import PlategaCallback
from app.services.activation_manager import get_tariffs

logger = logging.getLogger(__name__)


async def handle_platega_webhook(headers: dict, body_str: str) -> Response:
    """
    Тонкая защищенная обёртка для вебхука Platega.
    Строго валидирует подпись и исключает состояние гонки в СУБД.
    """
    # Пишем сырые логи для дебага
    # with open('/tmp/webhook.log', 'a') as f:
    #     f.write(f'=== WEBHOOK ===\nHeaders: {headers}\nBody: {body_str}\n\n')

    # ИСПРАВЛЕНО: Приводим ключи заголовков к нижнему регистру для стабильности Fastapi/Nginx
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    callback = PlategaCallback(
        merchant_id=settings.PLATEGA_MERCHANT_ID,
        secret=settings.PLATEGA_API
    )

    # ИСПРАВЛЕНО: Валидация подписи теперь СТРОГО ОБЯЗАТЕЛЬНА. Защита от подделки запросов.
    if not normalized_headers.get("x-merchantid"):
        logger.error("🚨 [WEBHOOK] Критическая уязвимость: Запрос без x-merchantid заблокирован!")
        return Response(content="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    if not callback.validate_raw(headers=headers, body=body_str):
        logger.error(f"🚨 [WEBHOOK] Криптографическая подпись не верна: {callback.get_validation_error()}")
        return Response(content="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    logger.info(f"🔥 [WEBHOOK] Подпись проверена. Тело: {body_str[:500]}")

    # Парсим JSON-тело
    data = json.loads(body_str)
    payment_status = data.get("status", "")
    raw_order_id = data.get("payload") or data.get("order_id")

    if payment_status not in ("CONFIRMED", "success"):
        logger.info(f"ℹ️ [WEBHOOK] Статус {payment_status} не является успешным, пропускаем.")
        return Response(content="OK", status_code=status.HTTP_200_OK)

    # ИСПРАВЛЕНО: Безопасное приведение строки заказа к UUID объекту для PostgreSQL
    try:
        order_uuid = uuid.UUID(str(raw_order_id).strip())
    except (ValueError, TypeError):
        logger.error(f"❌ [WEBHOOK] Неверный формат UUID инвойса: {raw_order_id}")
        return Response(content="Invalid UUID format", status_code=status.HTTP_400_BAD_REQUEST)

    # ФИКС ДЕДЛОКОВ: Быстрая СУБД транзакция (Защита от состояния гонки)
    async with AsyncSessionLocal() as session:
        try:
            res = await session.execute(
                text("SELECT status, user_id, tariff_slug FROM payment_attempts WHERE id = :id FOR UPDATE"),
                {"id": order_uuid}
            )
            invoice = res.fetchone()
            if not invoice:
                logger.error(f"❌ [WEBHOOK] Инвойс не найден в СУБД: {order_uuid}")
                return Response(content="Invoice Not Found", status_code=status.HTTP_404_NOT_FOUND)

            inv_status, user_id, tariff_slug = invoice

            if inv_status == "success":
                logger.info("ℹ️ [WEBHOOK] Инвойс уже был обработан успешно ранее.")
                return Response(content="Already Processed", status_code=status.HTTP_200_OK)

            # Переводим в промежуточный статус и мгновенно коммитим, освобождая СУБД воркеры
            await session.execute(
                text("UPDATE payment_attempts SET status = 'processing', updated_at = NOW() WHERE id = :id"),
                {"id": order_uuid}
            )
            await session.commit() # Мгновенно отпускаем блокировку FOR UPDATE таблицы!

        except Exception as e:
            await session.rollback()
            logger.exception(f"💥 [WEBHOOK СУБД ОШИБКА]: {e}")
            return Response(content="Internal Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ИЗОЛИРОВАННЫЙ КОНТУР: Выполняем активацию за пределами блокировки БД
    try:
        async with AsyncSessionLocal() as session:
            await _activate_subscription(session, order_uuid, user_id, tariff_slug)
        return Response(content="OK", status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"💥 [WEBHOOK АКТИВАЦИЯ ОШИБКА]: {e}")
        return Response(content="Activation Failed", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


async def _activate_subscription(session, order_id: uuid.UUID, user_id: int, tariff_slug: str):
    """Внутренний контур зачисления подписки."""
    tariffs = get_tariffs()
    days_to_add = tariffs.get(tariff_slug, {}).get("days", 30)
    now = datetime.now(timezone.utc)

    res_usr = await session.execute(
        text("SELECT tg_user_id, hiddify_uuid, email FROM users WHERE id = :uid"),
        {"uid": user_id}
    )
    usr = res_usr.fetchone()
    if not usr:
        raise ValueError(f"User {user_id} not found")

    tg_id, hiddify_uuid, email = usr
    hiddify_uuid_str = str(hiddify_uuid)

    res_sub = await session.execute(
        text("SELECT id, expires_at FROM subscriptions WHERE user_id = :uid AND status = 'active' LIMIT 1"),
        {"uid": user_id}
    )
    sub_row = res_sub.fetchone()

    if sub_row and sub_row[1] and sub_row[1] > now:
        new_expires = sub_row[1] + timedelta(days=days_to_add)
    else:
        new_expires = now + timedelta(days=days_to_add)

    total_days = (new_expires - now).days
    if total_days <= 0:
        total_days = days_to_add

    # Запрос к инфраструктуре Hiddify (транзакция выше закрыта, дедлок исключен)
    provisioner = HiddifyProvisioner()
    hiddify_success = await provisioner.create_user(
        uuid=hiddify_uuid_str,
        name=f"tg_{tg_id}" if tg_id else f"id_{user_id}",
        package_days=total_days,
        usage_limit_gb=500
    )

    status_str = "active" if hiddify_success else "provisioning"

    # Фиксируем результаты в СУБД одной короткой транзакцией

    provider_tx_id = data.get("id") or data.get("transactionId", "webhook")
    await session.execute(
            text("UPDATE payment_attempts SET status = 'success', provider_tx_id = :tx, updated_at = NOW() WHERE id = :id"),
    {"tx": provider_tx_id, "id": order_id}
    )

    if sub_row:
        await session.execute(
            text("UPDATE subscriptions SET expires_at = :exp, status = :status, updated_at = NOW() WHERE id = :sub_id"),
            {"exp": new_expires, "status": status_str, "sub_id": sub_row[0]}
        )
    else:
        # ИСПРАВЛЕНО: Переданы абсолютно все параметры, включая node_id, created_at, updated_at, чтобы избежать ошибок NOT NULL ограничений
        await session.execute(
            text("""
                INSERT INTO subscriptions (user_id, tariff_slug, status, starts_at, expires_at, activated_at, node_id, created_at, updated_at)
                VALUES (:uid, :tariff, :status, NOW(), :exp, NOW(), 'main', NOW(), NOW())
            """),
            {"uid": user_id, "tariff": tariff_slug, "status": status_str, "exp": new_expires}
        )

    await session.commit()

    # Блок отправки пушей
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    sub_link = f"https://{domain}/subscription/{hiddify_uuid_str}/#Ulysses"

    if tg_id:
        try:
            from app.services.telegram_bot import send_telegram_message
            msg = f"💳 <b>Оплата получена!</b>\n\nПодписка продлена на <b>{days_to_add} дней</b>.\n📅 До: <code>{new_expires.strftime('%Y-%m-%d %H:%M')}</code> UTC.\n🔗 <a href='{sub_link}'>Ссылка для подключения</a>"
            await send_telegram_message(tg_id=tg_id, text=msg)
        except Exception as e:
            logger.error(f"❌ [ACTIVATE] Failed to send TG message: {e}")


    if email and "@" in email and not email.endswith("@ulysses.internal"):
        try:
            from app.services.email_service import email_service
            subject, html_body, text_body = email_service.get_welcome_email(email, hiddify_uuid_str)
            await email_service.send_email(email, subject, html_body, text_body)
        except Exception as e:
            logger.error(f"❌ [ACTIVATE] Failed to send email: {e}")
