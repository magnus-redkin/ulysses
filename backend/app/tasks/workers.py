# ulysses-backend/app/tasks/workers.py

# АСИНХРОННЫЕ ФОНОВЫЕ ВОРКЕРЫ И ОЧЕРЕДЬ ВЫДАЧИ ДОСТУПА VPN WORKERS
# Модуль инкапсулирует тяжелые фоновые задачи (BackgroundTasks) FastAPI.
# Обеспечивает каскадный провижн: сначала гарантированно создает профиль
# на удаленной ноде Hiddify через API, фиксирует статус в PostgreSQL,
# и только затем отправляет карточку конфигурации в Telegram-чат пользователя.

import logging
import httpx
from datetime import datetime
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.config import settings
from app.services.hiddify_client import HiddifyProvisioner
from app.bot_messages import get_message

logger = logging.getLogger(__name__)


async def provision_and_notify(subscription_id: int, tg_user_id: int, hiddify_uuid: str, expires_at: datetime):
    """
    Фоновый воркер жизненного цикла выдачи услуг.
    Реализует отказоустойчивый конвейер: Провижн в Hiddify -> Фиксация в БД -> Уведомление в TG.
    """
    logger.info(f"🚀 [ВОРКЕР] Начата фоновая обработка подписки #{subscription_id} для TG ID {tg_user_id}")

    expires_str = expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "Не ограничено"
    bot_token = getattr(settings, "BOT_TOKEN", None)

    # Считываем базовый домен ноды для красивой сборки карточки ссылки
    domain = getattr(settings, "HIDDIFY_DOMAIN", None)
    if not domain and hasattr(settings, "HIDDIFY_API_URL"):
        url_parts = settings.HIDDIFY_API_URL.split("/")
        if len(url_parts) > 2:
            domain = url_parts[2]
    domain = domain or "193.188.22.128"

    # Ссылка для импорта в Sing-box/V2ray клиент
    sub_link = f"https://{domain}/X6CbExbUw2/sub/{hiddify_uuid}/"

    # ============================================================
    # ШАГ А: ФИЗИЧЕСКОЕ СОЗДАНИЕ КЛЮЧА В HIDDIFY MANAGER (API НОДЫ V2)
    # ============================================================
    hiddify_success = False
    node_error_msg = None

    try:
        logger.info(f"📡 [ВОРКЕР] Отправка API запроса на создание профиля UUID {hiddify_uuid} в HFM v2...")
        hiddify_client = HiddifyProvisioner()
        response_status = await hiddify_client.create_user(
            uuid=hiddify_uuid,
            name=f"tg_{tg_user_id}"
        )

        if response_status:
            hiddify_success = True
            logger.info(f"✅ [ВОРКЕР] Профиль UUID {hiddify_uuid} успешно активирован в панели HFM v2.")
        else:
            node_error_msg = "Панель Hiddify v2 вернула статус ошибки при создании"
            logger.error(f"⚠️ [ВОРКЕР] Нода отклонила создание профиля.")

    except Exception as hf_err:
        node_error_msg = str(hf_err)
        logger.error(f"💥 [ВОРКЕР] Критический сетевой сбой API Hiddify v2: {hf_err}")

    # ============================================================
    # ШАГ Б: ФИКСАЦИЯ СТАТУСОВ ТРАНЗАКЦИИ В POSTGRESQL
    # ============================================================
    async with AsyncSessionLocal() as session:
        try:
            if hiddify_success:
                sql_update = """
                    UPDATE subscriptions
                    SET status = 'active',
                        activated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP,
                        provisioning_error = NULL
                    WHERE id = :sub_id
                """
                await session.execute(text(sql_update), {"sub_id": subscription_id})
                logger.info(f"💾 [ВОРКЕР] Статус подписки #{subscription_id} обновлен на ACTIVE в PostgreSQL")
            else:
                sql_fail = """
                    UPDATE subscriptions
                    SET status = 'provisioning',
                        provisioning_attempts = provisioning_attempts + 1,
                        provisioning_error = :err_msg,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :sub_id
                """
                await session.execute(text(sql_fail), {"sub_id": subscription_id, "err_msg": node_error_msg[:200]})
                logger.warning(f"💾 [ВОРКЕР] Подписка #{subscription_id} зафиксирована в карантине (provisioning)")

            await session.commit()
        except Exception as db_err:
            await session.rollback()
            logger.error(f"❌ [ВОРКЕР] Ошибка фиксации стейта в БД: {db_err}")

    # ============================================================
    # ШАГ В: ОТПРАВКА УВЕДОМЛЕНИЯ СО ССЫЛКОЙ В TELEGRAM API
    # ============================================================
    if not bot_token:
        logger.error("❌ [ВОРКЕР] Сбой отправки: Параметр settings.BOT_TOKEN не обнаружен!")
        return

    # Собираем чистый HTML шаблон карточки выдачи (Защита от KeyError и Markdown-конфликтов)
    text_msg = (
        f"🎉 <b>Подписка успешно активирована!</b>\n\n"
        f"Ваш персональный VPN-туннель полностью готов к работе.\n"
        f"⏳ Срок действия: до <b>{expires_str}</b>\n\n"
        f"🔗 <b>Ваша ссылка для импорта (нажмите для копирования):</b>\n"
        f"<code>{sub_link}</code>\n\n"
        f"<i>Инструкция: Скопируйте ссылку выше, откройте приложение Hiddify App, нажмите 'Добавить профиль' и вставьте её туда.</i>"
    )

    reply_markup = {
        "inline_keyboard": [
            [{"text": "📊 Проверить баланс", "callback_data": "check_balance"}]
        ]
    }

    try:
        # 🌟 БРОНЕБОЙНЫЙ ВАРИАНТ: Разделяем хост и путь с токеном, чтобы httpx не путал двоеточие с сетевым портом!
        base_tg_host = "https://api.telegram.org"
        target_path = f"/bot{bot_token}/sendMessage"

        logger.info(f"📡 [ВОРКЕР] Отправка карточки в Telegram. Путь: {target_path[:25]}...")

        payload = {
            "chat_id": tg_user_id,
            "text": text_msg,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            tg_res = await client.post(f"{base_tg_host}{target_path}", json=payload)

            if tg_res.status_code == 200:
                logger.info(f"✅ [ВОРКЕР] Ссылка доступа успешно доставлена в чат пользователю {tg_user_id}")
            else:
                logger.error(f"❌ [ВОРКЕР] Сбой отправки сообщения в Telegram API: {tg_res.status_code} - {tg_res.text}")

    except Exception as tg_err:
        logger.error(f"❌ [ВОРКЕР] Критическая ошибка транспорта при отправке в Telegram: {tg_err}")
