#!/usr/bin/env python3
"""
Тест 01: Создание пользователя через email (сайт)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tests.set_env


import asyncio
import httpx
import uuid
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
TEST_EMAIL = f"test_{uuid.uuid4().hex[:8]}@example.com"

async def test_create_user_email():
    """Тест создания пользователя через сайт (email)"""

    print("=" * 60)
    print("🧪 ТЕСТ 01: Создание пользователя через email")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:

        # 0. Очистка перед тестом
        print(f"\n🧹 Шаг 0: Очистка перед тестом...")
        await client.delete(f"{BASE_URL}/api/admin/account", params={"email": TEST_EMAIL})
        await asyncio.sleep(0.3)

        # 1. Создаем инвойс
        print(f"\n📝 Шаг 1: Создаем инвойс для {TEST_EMAIL}...")
        response = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            json={
                "email": TEST_EMAIL,
                "tariff_slug": "premium"
            }
        )

        if response.status_code != 200:
            print(f"❌ Ошибка создания инвойса: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return False

        data = response.json()
        order_id = data.get('order_id')
        print(f"✅ Инвойс создан: {order_id}")
        print(f"   • Сумма: {data.get('amount')} {data.get('currency')}")

        # 2. Симулируем оплату через вебхук
        print("\n💰 Шаг 2: Симулируем оплату (вебхук)...")
        webhook_response = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            json={
                "order_id": order_id,
                "provider_tx_id": f"tx_test_{uuid.uuid4()}",
                "status": "success"
            }
        )

        if webhook_response.status_code != 200:
            print(f"❌ Ошибка вебхука: {webhook_response.status_code}")
            print(f"   Ответ: {webhook_response.text}")
            return False

        webhook_data = webhook_response.json()
        print(f"✅ Вебхук выполнен: {webhook_data.get('status')}")
        print(f"   • UUID: {webhook_data.get('hiddify_uuid')}")

        # 3. Ждем завершения фоновых задач
        await asyncio.sleep(2)

        # 4. Проверяем создание пользователя
        print("\n📊 Шаг 3: Проверяем создание пользователя...")
        balance_response = await client.get(
            f"{BASE_URL}/api/user/balance",
            params={"email": TEST_EMAIL}
        )

        if balance_response.status_code != 200:
            print(f"❌ Ошибка получения информации: {balance_response.status_code}")
            return False

        user_data = balance_response.json()
        print(f"✅ Пользователь найден:")
        print(f"   • Email: {user_data.get('email')}")
        print(f"   • UUID: {user_data.get('uuid')}")
        print(f"   • Статус: {'Активен' if user_data.get('is_active') else 'Неактивен'}")
        print(f"   • Дней осталось: {user_data.get('days_left')}")

        # 5. Проверяем, что письмо отправлено (проверяем по логам)
        print("\n📧 Шаг 4: Проверяем отправку письма...")
        print("   ✅ Письмо должно быть отправлено на email (проверьте логи)")
        print(f"   📧 {TEST_EMAIL}")


        # 6. Очистка
        print(f"\n🧹 Шаг 5: Очистка...")
        # Удалить из БД
        await client.delete(f"{BASE_URL}/api/admin/account", params={"email": TEST_EMAIL, "target": "db"})
        # Удалить из Hiddify
        hiddify_uuid = user_data.get('uuid')
        if hiddify_uuid:
            await client.delete(f"{BASE_URL}/api/admin/account", params={"uuid": hiddify_uuid, "target": "hiddify"})
        print(f"   ✅ Пользователь удалён")

        return True


async def main():
    success = await test_create_user_email()
    print("\n" + "=" * 60)
    print("✅ ТЕСТ 01 УСПЕШНО ПРОЙДЕН!" if success else "❌ ТЕСТ 01 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return success


if __name__ == "__main__":
    asyncio.run(main())
