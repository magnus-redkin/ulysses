# app/email_service.py
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
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = None
    ) -> bool:
        """
        Отправка email сообщения (только IPv4).

        Args:
            to_email: Email получателя
            subject: Тема письма
            html_body: HTML версия письма
            text_body: Текстовая версия (если None, не добавляется)

        Returns:
            bool: True если отправлено успешно
        """
        # Формируем сообщение
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_address
        msg["To"] = to_email
        msg["Reply-To"] = "support@ulysses.best"
        msg["Message-ID"] = f"<{uuid.uuid4()}@ulysses.best>"
        msg["Date"] = email_utils.formatdate(localtime=True)

        # HTML версия
        msg.set_content(html_body, subtype="html")

        # Текстовая версия (если есть)
        if text_body:
            msg.add_alternative(text_body, subtype="plain")

        # Порты для перебора
        ports_to_try = []
        if self.smtp_port:
            ports_to_try.append(self.smtp_port)
        for port in [587, 465, 25]:
            if port not in ports_to_try:
                ports_to_try.append(port)

        # Принудительно используем только IPv4
        original_getaddrinfo = socket.getaddrinfo

        def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
            """Резолвим только IPv4 адреса"""
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = getaddrinfo_ipv4

        try:
            for port in ports_to_try:
                try:
                    logger.debug(f"🔄 Пробую {self.smtp_host}:{port} (IPv4)...")

                    if port == 465:
                        # SSL соединение
                        await aiosmtplib.send(
                            msg,
                            hostname=self.smtp_host,
                            port=port,
                            username=self.smtp_user,
                            password=self.smtp_password,
                            use_tls=True,
                            tls_context=self.ssl_context,
                            timeout=15.0,
                            # local_hostname=self.smtp_host
                            local_hostname="mail.ulysses.best"
                        )
                    else:
                        # STARTTLS соединение
                        await aiosmtplib.send(
                            msg,
                            hostname=self.smtp_host,
                            port=port,
                            username=self.smtp_user,
                            password=self.smtp_password,
                            start_tls=True,
                            tls_context=self.ssl_context,
                            timeout=15.0,
                            # local_hostname=self.smtp_host
                            local_hostname="mail.ulysses.best"
                        )

                    logger.info(f"📧 Письмо отправлено на {to_email} (порт {port})")
                    return True

                except Exception as e:
                    error_str = str(e)
                    if "authentication failed" in error_str.lower():
                        logger.error(f"❌ Ошибка аутентификации на порту {port}: {e}")
                        return False
                    else:
                        # logger.debug(f"❌ Порт {port}: {e}")
                        import traceback
                        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА SMTP: {e}")
                        traceback.print_exc() # Выведет полный стек ошибки
                        logger.error(f"Ошибка отправки email: {e}")
                        return False

            logger.error(f"❌ Не удалось отправить письмо на {to_email}")
            return False

        finally:
            # Восстанавливаем оригинальный getaddrinfo
            socket.getaddrinfo = original_getaddrinfo

#     def get_welcome_email_real(self, to_email: str, hiddify_uuid: str) -> tuple:
#         """
#         Приветственное письмо после активации подписки.

#         Args:
#             to_email: Email пользователя
#             hiddify_uuid: UUID для подключения к VPN

#         Returns:
#             tuple: (subject, html_body, text_body)
#         """
#         subscription_link = f"https://vpn.ulysses.best/N0G5SfPATJC3UwW5TRa4tYHUxoMCqk/{hiddify_uuid}/#{to_email}"
#         account_link = f"https://ulysses.best/users/{hiddify_uuid}/"
#         telegram_link = f"https://t.me/ulysses_vpn_bot?start={hiddify_uuid}"

#         subject = "🚀 Ваш доступ к Ulysses VPN успешно активирован!"

