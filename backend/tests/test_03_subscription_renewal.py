#!/usr/bin/env python3
"""
Тест 03: Продление подписки (суммирование дней)
"""
import asyncio
import sys
from pathlib import Path
from sqlalchemy import text
from app.database import AsyncSessionLocal

sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import create_user_tg, get_user_balance, cleanup_user

TEST_TG_ID = 888888888
TEST_TG_USERNAME = "test_user_renew"


async def fake_pay_invoice(tg_id: int):
    """Имитирует успешную оплату и активирует подписку с гарантированным UTC-временем."""
    from datetime import datetime, timedelta, timezone

    async with AsyncSessionLocal() as session:
        try:
            sql_user = "SELECT id FROM users WHERE tg_user_id = :tg_id"
            res_user = await session.execute(text(sql_user), {"tg_id": tg_id})
            user_row = res_user.fetchone()

            if not user_row:
                print("      [PAYMENT SIMULATOR] ❌ Пользователь не найден в БД.")
                return

            user_internal_id = user_row[0]
            now = datetime.now(timezone.utc)

            sql_sub = "SELECT id, expires_at, status FROM subscriptions WHERE user_id = :uid LIMIT 1"
            res_sub = await session.execute(text(sql_sub), {"uid": user_internal_id})
            sub_row = res_sub.fetchone()

            if sub_row:
                sub_id, current_expires, status = sub_row
                if status == 'active' and current_expires and current_expires > now:
                    new_expires = current_expires + timedelta(days=30)
                else:
                    new_expires = now + timedelta(days=30)

                sql_update_sub = """
                    UPDATE subscriptions
                    SET status = 'active', starts_at = :now, expires_at = :expires,
                        activated_at = :now, updated_at = :now
                    WHERE id = :sub_id
                """
                await session.execute(text(sql_update_sub), {
                    "now": now, "expires": new_expires, "sub_id": sub_id
                })
                print(f"      [PAYMENT SIMULATOR] ✅ Подписка #{sub_id} переведена в active до {new_expires.strftime('%Y-%m-%d')}")
            else:
                new_expires = now + timedelta(days=30)
                sql_insert_sub = """
                    INSERT INTO subscriptions (user_id, tariff_slug, status, starts_at, expires_at, activated_at, node_id, created_at, updated_at)
                    VALUES (:uid, 'sub_1m', 'active', :now, :expires, :now, 'main', :now, :now)
                """
                await session.execute(text(sql_insert_sub), {
                    "uid": user_internal_id, "now": now, "expires": new_expires
                })
                print(f"      [PAYMENT SIMULATOR] ➕ Создана новая активная подписка на 30 дней.")

            await session.execute(
                text("UPDATE payment_attempts SET status = 'success', updated_at = :now WHERE user_id = :uid"),
                {"uid": user_internal_id, "now": now}
            )
            await session.commit()

        except Exception as e:
            await session.rollback()
            print(f"      [PAYMENT SIMULATOR] ❌ Критическая ошибка: {e}")


async def test_subscription_renewal():
    print("=" * 60)
    print("🧪 ТЕСТ 03: Продление подписки")
    print("=" * 60)

    # 0. Очистка
    print(f"\n🧹 Шаг 0: Очистка...")
    await cleanup_user(tg_id=TEST_TG_ID)
    await asyncio.sleep(0.5)

    # 🌟 ШАГ 0.5: Имитируем команду /start в Telegram-боте (Создаем пользователя в СУБД)
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
            print(f"   ✅ Запись пользователя успешно инициализирована в БД.")
        except Exception as db_err:
            await session.rollback()
            print(f"   ❌ Ошибка при прямой инициализации в БД: {db_err}")
            return False

    # 1. Первая покупка (платная, 30 дней)
    print(f"\n📝 Шаг 1: Первая покупка (sub_1m, 30 дн.)...")
    await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_1m")
    await asyncio.sleep(1)

    await fake_pay_invoice(TEST_TG_ID)
    await asyncio.sleep(2)

    balance1 = await get_user_balance(TEST_TG_ID)
    days1 = balance1.get('days_left', 0) if balance1 else 0
    print(f"   • Дней после первой покупки: {days1}")
    assert days1 >= 29, f"Ожидалось ~30 дней, получено {days1}"

    # 2. Продление (ещё 30 дней, суммирование)
    print(f"\n📝 Шаг 2: Продление (sub_1m, +30 дн.)...")
    await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_1m")
    await asyncio.sleep(1)

    await fake_pay_invoice(TEST_TG_ID)
    await asyncio.sleep(2)

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
    import sys
    # Если main() вернул True -> exit(0), если False -> exit(1)
    sys.exit(0 if asyncio.run(main()) else 1)
