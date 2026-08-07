#!/usr/bin/env python3
"""
Тест 08: Идемпотентность вебхуков
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import httpx
import uuid
from app.config import settings

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc"
HEADERS = {"X-API-Key": API_KEY}

WEBHOOK_HEADERS = {
    "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
    "X-Secret": settings.PLATEGA_API
}


async def cleanup(email: str):
    """Очистка тестового пользователя напрямую через БД."""
    from app.database import AsyncSessionLocal
    from app.services.hiddify_client import HiddifyProvisioner
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        # Получаем UUID для удаления из Hiddify
        res = await session.execute(
            text("SELECT hiddify_uuid FROM users WHERE email = :email"),
            {"email": email}
        )
        row = res.fetchone()
        if row:
            hiddify_uuid = str(row[0])
            try:
                await HiddifyProvisioner().delete_user(hiddify_uuid)
            except Exception:
                pass

        await session.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"), {"email": email})
        await session.execute(text("DELETE FROM payment_attempts WHERE email = :email"), {"email": email})
        await session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
        await session.commit()


async def test_same_order_id_multiple_times():
    """Тест 1: Один order_id - три вебхука success. Должна создаться только ОДНА подписка."""
    print("\n📋 Тест 1: Три вебхука success с одним order_id")
    print("-" * 40)

    test_email = f"idem1_{uuid.uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Создаем инвойс
        r = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            headers=HEADERS,
            json={"email": test_email, "tariff_slug": "sub_1m"}
        )
        data = r.json()
        order_id = data.get('order_id')
        print(f"✅ Инвойс: {order_id}")

        # Три вебхука success
        for i in range(3):
            r = await client.post(
                f"{BASE_URL}/api/billing/webhook",
                headers=WEBHOOK_HEADERS,
                json={
                    "id": f"tx_{i}_{uuid.uuid4().hex[:6]}",
                    "amount": 199.0,
                    "currency": "RUB",
                    "status": "CONFIRMED",
                    "paymentMethod": 10,
                    "payload": order_id
                }
            )
            print(f"   Вебхук {i+1}: {r.status_code} {r.text}")
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)

        # Проверка
        r = await client.get(
            f"{BASE_URL}/api/user/balance",
            headers=HEADERS,
            params={"email": test_email}
        )
        if r.status_code == 200:
            days = r.json().get('days_left', 0)
            print(f"📊 Дней: {days}")
            ok = 29 <= days <= 31
        else:
            print(f"❌ Баланс не получен: {r.status_code}")
            ok = False

        await cleanup(test_email)
        return ok


async def test_failed_then_success():
    """Тест 2: Failed -> Success."""
    print("\n📋 Тест 2: Failed -> Success")
    print("-" * 40)

    test_email = f"idem2_{uuid.uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            headers=HEADERS,
            json={"email": test_email, "tariff_slug": "sub_1m"}
        )
        order_id = r.json()['order_id']
        print(f"✅ Инвойс: {order_id}")

        # Failed
        await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers=WEBHOOK_HEADERS,
            json={
                "id": "tx_failed",
                "amount": 199.0,
                "currency": "RUB",
                "status": "CANCELED",
                "paymentMethod": 10,
                "payload": order_id
            }
        )
        r = await client.get(
            f"{BASE_URL}/api/user/balance",
            headers=HEADERS,
            params={"email": test_email}
        )
        # Пользователь создаётся при создании инвойса, так что 200, но неактивен
        if r.status_code == 200:
            is_active = r.json().get('is_active', False)
            assert not is_active, "После failed подписка не должна быть активна"
            print("✅ После failed подписка неактивна")
        else:
            print(f"ℹ️ Статус: {r.status_code}")

        # Success
        await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers=WEBHOOK_HEADERS,
            json={
                "id": "tx_success",
                "amount": 199.0,
                "currency": "RUB",
                "status": "CONFIRMED",
                "paymentMethod": 10,
                "payload": order_id
            }
        )
        await asyncio.sleep(2)

        r = await client.get(
            f"{BASE_URL}/api/user/balance",
            headers=HEADERS,
            params={"email": test_email}
        )
        assert r.status_code == 200, "После success пользователь должен существовать"
        print(f"✅ После success создан, дней: {r.json().get('days_left')}")

        await cleanup(test_email)
        return True


async def test_already_processed_response():
    """Тест 3: Повторный вебхук возвращает OK."""
    print("\n📋 Тест 3: Повторный вебхук")
    print("-" * 40)

    test_email = f"idem3_{uuid.uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            headers=HEADERS,
            json={"email": test_email, "tariff_slug": "sub_1m"}
        )
        order_id = r.json()['order_id']
        print(f"✅ Инвойс: {order_id}")

        # Первый success
        r1 = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers=WEBHOOK_HEADERS,
            json={
                "id": "tx_1",
                "amount": 199.0,
                "currency": "RUB",
                "status": "CONFIRMED",
                "paymentMethod": 10,
                "payload": order_id
            }
        )
        print(f"Первый: {r1.status_code} {r1.text}")
        await asyncio.sleep(1)

        # Второй success
        r2 = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers=WEBHOOK_HEADERS,
            json={
                "id": "tx_2",
                "amount": 199.0,
                "currency": "RUB",
                "status": "CONFIRMED",
                "paymentMethod": 10,
                "payload": order_id
            }
        )
        print(f"Второй: {r2.status_code} {r2.text}")

        await cleanup(test_email)
        # Оба должны вернуть 200 OK
        return r1.status_code == 200 and r2.status_code == 200


async def main():
    print("=" * 60)
    print("🧪 ТЕСТ 08: Идемпотентность вебхуков")
    print("=" * 60)

    results = []
    for name, fn in [("3x success", test_same_order_id_multiple_times),
                      ("Failed->Success", test_failed_then_success),
                      ("already_processed", test_already_processed_response)]:
        try:
            ok = await fn()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            ok = False
        results.append((name, ok))

    print("\n" + "=" * 60)
    print("📊 ИТОГИ:")
    all_pass = True
    for name, ok in results:
        print(f"   {'✅' if ok else '❌'} {name}")
        if not ok:
            all_pass = False
    print("=" * 60)
    print("✅ ТЕСТ 08 ПРОЙДЕН!" if all_pass else "❌ ТЕСТ 08 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return all_pass


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
