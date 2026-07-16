# ulysses-backend/app/tasks/workers.py

import os
import logging
import httpx
from datetime import datetime
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.config import settings
from app.bot_messages import get_message  # Локализация сообщений бота
from app.services.provisioning_manager import ProvisioningManager

logger = logging.getLogger(__name__)

async def provision_and_notify(subscription_id: int, to_email: str, hiddify_uuid: str):
    """
    Изолированная фоновая задача: активация VPN в панели ноды через ProvisioningManager,
    генерация подписочной ссылки и отправка финального уведомления в Telegram API.
    """
    logger.info(f"🔄 [ВОРКЕР] Запуск фоновой задачи для подписки #{subscription_id}")

    async with AsyncSessionLocal() as db:
        try:
            # 1. Активируем подписку в базе и на ноде через наш менеджер
            manager = ProvisioningManager(db)
            success = await manager.provision_subscription(subscription_id)

            if not success:
                logger.warning(f"❌ [ВОРКЕР] Фоновая активация для подписки #{subscription_id} завершилась неудачей")
                return

            # 2. Проверяем источник пользователя (Бот или Сайт)
            if to_email.endswith("@ulysses.internal"):
                logger.info("🤖 [ВОРКЕР] Обнаружен клиент из Telegram-бота. Отправка email отменена.")

                # Получаем данные пользователя для формирования сообщения
                sub_result = await db.execute(text("""
                    SELECT u.tg_user_id, s.tariff_slug, s.expires_at
                    FROM subscriptions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.id = :sub_id LIMIT 1
                """), {"sub_id": subscription_id})
                sub_row = sub_result.fetchone()

                if sub_row:
                    tg_user_id, tariff_slug, expires_at = sub_row
                    expires_str = expires_at.strftime("%d.%m.%Y") if expires_at else "N/A"

                    # Формируем защищенную ссылку подключения к Сердцу (HFM)
                    sub_link = f"https://45.131.215{hiddify_uuid}/"

                    # Сборка текста ответа в зависимости от типа тарифа
                    if tariff_slug in ("sub_free", "tariff_free"):
                        text_msg = (
                            f"🎁 <b>Тестовый период успешно активирован!</b>\n\n"
                            f"Ваш VPN-туннель готов к работе.\n"
                            f"⏳ Доступ активен до: <b>{expires_str}</b>\n\n"
                            f"🔗 Ссылка для подключения (нажмите для копирования):\n"
                            f"<code>{sub_link}</code>\n\n"
                            f"Инструкция: Скопируйте ссылку выше и вставьте её в приложение <b>Hiddify App</b> в поле 'Добавить профиль'."
                        )
                    else:
                        text_msg = (
                            f"🎉 <b>Оплата успешно получена!</b>\n\n"
                            f"Ваша подписка обновлена.\n"
                            f"⏳ Новый срок действия: <b>{expires_str}</b>\n\n"
                            f"🔗 Ваша ссылка для подключения:\n"
                            f"<code>{sub_link}</code>\n\n"
                            f"<i>Если вы уже добавляли этот профиль в приложение, перенастраивать ничего не нужно — конфиги обновятся автоматически!</i>"
                        )

                    # Формируем Inline-клавиатуру
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "📊 Проверить баланс", "callback_data": "action_check_balance"}],
                            [{"text": "✉️ Добавить Email для уведомлений", "callback_data": "action_prompt_add_email"}]
                        ]
                    }

                    # Отправляем сообщение напрямую в Telegram API через чистый HTML
                    bot_token = os.getenv("BOT_TOKEN")
                    if bot_token:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            # 🌟 Исправленный URL: Path-сегмент слит, слэши расставлены корректно
                            tg_url = f"https://api.telegram.org/{bot_token}/sendMessage"
                            payload = {
                                "chat_id": tg_user_id,
                                "text": text_msg,
                                "parse_mode": "HTML",
                                "reply_markup": reply_markup
                            }
                            tg_res = await client.post(tg_url, json=payload)
                            if tg_res.status_code == 200:
                                logger.info(f"✅ [ВОРКЕР] Финальный конфиг доставлен пользователю {tg_user_id} в Telegram")
                            else:
                                logger.error(f"❌ [ВОРКЕР] Сбой отправки сообщения в Telegram API: {tg_res.text}")
                else:
                    logger.error(f"❌ [ВОРКЕР] Не удалось найти связку пользователя для подписки #{subscription_id}")

            else:
                # Сценарий покупки с веб-сайта
                logger.info(f"📧 [ВОРКЕР] Пользователь пришел с сайта. Запуск отправки письма на {to_email}...")
                # На следующих этапах сюда импортируется хелпер send_welcome_email(to_email, hiddify_uuid)

        except Exception as e:
            logger.error(f"🚨 [ВОРКЕР] Критический сбой при выполнении фоновой задачи: {e}", exc_info=True)
