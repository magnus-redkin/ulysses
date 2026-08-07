#!/usr/bin/env python3
"""
Тест 07: Админ-статистика и проверка системы
"""
import asyncio
import sys
from pathlib import Path
import uuid as uuid_lib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal

sys.path.insert(0, str(Path(__file__).parent))
from lib.test_helpers import create_user_tg, get_user_balance, get_bot_state, cleanup_user, check_anomalies

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc"
HEADERS = {"X-API-Key": API_KEY}


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
        resp = await client.get(f"{BASE_URL}/api/admin/stats", headers=HEADERS)
        if resp.status_code != 200:
            print(f"   ❌ Ошибка: {resp.status_code} {resp.text}")
            return False
        stats_before = resp.json().get("stats", {})
        print(f"   • Всего: {stats_before.get('total_users')} | Активных: {stats_before.get('active_subscriptions')}")

        # 2. Создаем 3 тестовых пользователей
        print(f"\n📝 Шаг 2: Создаем 3 тестовых пользователей...")
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

        for i in range(3):
            tg_id = 100000000 + i
            await create_user_tg(tg_id, f"test_stat_{i}", "sub_free")

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
        resp = await client.get(f"{BASE_URL}/api/admin/stats", headers=HEADERS)
        if resp.status_code != 200:
            print(f"   ❌ Ошибка: {resp.status_code} {resp.text}")
            return False
        stats_after = resp.json().get("stats", {})
        print(f"   • Всего: {stats_after.get('total_users')} | Активных: {stats_after.get('active_subscriptions')}")
        assert stats_after.get('total_users', 0) >= stats_before.get('total_users', 0) + 3, "Пользователи не добавились"

        # 4. Проверка аномалий
        print(f"\n🔍 Шаг 4: Проверка системы (check)...")
        resp = await client.get(f"{BASE_URL}/api/admin/check", headers=HEADERS)
        if resp.status_code != 200:
            print(f"   ❌ Ошибка: {resp.status_code} {resp.text}")
            return False
        anomalies = resp.json()
        summary = anomalies.get('summary', {})
        print(f"   • Грязных инвойсов: {summary.get('dirty_invoices_count', 0)}")
        print(f"   • Аномалий профилей: {summary.get('hiddify_anomalies_count', 0)}")

        # 5. Очистка инвойсов
        print(f"\n🔧 Шаг 5: Очистка инвойсов...")
        resp = await client.post(f"{BASE_URL}/api/admin/fix/cleanup-invoices", headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            print(f"   • Удалено: {data.get('deleted_count', 0)}")
        else:
            print(f"   ⚠️ Ошибка: {resp.status_code}")

        # 6. Очистка пользователей
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
    sys.exit(0 if asyncio.run(main()) else 1)
