#!/usr/bin/env python3
"""
Тест 08: Идемпотентность вебхуков
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import httpx
import uuid

BASE_URL = "http://127.0.0.1:8000"


async def cleanup(email: str):
    """Очистка тестового пользователя."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.delete(f"{BASE_URL}/api/admin/account", params={"email": email, "target": "all"})


async def test_same_order_id_multiple_times():
    """Тест 1: Один order_id - три вебхука success. Должна создаться только ОДНА подписка."""
    print("\n📋 Тест 1: Три вебхука success с одним order_id")
    print("-" * 40)

    test_email = f"idem1_{uuid.uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Создаем инвойс
        r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
            "email": test_email, "tariff_slug": "sub_1m"
        })
        order_id = r.json()['order_id']
        print(f"✅ Инвойс: {order_id}")

        # Три вебхука success
        for i in range(3):
            r = await client.post(f"{BASE_URL}/api/billing/webhook", json={
                "order_id": order_id,
                "provider_tx_id": f"tx_{i}_{uuid.uuid4().hex[:6]}",
                "status": "success"
            })
            print(f"   Вебхук {i+1}: {r.json().get('status')}")
            await asyncio.sleep(0.5)

        await asyncio.sleep(2)

        # Проверка
        r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
        days = r.json().get('days_left', 0)
        print(f"📊 Дней: {days}")

        # Очистка
        await cleanup(test_email)

        return 29 <= days <= 31


async def test_failed_then_success():
    """Тест 2: Failed -> Success."""
    print("\n📋 Тест 2: Failed -> Success")
    print("-" * 40)

    test_email = f"idem2_{uuid.uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
            "email": test_email, "tariff_slug": "sub_1m"
        })
        order_id = r.json()['order_id']

        # Failed
        await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": order_id, "provider_tx_id": "tx_failed", "status": "failed"
        })
        r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
        assert r.status_code == 404, "После failed пользователь не должен существовать"
        print("✅ После failed пользователь не создан")

        # Success
        await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": order_id, "provider_tx_id": "tx_success", "status": "success"
        })
        await asyncio.sleep(2)

        r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
        assert r.status_code == 200, "После success пользователь должен существовать"
        print(f"✅ После success создан, дней: {r.json().get('days_left')}")

        await cleanup(test_email)
        return True


async def test_already_processed_response():
    """Тест 3: Ответ 'already_processed'."""
    print("\n📋 Тест 3: Ответ 'already_processed'")
    print("-" * 40)

    test_email = f"idem3_{uuid.uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
            "email": test_email, "tariff_slug": "sub_1m"
        })
        order_id = r.json()['order_id']

        # Первый success
        r1 = await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": order_id, "provider_tx_id": "tx_1", "status": "success"
        })
        print(f"Первый: {r1.json().get('status')}")
        await asyncio.sleep(1)

        # Второй success
        r2 = await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": order_id, "provider_tx_id": "tx_2", "status": "success"
        })
        status2 = r2.json().get('status')
        print(f"Второй: {status2}")

        await cleanup(test_email)
        return status2 == 'already_processed'


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
    import sys
    # Если main() вернул True -> exit(0), если False -> exit(1)
    sys.exit(0 if asyncio.run(main()) else 1)
