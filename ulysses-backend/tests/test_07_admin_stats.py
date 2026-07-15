#!/usr/bin/env python3
"""
Тест 07: Админ-статистика и проверка системы
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_tg, cleanup_user, check_anomalies

BASE_URL = "http://127.0.0.1:8000"


async def test_admin_stats():
    print("=" * 60)
    print("🧪 ТЕСТ 07: Админ-статистика и проверка")
    print("=" * 60)

    async with __import__('httpx').AsyncClient(timeout=30.0) as client:
        # 0. Очистка старых тестовых
        for i in range(3):
            await cleanup_user(tg_id=100000000 + i)
        await asyncio.sleep(0.5)

        # 1. Получаем статистику ДО
        print(f"\n📊 Шаг 1: Статистика ДО создания...")
        resp = await client.get(f"{BASE_URL}/api/admin/stats")
        stats_before = resp.json()
        print(f"   • Всего: {stats_before.get('total_users')} | Активных: {stats_before.get('active_subscriptions')}")

        # 2. Создаем 3 тестовых пользователей
        print(f"\n📝 Шаг 2: Создаем 3 тестовых пользователей...")
        for i in range(3):
            tg_id = 100000000 + i
            await create_user_tg(tg_id, f"test_stat_{i}", "sub_free")
        await asyncio.sleep(3)
        print(f"   ✅ Созданы")

        # 3. Статистика ПОСЛЕ
        print(f"\n📊 Шаг 3: Статистика ПОСЛЕ создания...")
        resp = await client.get(f"{BASE_URL}/api/admin/stats")
        stats_after = resp.json()
        print(f"   • Всего: {stats_after.get('total_users')} | Активных: {stats_after.get('active_subscriptions')}")
        assert stats_after.get('total_users') >= stats_before.get('total_users') + 3, "Пользователи не добавились"

        # 4. Проверка аномалий
        print(f"\n🔍 Шаг 4: Проверка системы (check)...")
        anomalies = await check_anomalies()
        summary = anomalies.get('summary', {})
        print(f"   • Грязных инвойсов: {summary.get('dirty_invoices_count', 0)}")
        print(f"   • Аномалий профилей: {summary.get('hiddify_anomalies_count', 0)}")

        # 5. Автофикс
        print(f"\n🔧 Шаг 5: fix sync...")
        resp = await client.post(f"{BASE_URL}/api/admin/fix/sync")
        fix = resp.json()
        print(f"   • Исправлено статусов: {fix.get('fixed_hiddify_statuses', 0)}")

        # 6. Очистка
        print(f"\n🧹 Шаг 6: Очистка...")
        for i in range(3):
            await cleanup_user(tg_id=100000000 + i)
        print(f"   ✅ Все удалены")

        return True


async def main():
    try:
        success = await test_admin_stats()
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 07 ПРОЙДЕН!" if success else "❌ ТЕСТ 07 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    asyncio.run(main())
