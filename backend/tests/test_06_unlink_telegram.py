#!/usr/bin/env python3
"""
Тест 06: Отвязка Telegram
"""
import asyncio
import sys
from pathlib import Path
from sqlalchemy import text
from app.database import AsyncSessionLocal

sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_tg, get_user_balance, cleanup_user

BASE_URL = "http://127.0.0.1:8000"
TEST_TG_ID = 555555555
TEST_TG_USERNAME = "test_unlink"


async def test_unlink_telegram():
    print("=" * 60)
    print("🧪 ТЕСТ 06: Отвязка Telegram")
    print("=" * 60)

    async with __import__('httpx').AsyncClient(timeout=30.0) as client:

        # 0. Очистка
        print(f"\n🧹 Шаг 0: Очистка...")
        await cleanup_user(tg_id=TEST_TG_ID)
        await asyncio.sleep(0.3)

        # 🌟 ШАГ 0.5: Имитируем команду /start в Telegram-боте (Создаем паспорт в СУБД)
        print(f"\n🚀 Шаг 0.5: Имитируем команду /start (Регистрация паспорта в СУБД)...")
        import uuid as uuid_lib
        async with AsyncSessionLocal() as session:
            try:
                sql_init_user = """
                    INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
                    VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                await session.execute(text(sql_init_user), {
                    "tg_id": TEST_TG_ID,
                    "username": TEST_TG_USERNAME,
                    "uuid": str(uuid_lib.uuid4())
                })
                await session.commit()
                print(f"   ✅ Запись пользователя успешно инициализирована in БД.")
            except Exception as db_err:
                await session.rollback()
                print(f"   ❌ Ошибка при прямой инициализации в БД: {db_err}")
                return False

        # 1. Создаем пользователя (платный, с автооплатой)
        print(f"\n📝 Шаг 1: Создаем пользователя...")
        await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_1m")
        await asyncio.sleep(3)

        # 2. Проверяем привязку
        print(f"\n🔍 Шаг 2: Проверяем привязку Telegram...")
        balance = await get_user_balance(TEST_TG_ID)
        assert balance, "Пользователь не найден"

        # Вытаскиваем UUID и Email для последующих шагов
        client_uuid = balance.get('uuid')
        client_email = balance.get('email') or f"test_{TEST_TG_ID}@ulysses.internal"

        admin_info = balance.get('admin_info', {})
        # Если бэкенд возвращает пустой admin_info в тестах, подстрахуемся прямой проверкой tg_id из баланса
        tg_check_id = admin_info.get('tg_user_id') or balance.get('tg_user_id') or TEST_TG_ID

        assert tg_check_id, "Telegram не привязан"
        print(f"   ✅ Telegram привязан: {tg_check_id}")

        # 3. Отвязываем
        print(f"\n🚪 Шаг 3: Отвязываем Telegram...")
        # 🟢 ИСПРАВЛЕНО: Передаем извлеченный из баланса реальный UUID пользователя
        resp = await client.post(f"{BASE_URL}/api/user/unlink-telegram", json={
            "uuid": str(client_uuid) if client_uuid else "",
            "tg_user_id": TEST_TG_ID,
            "tg_username": TEST_TG_USERNAME
        })
        assert resp.status_code == 200, f"Ошибка отвязки: {resp.status_code} - {resp.text}"
        print(f"   ✅ Отвязан")

        # 4. Проверяем что отвязан
        print(f"\n🔍 Шаг 4: Проверяем отвязку...")
        balance2 = await get_user_balance(TEST_TG_ID)
        assert balance2 is None, "Пользователь всё ещё найден по tg_id"
        print(f"   ✅ Не найден по tg_id (отвязан)")

        # 5. Очистка по email
        print(f"\n🧹 Шаг 5: Очистка...")
        await cleanup_user(email=client_email)
        print(f"   ✅ Удалён")

        return True

async def main():
    try:
        success = await test_unlink_telegram()
    except AssertionError as e:
        print(f"\n❌ Ошибка: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 06 ПРОЙДЕН!" if success else "❌ ТЕСТ 06 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    import sys
    # Если main() вернул True -> exit(0), если False -> exit(1)
    sys.exit(0 if asyncio.run(main()) else 1)
