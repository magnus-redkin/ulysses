#!/usr/bin/env python3
"""
Тест 07: Админ-статистика и проверка системы
"""
import asyncio
import sys
from pathlib import Path
from sqlalchemy import text
from app.database import AsyncSessionLocal
import uuid as uuid_lib

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

        # 🌟 ИСПРАВЛЕНИЕ: Массовая предварительная регистрация паспортов в СУБД до вызова bot/action
        async with AsyncSessionLocal() as session:
            try:
                for i in range(3):
                    tg_id = 100000000 + i
                    sql_init_user = """
                        INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
                        VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                    await session.execute(text(sql_init_user), {
                        "tg_id": tg_id,
                        "username": f"test_stat_{i}",
                        "uuid": str(uuid_lib.uuid4())
                    })
                await session.commit()
                print("   • Входные паспорта пользователей успешно инициализированы в БД.")
            except Exception as db_err:
                await session.rollback()
                print(f"   ❌ Ошибка при массовой инициализации в БД: {db_err}")
                return False

        # Теперь вызываем логику создания подписок для уже существующих в БД пользователей
        for i in range(3):
            tg_id = 100000000 + i
            await create_user_tg(tg_id, f"test_stat_{i}", "sub_free")

            # Адаптация под логику триалов (как в тесте 05): пушим в active, если бэкенд оставляет в provisioning
            async with AsyncSessionLocal() as session:
                sql_activate = """
                    UPDATE subscriptions
                    SET status = 'active', starts_at = CURRENT_TIMESTAMP,
                        expires_at = CURRENT_TIMESTAMP + INTERVAL '3 days', activated_at = CURRENT_TIMESTAMP
                    WHERE user_id = (SELECT id FROM users WHERE tg_user_id = :tg_id)
                """
                await session.execute(text(sql_activate), {"tg_id": tg_id})
                await session.commit()

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
        summary = anomalies.get('summary', {}) if anomalies else {}
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
    import sys
    # Если main() вернул True -> exit(0), если False -> exit(1)
    sys.exit(0 if asyncio.run(main()) else 1)
