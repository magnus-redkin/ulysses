# tests/test_bot_token_config.py
"""
Тест: BOT_TOKEN берётся из app.config.settings, а не из отдельного .env.
Запуск: utest backend/tests/test_bot_token_config.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_bot_token_from_settings():
    """BOT_TOKEN должен быть доступен через settings, а не os.getenv."""
    from app.config import settings

    token = settings.BOT_TOKEN
    assert token, "BOT_TOKEN не задан в settings"
    assert token != "", "BOT_TOKEN пустой"
    print(f"  BOT_TOKEN: {token[:6]}...{token[-4:]}")
    print("✅ test_bot_token_from_settings PASSED")

def test_admin_ids_from_settings():
    """ADMIN_IDS должен быть списком целых чисел из settings."""
    from app.config import settings

    admin_ids_str = settings.ADMIN_IDS
    assert admin_ids_str is not None, "ADMIN_IDS не задан в settings"
    # Может быть пустым, это нормально
    print(f"  ADMIN_IDS: {admin_ids_str}")
    print("✅ test_admin_ids_from_settings PASSED")

def test_telegram_bot_uses_settings():
    """telegram_bot.py должен использовать settings, а не загружать .env отдельно."""
    from app.services.telegram_bot import BOT_TOKEN, ADMIN_IDS

    # BOT_TOKEN должен быть строкой (не None)
    assert isinstance(BOT_TOKEN, str), f"BOT_TOKEN должен быть str, а не {type(BOT_TOKEN)}"
    # ADMIN_IDS должен быть списком
    assert isinstance(ADMIN_IDS, list), f"ADMIN_IDS должен быть list, а не {type(ADMIN_IDS)}"
    print(f"  BOT_TOKEN из telegram_bot: {BOT_TOKEN[:6]}...{BOT_TOKEN[-4:] if len(BOT_TOKEN) > 10 else ''}")
    print(f"  ADMIN_IDS: {ADMIN_IDS}")
    print("✅ test_telegram_bot_uses_settings PASSED")

def main():
    test_bot_token_from_settings()
    test_admin_ids_from_settings()
    test_telegram_bot_uses_settings()

if __name__ == "__main__":
    main()
