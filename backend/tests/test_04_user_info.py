#!/usr/bin/env python3
"""
Тест 04: Информация о пользователе (поиск по разным параметрам)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_email, get_user_balance, cleanup_user, check_anomalies

TEST_EMAIL = f"test_search_{__import__('uuid').uuid4().hex[:8]}@example.com"


async def test_user_info():
    print("=" * 60)
    print("🧪 ТЕСТ 04: Информация о пользователе (поиск)")
    print("=" * 60)

    # 0. Очистка
    print(f"\n🧹 Шаг 0: Очистка...")
    await cleanup_user(email=TEST_EMAIL)
    await asyncio.sleep(0.3)

    # 1. Создаем пользователя через email
    print(f"\n📝 Шаг 1: Создаем пользователя через email...")
    result = await create_user_email(TEST_EMAIL, "monthly")
    await asyncio.sleep(2)
    print(f"   ✅ Создан: {TEST_EMAIL}")

    # 2. Поиск по email
    print(f"\n🔍 Шаг 2: Поиск по email...")
    balance = await get_user_balance(TEST_EMAIL, by="email")
    assert balance, "Не найден по email"
    uuid_user = balance.get('uuid')
    print(f"   ✅ Найден: {balance.get('email')} | UUID: {uuid_user[:12]}... | Дней: {balance.get('days_left')}")

    # 3. Поиск по UUID
    print(f"\n🔍 Шаг 3: Поиск по UUID...")
    balance2 = await get_user_balance(uuid_user, by="uuid")
    assert balance2, "Не найден по UUID"
    print(f"   ✅ Найден: {balance2.get('email')} | Дней: {balance2.get('days_left')}")

    # 4. Проверка аномалий
    print(f"\n📝 Шаг 4: Проверка аномалий...")
    anomalies = await check_anomalies(TEST_EMAIL)
    anomaly = anomalies.get('anomaly') if anomalies else 'error'
    print(f"   {'⚠️ Аномалия: ' + anomaly if anomaly else '✅ Аномалий нет'}")

    # 5. Очистка
    print(f"\n🧹 Шаг 5: Очистка...")
    await cleanup_user(email=TEST_EMAIL)
    print(f"   ✅ Удалён")

    return True


async def main():
    try:
        success = await test_user_info()
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 04 ПРОЙДЕН!" if success else "❌ ТЕСТ 04 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    import sys
    # Если main() вернул True -> exit(0), если False -> exit(1)
    sys.exit(0 if asyncio.run(main()) else 1)
