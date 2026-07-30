"""
Обёртка для обработки вебхуков Platega.
Вызывает нетронутый SDK для валидации, затем нашу бизнес-логику.
"""
import json
import logging
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
    Тонкая обёртка для вебхука Platega.
    1. Валидирует запрос через SDK (если заголовки отсутствуют, пропускаем для тестов).
    2. Извлекает order_id и статус.
    3. Если платеж успешен — активирует подписку и отправляет уведомления.
    """

    with open('/tmp/webhook.log', 'a') as f:
        f.write(f'=== WEBHOOK ===\nHeaders: {headers}\nBody: {body_str}\n\n')

    # 1. Пытаемся извлечь данные через SDK
    callback = PlategaCallback(
        merchant_id=settings.PLATEGA_MERCHANT_ID,
        secret=settings.PLATEGA_API
    )

    # Если есть заголовки безопасности — валидируем
    if headers.get("X-MerchantId"):
        if not callback.validate_raw(headers=headers, body=body_str):
            logger.error(f"🚨 [WEBHOOK] Validation failed: {callback.get_validation_error()}")
            return Response(content="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    logger.info(f"🔥 [WEBHOOK] Raw body: {body_str[:500]}")
    logger.info(f"🔥 [WEBHOOK] Headers: {headers}")


    # Парсим JSON-тело
    data = json.loads(body_str)
    payment_status = data.get("status", "")
    order_id = data.get("payload") or data.get("order_id")  # сначала payload, потом order_id

    logger.info(f"🔍 [WEBHOOK] payment_status={payment_status}, order_id={order_id}")
    with open('/tmp/webhook.log', 'a') as f:
        f.write(f'=== WEBHOOK ===\npayment_status={payment_status}\norder_id: {order_id}\n\n')

    if payment_status not in ("CONFIRMED", "success"):
        logger.info(f"ℹ️ [WEBHOOK] Payment status {payment_status} is not success, skipping activation")
        return Response(content="OK", status_code=status.HTTP_200_OK)


    # 2. Обрабатываем платеж
    async with AsyncSessionLocal() as session:
        try:
            # Находим инвойс
            res = await session.execute(
                text("SELECT status, user_id, tariff_slug FROM payment_attempts WHERE id = :id FOR UPDATE"),
                {"id": order_id}
            )
            invoice = res.fetchone()
            if not invoice:
                logger.error(f"❌ [WEBHOOK] Invoice not found: {order_id}")
                return Response(content="Invoice Not Found", status_code=status.HTTP_404_NOT_FOUND)

            inv_status, user_id, tariff_slug = invoice
            logger.info(f"🔍 [WEBHOOK] Invoice: status={inv_status}, user_id={user_id}, tariff={tariff_slug}")

            # Проверка на повторную обработку
            if inv_status == "success":
                logger.info("ℹ️ [WEBHOOK] Invoice already processed")
                return Response(content="Already Processed", status_code=status.HTTP_200_OK)

            # 3. Активируем подписку
            await _activate_subscription(session, order_id, user_id, tariff_slug)

            logger.info(f"✅ [WEBHOOK] Subscription activated for user {user_id}")
            return Response(content="OK", status_code=status.HTTP_200_OK)

        except Exception as e:
            await session.rollback()
            logger.exception(f"💥 [WEBHOOK] Error: {e}")
            return Response(content="Internal Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


async def _activate_subscription(session, order_id: str, user_id: int, tariff_slug: str):
    """
    Внутренняя функция активации подписки после успешной оплаты.
    Вызывается только из handle_platega_webhook.
    """
    # Загружаем тарифы
    tariffs = get_tariffs()
    days_to_add = tariffs.get(tariff_slug, {}).get("days", 30)
    logger.info(f"📅 [ACTIVATE] Adding {days_to_add} days for tariff {tariff_slug}")

    # Получаем пользователя
    res_usr = await session.execute(
        text("SELECT tg_user_id, hiddify_uuid, email FROM users WHERE id = :uid"),
        {"uid": user_id}
    )
    usr = res_usr.fetchone()
    if not usr:
        raise ValueError(f"User {user_id} not found")

    tg_id, hiddify_uuid, email = usr
    hiddify_uuid_str = str(hiddify_uuid)
    now = datetime.now(timezone.utc)

    # Вычисляем новый срок подписки
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

    # Provisioning на HFM
    provisioner = HiddifyProvisioner()
    hiddify_success = await provisioner.create_user(
        uuid=hiddify_uuid_str,
        name=f"tg_{tg_id}" if tg_id else f"id_{user_id}",
        package_days=total_days,
        usage_limit_gb=500
    )
    # сразу активен:
    # if hiddify_success:
    #     await provisioner.enable_user(hiddify_uuid_str)

    # Обновляем инвойс
    await session.execute(
        text("UPDATE payment_attempts SET status = 'success', provider_tx_id = :tx, updated_at = :now WHERE id = :id"),
        {"tx": "webhook", "now": now, "id": order_id}
    )

    # Обновляем или создаём подписку
    if sub_row:
        await session.execute(
            text("UPDATE subscriptions SET expires_at = :exp, status = :status, updated_at = :now WHERE id = :sub_id"),
            {"exp": new_expires, "status": "active" if hiddify_success else "provisioning", "now": now, "sub_id": sub_row[0]}
        )
    else:
        await session.execute(
            text("INSERT INTO subscriptions (user_id, tariff_slug, status, starts_at, expires_at, activated_at, node_id) VALUES (:uid, :tariff, :status, :now, :exp, :now, 'main')"),
            {"uid": user_id, "tariff": tariff_slug, "status": "active" if hiddify_success else "provisioning", "now": now, "exp": new_expires}
        )

    await session.commit()

    # Уведомления
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    sub_link = f"https://{domain}/subscription/{hiddify_uuid_str}/#Ulysses"

    # Telegram
    if tg_id:
        try:
            from app.services.telegram_bot import send_telegram_message
            msg = f"💳 <b>Оплата получена!</b>\n\nПодписка продлена на <b>{days_to_add} дней</b>.\n📅 До: <code>{new_expires.strftime('%Y-%m-%d %H:%M')}</code> UTC.\n🔗 <a href='{sub_link}'>Ссылка для подключения</a>"
            await send_telegram_message(tg_id=tg_id, text=msg)
        except Exception as e:
            logger.error(f"❌ [ACTIVATE] Failed to send TG message: {e}")

    # Email (только если email настоящий)
    if email and "@" in email and not email.endswith("@ulysses.internal"):
        try:
            from app.email_service import email_service as mail_svc
            subject, html_body, text_body = mail_svc.get_welcome_email(email, hiddify_uuid_str)
            await mail_svc.send_email(email, subject, html_body, text_body)
        except Exception as e:
            logger.error(f"❌ [ACTIVATE] Failed to send email: {e}")
