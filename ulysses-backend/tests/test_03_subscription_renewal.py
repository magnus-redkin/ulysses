#!/usr/bin/env python3
"""
Тест 03: Продление подписки (суммирование дней)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_tg, get_user_balance, cleanup_user

TEST_TG_ID = 888888888
TEST_TG_USERNAME = "test_user_renew"


async def test_subscription_renewal():
    print("=" * 60)
    print("🧪 ТЕСТ 03: Продление подписки")
    print("=" * 60)

    # 0. Очистка
    print(f"\n🧹 Шаг 0: Очистка...")
    await cleanup_user(tg_id=TEST_TG_ID)
    await asyncio.sleep(0.5)

    # 1. Первая покупка (платная, 30 дней)
    print(f"\n📝 Шаг 1: Первая покупка (sub_1m, 30 дн.)...")
    await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_1m")
    await asyncio.sleep(3)

    balance1 = await get_user_balance(TEST_TG_ID)
    days1 = balance1.get('days_left', 0) if balance1 else 0
    print(f"   • Дней после первой покупки: {days1}")
    assert days1 >= 29, f"Ожидалось ~30 дней, получено {days1}"

    # 2. Продление (ещё 30 дней, суммирование)
    print(f"\n📝 Шаг 2: Продление (sub_1m, +30 дн.)...")
    await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_1m")
    await asyncio.sleep(3)

    balance2 = await get_user_balance(TEST_TG_ID)
    days2 = balance2.get('days_left', 0) if balance2 else 0
    print(f"   • Дней после продления: {days2}")

    # 3. Проверка суммирования
    print(f"\n📝 Шаг 3: Проверка суммирования...")
    print(f"   • Было: {days1}, Стало: {days2}")
    assert days2 >= days1 + 28, f"Дни не суммировались: {days1} → {days2}"

    # 4. Чистим
    print(f"\n📝 Шаг 4: Очистка...")
    await cleanup_user(tg_id=TEST_TG_ID)
    print(f"   ✅ Пользователь удалён")

    return True


async def main():
    try:
        success = await test_subscription_renewal()
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 03 ПРОЙДЕН!" if success else "❌ ТЕСТ 03 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    asyncio.run(main())
