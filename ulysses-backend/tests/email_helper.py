# tests/email_helper.py
"""
Модуль для тестирования отправки писем.
Использует EmailService и настройки из .env.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

# Загружаем .env
import tests.set_env

from app.email_service import email_service
from app.config import settings

async def test_welcome_email_template():
    """Тест шаблона приветственного письма"""
    print("=" * 60)
    print("📧 Тест шаблона приветственного письма")
    print("=" * 60)

    test_email = "test@example.com"
    test_uuid = "test-uuid-123"

    subject, html, text = email_service.get_welcome_email(test_email, test_uuid)

    print(f"✅ Тема: {subject}")
    print(f"✅ HTML: {len(html)} символов")
    print(f"✅ Текст: {len(text)} символов")

    # Проверяем наличие всех ссылок
    checks = [
        # ("Ссылка Hiddify", "hiddify" in html.lower()),
        ("Личный кабинет", "ulysses.best/users" in html),
        ("Telegram бот", "t.me" in html),
        ("Кнопка копирования", "navigator.clipboard" in html),
        ("Инструкция", "Быстрый старт" in html),
    ]

    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"   {status} {name}")

    return True

async def test_send_real_email():
    """Отправка реального тестового письма"""
    print("\n📤 Отправка тестового письма...")

    if not settings.SMTP_PASS:
        print("❌ SMTP не настроен (нет пароля в .env)")
        return False

    print(f"   От: {settings.SMTP_FROM}")
    print(f"   Кому: {settings.SMTP_USER} (тестовое)")

    success = await email_service.send_email(
        to_email=settings.SMTP_USER,
        subject="🔧 Ulysses: Тест email сервиса",
        html_body="""
        <h2>✅ Тест email сервиса Ulysses</h2>
        <p>Если вы получили это письмо, значит:</p>
        <ul>
            <li>SMTP сервер работает</li>
            <li>Логин/пароль правильные</li>
            <li>Email сервис настроен верно</li>
        </ul>
        <p><small>Это автоматическое тестовое письмо.</small></p>
        """,
        text_body="Тест email сервиса Ulysses. Если вы получили это - всё работает!"
    )

    if success:
        print(f"✅ Письмо успешно отправлено!")
        return True
    else:
        print("❌ Не удалось отправить письмо")
        print("   Проверьте:")
        print("   1. SMTP сервер доступен")
        print("   2. Логин и пароль в .env правильные")
        print("   3. Порт не заблокирован")
        return False

async def test_send_to_custom_email(email: str):
    """Отправка тестового письма на указанный адрес"""
    print(f"\n📤 Отправка тестового письма на {email}...")

    success = await email_service.send_email(
        to_email=email,
        subject="🧪 Ulysses: Тестовое письмо",
        html_body="<h2>Тестовое письмо от Ulysses Lab</h2><p>Проверка доставки.</p>",
        text_body="Тестовое письмо от Ulysses Lab. Проверка доставки."
    )

    if success:
        print(f"✅ Доставлено на {email}")
        return True
    else:
        print(f"❌ Ошибка доставки на {email}")
        return False

if __name__ == "__main__":
    import sys

    print("🧪 Тестирование Email сервиса Ulysses\n")

    # Всегда тестируем шаблон
    asyncio.run(test_welcome_email_template())

    # Если передан email - отправляем на него
    if len(sys.argv) > 1:
        asyncio.run(test_send_to_custom_email(sys.argv[1]))
    else:
        # Иначе тестируем отправку на себя
        asyncio.run(test_send_real_email())
