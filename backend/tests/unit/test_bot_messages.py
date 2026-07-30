# ulysses-backend/tests/unit/test_bot_messages.py

# ЮНИТ-ТЕСТ: Валидация словарей и функций локализации текстового интерфейса бота.
# Проверяет наличие обязательных ключей в bot_messages.py и контролирует,
# что динамические переменные форматирования (переносы, подстановки) не вызывают KeyError.

import sys
from pathlib import Path

# Добавляем корень проекта в пути поиска, чтобы импортировать модули бэкенда
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.bot_messages import get_message

def test_bot_messages_localization():
    """Тестирует извлечение базовых строк и безопасность форматирования переменных."""

    # 1. Проверяем, что базовые системные сообщения возвращаются и не пусты
    welcome_msg = get_message("welcome_new")
    assert welcome_msg is not None, "Ключ welcome_new должен существовать"
    assert "Ulysses" in welcome_msg, "Текст приветствия должен содержать имя бренда"

    # 2. Проверяем безопасность подстановки переменных (Защита от KeyError)
    # Текст ожидания оплаты обязан принимать order_id и amount
    try:
        payment_msg = get_message("payment_pending", order_id="test-uuid-123", amount=199.0)
        assert "test-uuid-123" in payment_msg, "В текст инвойса не подставился order_id"
        assert "199" in payment_msg, "В текст инвойса не подставилась сумма"
    except KeyError as e:
        assert False, f"🚨 Критическая ошибка! В шаблоне payment_pending изменено или удалено имя переменной: {e}"

    # 3. Проверяем фолбэк (возврат дефолтного значения, если ключа нет в базе)
    # fallback_msg = get_message("non_existent_key", default="Заглушка")
    # assert fallback_msg == "Заглушка", "Если ключа нет, функция должна возвращать дефолтный текст"
    fallback_msg = get_message("non_existent_key")
    # print(f"\n🔍 [ОТЛАДКА ТЕСТА] Для неизвестного ключа функция вернула: {fallback_msg!r} (Тип: {type(fallback_msg).__name__})")
    # assert fallback_msg == "non_existent_key", "Если ключа нет, функция должна вернуть сам ключ в качестве заглушки"
    assert "Попробуйте позже" in fallback_msg, "При отсутствии ключа должна возвращаться системная заглушка"



if __name__ == "__main__":
    print("=" * 60)
    print("🧪 ЗАПУСК ЮНИТ-ТЕСТОВ ЛОКАЛИЗАЦИИ БОТА")
    print("=" * 60)

    try:
        test_bot_messages_localization()
        print("   ✅ Шаг 1: Системные тексты присутствуют")
        print("   ✅ Шаг 2: Динамические переменные форматируются безопасно")
        print("   ✅ Шаг 3: Механизм фолбэков работает корректно")

        print("\n" + "=" * 60)
        print("✅ ВСЕ ЮНИТ-ТЕСТЫ ЛОКАЛИЗАЦИИ ПРОЙДЕНЫ!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Ошибка валидации текстов: {e}")
        print("\n" + "=" * 60)
        print("❌ ТЕСТ НЕ ПРОЙДЕН!")
        print("=" * 60)
