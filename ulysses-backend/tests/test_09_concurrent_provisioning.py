#!/usr/bin/env python3
"""
Тест 09: Конкурентный провижининг
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import httpx
import uuid

BASE_URL = "http://127.0.0.1:8000"


async def cleanup(email: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.delete(f"{BASE_URL}/api/admin/account", params={"email": email, "target": "all"})


async def test_concurrent_same_user():
    print("\n📋 Тест 1: 5 одновременных оплат одним пользователем")
    print("-" * 40)

    test_email = f"concurrent_{uuid.uuid4().hex[:6]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Создаем 5 инвойсов
        orders = []
        for _ in range(5):
            r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
                "email": test_email, "tariff_slug": "sub_1m"
            })
            if r.status_code == 200:
                orders.append(r.json()['order_id'])
        print(f"✅ Создано {len(orders)} инвойсов")

        # Оплачиваем все одновременно
        tasks = [client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": oid, "provider_tx_id": f"tx_{uuid.uuid4().hex[:8]}", "status": "success"
        }) for oid in orders]
        responses = await asyncio.gather(*tasks)
        print(f"💰 Успешных оплат: {sum(1 for r in responses if r.status_code == 200)}/{len(responses)}")

        await asyncio.sleep(3)

        r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
        days = r.json().get('days_left', 0) if r.status_code == 200 else 0
        print(f"📊 Дней: {days}")

        await cleanup(test_email)
        return 29 <= days <= 150


async def test_concurrent_different_users():
    print("\n📋 Тест 2: 10 одновременных оплат разными пользователями")
    print("-" * 40)

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def create_and_pay(email):
            r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
                "email": email, "tariff_slug": "sub_1m"
            })
            if r.status_code != 200:
                return None
            oid = r.json()['order_id']
            r = await client.post(f"{BASE_URL}/api/billing/webhook", json={
                "order_id": oid, "provider_tx_id": f"tx_{uuid.uuid4().hex[:8]}", "status": "success"
            })
            return oid if r.status_code == 200 else None

        emails = [f"bulk_{i}_{uuid.uuid4().hex[:4]}@example.com" for i in range(10)]
        results = await asyncio.gather(*[create_and_pay(e) for e in emails])
        success = sum(1 for r in results if r is not None)
        print(f"✅ Успешных: {success}/10")

        for e in emails:
            await cleanup(e)
        return success >= 8


async def test_race_condition_provisioning():
    print("\n📋 Тест 3: Race condition при создании")
    print("-" * 40)

    test_email = f"race_{uuid.uuid4().hex[:6]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def invoice_and_pay():
            r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
                "email": test_email, "tariff_slug": "sub_1m"
            })
            if r.status_code != 200:
                return False
            oid = r.json()['order_id']
            r = await client.post(f"{BASE_URL}/api/billing/webhook", json={
                "order_id": oid, "provider_tx_id": f"tx_{uuid.uuid4().hex[:8]}", "status": "success"
            })
            return r.status_code == 200

        await asyncio.gather(invoice_and_pay(), invoice_and_pay())
        await asyncio.sleep(3)

        r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
        days = r.json().get('days_left', 0) if r.status_code == 200 else 0
        print(f"✅ Дней: {days}")

        await cleanup(test_email)
        return 29 <= days <= 60


async def test_provisioning_background_tasks():
    print("\n📋 Тест 4: Фоновые задачи provisioning")
    print("-" * 40)

    test_email = f"bg_{uuid.uuid4().hex[:6]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
            "email": test_email, "tariff_slug": "sub_1m"
        })
        oid = r.json()['order_id']
        await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": oid, "provider_tx_id": "tx_bg", "status": "success"
        })
        print("✅ Оплата отправлена")

        for delay in [1, 3, 5]:
            await asyncio.sleep(delay)
            r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
            if r.status_code == 200:
                d = r.json()
                print(f"   Через {delay}с: active={d.get('is_active')}, дней={d.get('days_left')}")

        await cleanup(test_email)
        return True


async def main():
    print("=" * 60)
    print("🧪 ТЕСТ 09: Конкурентный провижининг")
    print("=" * 60)

    tests = [
        ("5 оплат одним", test_concurrent_same_user),
        ("10 разных пользователей", test_concurrent_different_users),
        ("Race condition", test_race_condition_provisioning),
        ("Фоновые задачи", test_provisioning_background_tasks),
    ]
    results = []
    for name, fn in tests:
        try:
            ok = await fn()
        except Exception as e:
            print(f"❌ {e}")
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
    print("✅ ТЕСТ 09 ПРОЙДЕН!" if all_pass else "❌ ТЕСТ 09 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return all_pass


if __name__ == "__main__":
    asyncio.run(main())
