#!/usr/bin/env python3
"""
Тест 12: Проверка эквайринга Platega.io (Мультивалютность и Идемпотентность)
"""
import asyncio
import sys
import uuid as uuid_lib
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings

# Добавляем путь к helpers
sys.path.insert(0, str(Path(__file__).parent))

from lib.test_helpers import get_user_balance, cleanup_user

BASE_URL = "http://127.0.0.1:8000"
TEST_TG_ID = 444444444
TEST_TG_USERNAME = "test_platega_user"


async def test_platega_billing():
    print("=" * 60)
    print("🧪 ТЕСТ 12: Интеграция эквайринга Platega.io")
    print("=" * 60)

    async with __import__('httpx').AsyncClient(timeout=10.0) as client:

        # --------------------------------------------------------
        # Шаг 0: Очистка и пред-инициализация «паспорта» пользователя
        # --------------------------------------------------------
        print(f"\n🧹 Шаг 0: Очистка среды...")
        await cleanup_user(tg_id=TEST_TG_ID)
        await asyncio.sleep(0.3)

        print(f"🚀 Шаг 0.5: Регистрация паспорта пользователя в СУБД...")
        user_internal_id = None
        async with AsyncSessionLocal() as session:
            sql_init_user = """
                INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
                VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """
            res_usr = await session.execute(text(sql_init_user), {
                "tg_id": TEST_TG_ID, "username": TEST_TG_USERNAME, "uuid": str(uuid_lib.uuid4())
            })
            user_internal_id = res_usr.scalar_one()
            await session.commit()
        print(f"   ✅ Пользователь зафиксирован. Внутренний ID: {user_internal_id}")

        # --------------------------------------------------------
        # Шаг 1: Создание инвойса в статусе 'pending' (Имитация покупки)
        # --------------------------------------------------------
        print(f"\n📝 Шаг 1: Генерация инвойса вpayment_attempts (USD)...")
        invoice_id = str(uuid_lib.uuid4())
        async with AsyncSessionLocal() as session:
            sql_invoice = """
                INSERT INTO payment_attempts (id, email, user_id, tariff_slug, amount, currency, status, created_at, updated_at)
                VALUES (:id, 'test@ulysses.best', :uid, 'sub_1m', 5.00, 'USD', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            await session.execute(text(sql_invoice), {
                "id": invoice_id, "uid": user_internal_id, "currency": "USD"
            })
            await session.commit()
        print(f"   ✅ Создан инвойс {invoice_id} на сумму 5.00 USD")

        # --------------------------------------------------------
        # Шаг 2: Проверка защиты эндпоинта (Ожидаем HTTP 401)
        # --------------------------------------------------------
        print(f"\n🛡️ Шаг 2: Проверка защиты вебхука (запрос без секретных ключей)...")
        bad_resp = await client.post(f"{BASE_URL}/api/payments/platega-callback", json={"id": "fake"})
        print(f"   • Статус ответа: {bad_resp.status_code}")
        assert bad_resp.status_code == 401, "Эндпоинт должен отклонять запросы без X-Secret / X-MerchantId!"
        print("   ✅ Защита эндпоинта работает корректно.")

        # --------------------------------------------------------
        # Шаг 3: Имитация успешного мультивалютного Callback от Platega
        # --------------------------------------------------------
        print(f"\n💳 Шаг 3: Отправка валидного Callback от Platega (Оплата инвойса в USD)...")
        platega_tx_id = f"plt_{str(uuid_lib.uuid4())[:8]}"

        # Собираем payload строго по спецификации SDK Platega
        webhook_payload = {
            "id": platega_tx_id,
            "amount": 5.00,
            "currency": "USD",
            "status": "CONFIRMED",
            "paymentMethod": 13,  # METHOD_CRYPTO
            "payload": invoice_id  # UUID нашего инвойса
        }

        # Навешиваем боевые заголовки авторизации SDK
        valid_headers = {
            "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
            "X-Secret": settings.PLATEGA_API
        }

        resp = await client.post(
            f"{BASE_URL}/api/payments/platega-callback",
            headers=valid_headers,
            json=webhook_payload
        )
        print(f"   • Ответ бэкенда: HTTP {resp.status_code} - {resp.text}")
        assert resp.status_code == 200, f"Бэкенд отклонил валидный вебхук: {resp.text}"

        # Проверяем, начислились ли 30 дней подписки
        await asyncio.sleep(1)
        balance1 = await get_user_balance(TEST_TG_ID)
        days1 = balance1.get('days_left', 0) if balance1 else 0
        print(f"   • Подписка активна: {balance1.get('is_active')} | Дней начислено: {days1}")
        assert days1 >= 29, f"Подписка должна была включиться на 30 дней, но получили {days1}"

        # --------------------------------------------------------
        # Шаг 4: Тест Идемпотентности (Дублирование сетевого пакета)
        # --------------------------------------------------------
        print(f"\n🔄 Шаг 4: Тест идемпотентности (Повторная отправка того же вебхука)...")
        resp_duplicate = await client.post(
            f"{BASE_URL}/api/payments/platega-callback",
            headers=valid_headers,
            json=webhook_payload
        )
        print(f"   • Ответ на дубликат: HTTP {resp_duplicate.status_code} - {resp_duplicate.text}")
        assert resp_duplicate.status_code == 200, "Дубликат должен возвращать HTTP 200 OK!"

        # Проверяем баланс времени еще раз
        balance2 = await get_user_balance(TEST_TG_ID)
        days2 = balance2.get('days_left', 0) if balance2 else 0
        print(f"   • Было дней: {days1} | Стало дней после дубликата: {days2}")

        # Если идемпотентность нарушена, дней станет 60, и ассерт упадет
        assert days2 == days1, f"🚨 Сбой идемпотентности! Дни были начислены повторно: {days1} -> {days2}"
        print("   ✅ Идемпотентность подтверждена. Повторные начисления заблокированы.")

        # --------------------------------------------------------
        # Шаг 5: Вычищаем хвосты
        # --------------------------------------------------------
        print(f"\n🧹 Шаг 5: Очистка системы...")
        await cleanup_user(tg_id=TEST_TG_ID)
        print("   ✅ Тест-пользователь удален.")
        return True


async def main():
    try:
        success = await test_platega_billing()
    except AssertionError as e:
        print(f"\n❌ Ошибка утверждения: {e}")
        success = False
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка во время теста: {e}")
        success = False

    print("\n" + "=" * 60)
    print("✅ ТЕСТ 12 ПРОЙДЕН!" if success else "❌ ТЕСТ 12 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    import sys
    # Возвращаем честный exit code оркестратору run_all.py
    sys.exit(0 if asyncio.run(main()) else 1)
