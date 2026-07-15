#!/usr/bin/env python3
"""
Тест 02: Создание пользователя через Telegram (без email)
"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к helpers
sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_tg, get_user_balance, get_bot_state, check_anomalies, cleanup_user

TEST_TG_ID = 999999999
TEST_TG_USERNAME = "test_user_tg"


async def test_create_user_telegram():
    print("=" * 60)
    print("🧪 ТЕСТ 02: Создание пользователя через Telegram")
    print("=" * 60)

    # 0. Очистка перед тестом
    print(f"\n🧹 Шаг 0: Очистка перед тестом...")
    await cleanup_user(tg_id=TEST_TG_ID)
    await asyncio.sleep(0.5)
    print(f"   ✅ Очищено")

    # 1. Состояние до
    print(f"\n📝 Шаг 1: Проверяем состояние до создания...")
    state = await get_bot_state(TEST_TG_ID)
    print(f"   • state: {state.get('state')}" if state else "   ❌ Ошибка")
    assert state and state.get('state') == 'new', "Ожидался state='new'"

    # 2. Создаём через bot/action
    print(f"\n📝 Шаг 2: Создаём заказ через bot/action...")
    result = await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_free")
    print(f"   • state: {result.get('state')}")
    print(f"   • message: {result.get('message')}")
    assert result and result.get('state') in ('payment_free', 'payment_pending'), f"Неожиданный state: {result.get('state')}"

    # 3. Ждём активации
    print(f"\n📝 Шаг 3: Ждём активации...")
    await asyncio.sleep(3)

    # 4. Проверяем баланс
    print(f"\n📝 Шаг 4: Проверяем баланс...")
    balance = await get_user_balance(TEST_TG_ID)
    if balance:
        print(f"   • Статус: {'Активен' if balance.get('is_active') else 'Неактивен'}")
        print(f"   • Дней: {balance.get('days_left')}")
        print(f"   • Email: {balance.get('email')}")
        print(f"   • UUID: {balance.get('uuid')}")
        assert balance.get('is_active'), "Подписка должна быть активна"
    else:
        print("   ⚠️ Баланс не получен (возможно, pending)")

    # 5. Проверяем аномалии
    print(f"\n📝 Шаг 5: Проверяем аномалии...")
    anomalies = await check_anomalies(str(TEST_TG_ID))
    anomaly = anomalies.get('anomaly') if anomalies else 'error'
    if anomaly:
        print(f"   ⚠️ Аномалия: {anomaly}")
    else:
        print(f"   ✅ Аномалий нет")

    # 6. Чистим
    print(f"\n📝 Шаг 6: Очистка...")
    await cleanup_user(tg_id=TEST_TG_ID)
    print(f"   ✅ Пользователь удалён")

    return True


async def main():
    try:
        success = await test_create_user_telegram()
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 02 ПРОЙДЕН!" if success else "❌ ТЕСТ 02 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    asyncio.run(main())