#         html_body = f"""
#         <!DOCTYPE html>
#         <html lang="ru">
#             <head><meta charset="UTF-8"></head>
#             <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
#                 <h2 style="color: #2b6cb0;">Добро пожаловать в Лабораторию Улисс!</h2>
#                 <p>Оплата прошла успешно. Ваш персональный защищенный туннель полностью готов к работе.</p>

#                 <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 20px; margin: 20px 0;">
#                     <h3 style="margin-top: 0; color: #166534;">🔗 Ссылка для подключения</h3>
#                     <p style="color: #166534; font-size: 14px;">Скопируйте эту ссылку и вставьте в приложение Hiddify:</p>
#                     <div style="background: white; border: 1px solid #86efac; border-radius: 4px; padding: 12px; word-break: break-all; font-family: monospace; font-size: 13px; color: #166534; margin-bottom: 10px;">
#                         {subscription_link}
#                     </div>
#                 </div>

#                 <div style="background-color: #f7fafc; border-left: 4px solid #2b6cb0; padding: 15px; margin: 20px 0;">
#                     <h3 style="margin-top: 0;">📋 Быстрый старт за 2 минуты:</h3>
#                     <ol style="padding-left: 20px;">
#                         <li style="margin-bottom: 10px;">Скопируйте ссылку подключения выше</li>
#                         <li style="margin-bottom: 10px;">Скачайте приложение <strong>Hiddify App</strong></li>
#                         <li style="margin-bottom: 10px;">Вставьте ссылку в поле "Добавить подписку"</li>
#                     </ol>
#                 </div>

#                 <div style="background-color: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px; padding: 20px; margin: 20px 0;">
#                     <h3 style="margin-top: 0; color: #1e40af;">📊 Ваш личный кабинет</h3>
#                     <p style="color: #1e40af; font-size: 14px;">Информация о подписке доступна по ссылке:</p>
#                     <a href="{account_link}" style="color: #2563eb; word-break: break-all;">{account_link}</a>
#                 </div>

#                 <div style="background-color: #f0f9ff; border: 1px solid #38bdf8; border-radius: 8px; padding: 20px; margin: 20px 0;">
#                     <h3 style="margin-top: 0; color: #0369a1;">🤖 Telegram бот</h3>
#                     <p style="color: #0369a1; font-size: 14px;">Привяжите подписку к Telegram для быстрой проверки баланса:</p>
#                     <a href="{telegram_link}" style="color: #0284c7;">{telegram_link}</a>
#                 </div>

#                 <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
#                 <p style="font-size: 12px; color: #718096; text-align: center;">
#                     Ulysses Lab © 2024-2026<br>
#                     Нужна помощь? Telegram: @ulysses_vpn_bot
#                 </p>
#             </body>
#         </html>
#         """

#         text_body = f"""Добро пожаловать в Ulysses Lab!

# Оплата прошла успешно. Ваш персональный защищенный туннель готов к работе.

# 🔗 Ссылка для подключения (скопируйте и вставьте в Hiddify App):
# {subscription_link}

# 📊 Личный кабинет:
# {account_link}

# 🤖 Telegram бот:
# {telegram_link}

# 📋 Быстрый старт:
# 1. Скопируйте ссылку подключения выше
# 2. Скачайте Hiddify App
# 3. Вставьте ссылку в поле "Добавить подписку"

# 💡 Нужна помощь? Telegram: @ulysses_vpn_bot
# """

