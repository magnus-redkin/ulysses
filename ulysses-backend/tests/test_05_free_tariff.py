#!/usr/bin/env python3
"""
Тест 05: Бесплатный тариф (автоактивация) + проверка повторной активации
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_tg, get_user_balance, get_bot_state, cleanup_user

TEST_TG_ID = 666666666
TEST_TG_USERNAME = "test_free"


async def test_free_tariff():
    print("=" * 60)
    print("🧪 ТЕСТ 05: Бесплатный тариф")
    print("=" * 60)

    # 0. Очистка
    print(f"\n🧹 Шаг 0: Очистка...")
    await cleanup_user(tg_id=TEST_TG_ID)
    await asyncio.sleep(0.3)

    # 1. Первая активация free
    print(f"\n📝 Шаг 1: Первая активация sub_free...")
    result = await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_free")
    print(f"   • state: {result.get('state')}")
    assert result.get('state') == 'payment_free', f"Ожидался payment_free, получен {result.get('state')}"

    await asyncio.sleep(2)
    balance = await get_user_balance(TEST_TG_ID)
    assert balance and balance.get('is_active'), "Подписка должна быть активна"
    print(f"   ✅ Активна, дней: {balance.get('days_left')}")

    # 2. Повторная активация free — должна вернуть ошибку
    print(f"\n📝 Шаг 2: Повторная активация sub_free (должна быть ошибка)...")
    result2 = await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_free")
    print(f"   • state: {result2.get('state')}")
    assert result2.get('state') == 'error', f"Ожидалась ошибка, получен {result2.get('state')}"
    print(f"   ✅ Бесплатный тариф больше не доступен")

    # 3. Очистка
    print(f"\n🧹 Шаг 3: Очистка...")
    await cleanup_user(tg_id=TEST_TG_ID)
    print(f"   ✅ Удалён")

    return True


async def main():
    try:
        success = await test_free_tariff()
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 05 ПРОЙДЕН!" if success else "❌ ТЕСТ 05 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    asyncio.run(main())
