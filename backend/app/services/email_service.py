# app/services/email_service.py
"""
Сервис отправки email для Ulysses Lab.
Содержит все шаблоны писем и логику отправки.
"""
import uuid
import ssl
import socket
import logging
from email.message import EmailMessage
import email.utils as email_utils
import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Сервис отправки email уведомлений"""

    def __init__(self):
        # Используем настройки из .env
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASS
        self.from_address = settings.SMTP_FROM

        logger.info(f"📧 Email сервис: {self.smtp_user}@{self.smtp_host}:{self.smtp_port}")

        # SSL контекст
        # self.ssl_context = ssl.create_default_context()
        # self.ssl_context.check_hostname = False
        # self.ssl_context.verify_mode = ssl.CERT_NONE

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = None
    ) -> bool:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_address
        msg["To"] = to_email
        msg["Reply-To"] = "support@ulysses.best"
        msg["Message-ID"] = f"<{uuid.uuid4()}@ulysses.best>"
        msg["Date"] = email_utils.formatdate(localtime=True)

        msg.set_content(html_body, subtype="html")
        if text_body:
            msg.add_alternative(text_body, subtype="plain")

        ports_to_try = []
        if self.smtp_port:
            ports_to_try.append(self.smtp_port)
        for port in [587, 465, 25]:
            if port not in ports_to_try:
                ports_to_try.append(port)

        try:
            for port in ports_to_try:
                try:
                    # Инициализируем низкоуровневый SMTP-клиент с принудительным IPv4
                    smtp_client = aiosmtplib.SMTP(
                        hostname=self.smtp_host,
                        port=port,
                        use_tls=(port == 465),
                        start_tls=(port != 465),
                        # tls_context=self.ssl_context,
                        timeout=15.0,
                        local_hostname="mail.ulysses.best",
                        source_address=("0.0.0.0", 0)  # Жесткая изоляция сокета на IPv4
                    )

                    # Выполняем асинпо цепочке действий
                    async with smtp_client:
                        if self.smtp_user and self.smtp_password:
                            await smtp_client.login(self.smtp_user, self.smtp_password)
                        await smtp_client.send_message(msg)

                    logger.info(f"📧 Письмо успешно отправлено на {to_email} через порт {port}")
                    return True

                except Exception as e:
                    error_str = str(e).lower()
                    if "authentication failed" in error_str:
                        logger.error(f"❌ Ошибка аутентификации на порту {port}: {e}")
                        break
                    else:
                        logger.debug(f"Порт {port} не подошёл: {e}")
                        continue


        except Exception as global_e:
            logger.error(f"❌ Глобальная ошибка в методе отправки: {global_e}")

        logger.error(f"❌ Не удалось отправить письмо на {to_email}")
        return False



    def get_welcome_email(self, to_email: str, hiddify_uuid: str) -> tuple:
        domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
        subscription_link = f"https://{domain}/subscription/{hiddify_uuid}/#Ulysses"
        account_link = f"https://ulysses.best/account/{hiddify_uuid}"
        telegram_bot_link = f"https://t.me/ulysses_vpn_bot?start={hiddify_uuid}"

        subject = "Ulysses Lab — ваш доступ активирован"

        html_body = f"""\
        <html>
        <head><meta charset="UTF-8"></head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px;">
        <p>Здравствуйте!</p>
        <p>Ваш доступ к Ulysses Lab активирован.</p>

        <p>🔗 <strong>Ссылка для подключения:</strong><br>
        <a href="{subscription_link}">{subscription_link}</a></p>

        <p>📊 <strong>Личный кабинет:</strong><br>
        <a href="{account_link}">{account_link}</a></p>

        <p>🤖 <strong>Поддержка в Telegram:</strong><br>
        <a href="{telegram_bot_link}">Написать боту</a></p>

        <p>Инструкция: скопируйте ссылку подключения и вставьте в приложение Hiddify Next.</p>

        <p style="color: #888; font-size: 12px; text-align: center;">
        Ulysses Lab<br>
        Вся поддержка — в Telegram-боте.
        </p>
        </body>
        </html>
        """

        text_body = f"""\
        Здравствуйте!

        Ваш доступ к Ulysses Lab активирован.

        🔗 Ссылка для подключения:
        {subscription_link}

        📊 Личный кабинет:
        {account_link}

        🤖 Поддержка в Telegram:
        {telegram_bot_link}

        Инструкция: скопируйте ссылку и вставьте в Hiddify Next.
        """
        return subject, html_body, text_body

    def get_expiring_email(self, to_email: str, days_left: int) -> tuple:
        """
        Письмо с предупреждением об истечении подписки.

        Args:
            to_email: Email пользователя
            days_left: Осталось дней

        Returns:
            tuple: (subject, html_body, text_body)
        """
        if days_left == 1:
            day_word = "день"
        elif 2 <= days_left <= 4:
            day_word = "дня"
        else:
            day_word = "дней"

        subject = f"⏳ Подписка Ulysses Lab истекает через {days_left} {day_word}"

        html_body = f"""
        <!DOCTYPE html>
        <html lang="ru">
            <head><meta charset="UTF-8"></head>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #d97706;">⚠️ Подписка скоро истекает</h2>
                <p>Ваша подписка на Ulysses Lab истекает через <strong>{days_left} {day_word}</strong>.</p>
                <p>Чтобы не остаться без защиты, продлите подписку:</p>
                <a href="https://ulysses.best" style="display: inline-block; background: #d97706; color: white; padding: 12px 24px; border-radius: 4px; text-decoration: none;">Продлить подписку</a>
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                <p style="font-size: 12px; color: #718096; text-align: center;">
                    Ulysses Lab © 2024-2026<br>
                    Нужна помощь? Telegram: @ulysses_support_bot
                </p>
            </body>
        </html>
        """

        text_body = f"Ваша подписка Ulysses Lab истекает через {days_left} {day_word}.\nПродлите: https://ulysses.best"

        return subject, html_body, text_body


# Глобальный экземпляр сервиса
email_service = EmailService()