#         return subject, html_body, text_body

    # def get_expiring_email(self, to_email: str, days_left: int) -> tuple:
    #     """
    #     Письмо с предупреждением об истечении подписки.

    #     Args:
    #         to_email: Email пользователя
    #         days_left: Осталось дней

    #     Returns:
    #         tuple: (subject, html_body, text_body)
    #     """
    #     if days_left == 1:
    #         day_word = "день"
    #     elif 2 <= days_left <= 4:
    #         day_word = "дня"
    #     else:
    #         day_word = "дней"

    #     subject = f"⏳ Подписка Ulysses VPN истекает через {days_left} {day_word}"

    #     html_body = f"""
    #     <!DOCTYPE html>
    #     <html lang="ru">
    #         <head><meta charset="UTF-8"></head>
    #         <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    #             <h2 style="color: #d97706;">⚠️ Подписка скоро истекает</h2>
    #             <p>Ваша подписка на Ulysses VPN истекает через <strong>{days_left} {day_word}</strong>.</p>
    #             <p>Чтобы не остаться без защиты, продлите подписку:</p>
    #             <a href="https://ulysses.best" style="display: inline-block; background: #d97706; color: white; padding: 12px 24px; border-radius: 4px; text-decoration: none;">Продлить подписку</a>
    #             <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
    #             <p style="font-size: 12px; color: #718096; text-align: center;">
    #                 Ulysses Lab © 2024-2026<br>
    #                 Нужна помощь? Telegram: @ulysses_vpn_bot
    #             </p>
    #         </body>
    #     </html>
    #     """

    #     text_body = f"Ваша подписка Ulysses VPN истекает через {days_left} {day_word}.\nПродлите: https://ulysses.best"

    #     return subject, html_body, text_body

    def get_welcome_email(self, to_email: str, hiddify_uuid: str) -> tuple:
        """
        Приветственное письмо после активации подписки.

        Args:
            to_email: Email пользователя

        Returns:
            tuple: (subject, html_body, text_body)
        """
        subscription_link = f"https://ulysses.best/#{to_email}"
        account_link = f"https://ulysses.best/users/"
        telegram_link = f"https://t.me/ulysses_support_bot"

        subject = "🚀 Ваш доступ к Ulysses Lab успешно активирован!"

        html_body = f"""
        <!DOCTYPE html>
        <html lang="ru">
            <head><meta charset="UTF-8"></head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2b6cb0;">Добро пожаловать в Лабораторию Улисс!</h2>
                <p>Оплата прошла успешно. </p>

                <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #166534;">🔗 Ссылка для подключения</h3>
                    <p style="color: #166534; font-size: 14px;">Скопируйте эту ссылку и вставьте в приложение:</p>
                    <div style="background: white; border: 1px solid #86efac; border-radius: 4px; padding: 12px; word-break: break-all; font-family: monospace; font-size: 13px; color: #166534; margin-bottom: 10px;">
                        {subscription_link}
                    </div>
                </div>

                <div style="background-color: #f7fafc; border-left: 4px solid #2b6cb0; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">📋 Быстрый старт за 2 минуты:</h3>
                </div>

                <div style="background-color: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af;">📊 Ваш личный кабинет</h3>
                    <p style="color: #1e40af; font-size: 14px;">Информация о подписке доступна по ссылке:</p>
                    <a href="{account_link}" style="color: #2563eb; word-break: break-all;">{account_link}</a>
                </div>

                <div style="background-color: #f0f9ff; border: 1px solid #38bdf8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #0369a1;">🤖 Telegram бот</h3>
                    <p style="color: #0369a1; font-size: 14px;">Привяжите подписку к Telegram для быстрой проверки баланса:</p>
                    <a href="{telegram_link}" style="color: #0284c7;">{telegram_link}</a>
                </div>

                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                <p style="font-size: 12px; color: #718096; text-align: center;">
                    Ulysses Lab © 2024-2026<br>
                    Нужна помощь? Telegram: @ulysses_support_bot
                </p>
            </body>
        </html>
        """

        text_body = f"""Добро пожаловать в Ulysses Lab!

Оплата прошла успешно.

🔗 Ссылка для подключения (скопируйте и вставьте в приложение):
{subscription_link}

📊 Личный кабинет:
{account_link}

🤖 Telegram бот:
{telegram_link}

📋 Быстрый старт:
1. Скопируйте ссылку подключения выше
2. Вставьте ссылку в поле "Добавить подписку"

💡 Нужна помощь? Telegram: @ulysses_support_bot
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
