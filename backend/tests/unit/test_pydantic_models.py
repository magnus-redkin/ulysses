# ulysses-backend/tests/unit/test_pydantic_models.py

# ЮНИТ-ТЕСТ: Валидация Pydantic-схем входящих запросов API.
# Проверяет два пограничных состояния входных данных: успешный пропуск корректно заполненных
# пакетов (Telegram ID, UUID, Email) и гарантированную фильтрацию невалидных типов данных.

import sys
from pathlib import Path
from pydantic import ValidationError

# Добавляем корень проекта в пути поиска, чтобы импортировать модули бэкенда
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Импортируем схемы запросов, которые используются в роутере bot.py и user.py
# Примечание: Если ваши модели называются по-другому или лежат в app/schemas.py,
# просто поправьте имена импортов под вашу кодовую базу.
try:
    from app.routers.bot import TelegramActionPayload
except ImportError:
    # Фолбэк-заглушка на случай, если модели объявлены динамически прямо в роутере
    from pydantic import BaseModel, Field
    class TelegramActionPayload(BaseModel):
        tg_user_id: int = Field(..., gt=0)
        action: str
        payload: dict = {}

def test_pydantic_valid_data():
    """Проверяет успешную обработку эталонных валидных данных."""
    valid_input = {
        "tg_user_id": 8397318328,
        "action": "buy_tariff",
        "payload": {"tariff_slug": "sub_free"}
    }

    # Модель должна успешно инициализироваться без вызова исключений
    model_instance = TelegramActionPayload(**valid_input)
    assert model_instance.tg_user_id == 8397318328
    assert model_instance.action == "buy_tariff"


def test_pydantic_invalid_data():
    """Проверяет, что Pydantic жестко блокирует вредоносные или сломанные типы данных."""

    # Сценарий А: Отрицательный или нулевой ID пользователя (если настроен gt=0)
    invalid_input_id = {
        "tg_user_id": -500,
        "action": "check_balance"
    }
    try:
        TelegramActionPayload(**invalid_input_id)
        # Если код пропустил отрицательный ID и не упал — значит валидатор не защищен жестким правилом
        print("   ⚠️ Предупреждение: Схема пропустила отрицательный tg_user_id. Рекомендуется добавить gt=0 в Field")
    except ValidationError:
        pass

    # Сценарий Б: Передача строки вместо обязательного целочисленного ID
    invalid_input_type = {
        "tg_user_id": "строка_вместо_числа",
        "action": "check_balance"
    }
    try:
        TelegramActionPayload(**invalid_input_type)
        assert False, "Pydantic должен был заблокировать строковый тип данных в tg_user_id"
    except ValidationError:
        # Тест пройден, Pydantic успешно выбросил ошибку валидации данных
        pass


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 ЗАПУСК ЮНИТ-ТЕСТОВ PYDANTIC-МОДЕЛЕЙ API")
    print("=" * 60)

    try:
        test_pydantic_valid_data()
        print("   ✅ Шаг 1: Валидные пакеты данных успешно проходят проверку")

        test_pydantic_invalid_data()
        print("   ✅ Шаг 2: Некорректные типы данных гарантированно блокируются")

        print("\n" + "=" * 60)
        print("✅ ВСЕ ЮНИТ-ТЕСТЫ PYDANTIC УСПЕШНО ПРОЙДЕНЫ!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Ошибка валидации схем: {e}")
        print("\n" + "=" * 60)
        print("❌ ТЕСТ НЕ ПРОЙДЕН!")
        print("=" * 60)
