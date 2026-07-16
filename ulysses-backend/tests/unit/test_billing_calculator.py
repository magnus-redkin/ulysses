# ulysses-backend/tests/unit/test_billing_calculator.py

# ЮНИТ-ТЕСТ: Проверка калькулятора дат биллинга и алгоритма суммирования дней подписки.
# Тестирует два сценария: активацию тарифа с текущего момента для нового клиента
# и корректное прибавление дней к дате окончания для уже существующей активной подписки.

import pytest
from datetime import datetime, timedelta

def calculate_subscription_dates(last_expires_at: datetime | None, days_to_add: int) -> tuple[datetime, datetime]:
    """
    Чистая функция калькулятора дат (дублирует бизнес-логику из ProvisioningManager).
    Принимает дату окончания текущей подписки и количество добавляемых дней.
    Возвращает кортеж (дата_начала, дата_окончания).
    """
    now = datetime.utcnow()

    # Сценарий 1: Если активной подписки нет или она истекла, старт с текущей секунды
    if not last_expires_at or last_expires_at.replace(tzinfo=None) <= now:
        starts_at = now
    # Сценарий 2: Если есть активная подписка, старт строго в секунду окончания старой
    else:
        starts_at = last_expires_at.replace(tzinfo=None)

    expires_at = starts_at + timedelta(days=days_to_add)
    return starts_at, expires_at


def test_calculate_dates_for_new_user():
    """Проверка калькуляции дат для нового пользователя без активной подписки."""
    days_to_add = 30
    now_before = datetime.utcnow()

    starts_at, expires_at = calculate_subscription_dates(last_expires_at=None, days_to_add=days_to_add)
    now_after = datetime.utcnow()

    # Проверяем, что дата начала лежит в промежутке выполнения функции
    assert now_before <= starts_at <= now_after
    # Проверяем, что срок действия увеличился ровно на 30 дней
    assert expires_at == starts_at + timedelta(days=days_to_add)


def test_calculate_dates_for_active_user_extension():
    """Проверка алгоритма суммирования дней подписки для постоянного клиента."""
    days_to_add = 90
    # Создаем фиктивную старую подписку, которая истечет только через 15 дней
    future_expiration = datetime.utcnow() + timedelta(days=15)

    starts_at, expires_at = calculate_subscription_dates(last_expires_at=future_expiration, days_to_add=days_to_add)

    # Новая подписка должна начаться строго в момент окончания старой подписки (защита от потери дней)
    assert starts_at == future_expiration
    # Итоговая дата окончания должна увеличиться ровно на 90 дней от старого лимита
    assert expires_at == future_expiration + timedelta(days=days_to_add)
    # Суммарный остаток дней у пользователя должен составить ровно 15 + 90 = 105 дней
    assert (expires_at - datetime.utcnow()).days == 104  # 104 полных дня, так как секунды текущего момента текут вперед

# Допишите в самый конец файла test_billing_calculator.py для совместимости с utest

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 ЗАПУСК ЮНИТ-ТЕСТОВ КАЛЬКУЛЯТОРА ДАТ")
    print("=" * 60)

    try:
        test_calculate_dates_for_new_user()
        print("   ✅ Шаг 1: Новый пользователь расчитан верно")

        test_calculate_dates_for_active_user_extension()
        print("   ✅ Шаг 2: Продление дней суммировано верно")

        print("\n" + "=" * 60)
        print("✅ ВСЕ ЮНИТ-ТЕСТЫ КАЛЬКУЛЯТОРА ПРОЙДЕНЫ!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Ошибка валидации: {e}")
        print("\n" + "=" * 60)
        print("❌ ТЕСТ НЕ ПРОЙДЕН!")
        print("=" * 60)
