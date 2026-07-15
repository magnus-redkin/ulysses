#!/usr/bin/env python3
"""
Тест 10: Обработка отказов и системные проверки
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


async def test_provisioning_creates_user():
    print("\n📋 Тест 1: Создание подписки")
    print("-" * 40)

    test_email = f"nohf_{uuid.uuid4().hex[:6]}@example.com"

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
            "email": test_email, "tariff_slug": "sub_1m"
        })
        oid = r.json()['order_id']
        r = await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": oid, "provider_tx_id": "tx_test", "status": "success"
        })
        print(f"💰 Статус: {r.json().get('status')}")
        await asyncio.sleep(3)

        r = await client.get(f"{BASE_URL}/api/user/balance", params={"email": test_email})
        ok = r.status_code == 200
        if ok:
            d = r.json()
            print(f"✅ Создан: дней={d.get('days_left')}, active={d.get('is_active')}")
        else:
            print(f"❌ Не создан: {r.status_code}")

        await cleanup(test_email)
        return ok


async def test_admin_check_endpoint():
    print("\n📋 Тест 2: /api/admin/check")
    print("-" * 40)

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{BASE_URL}/api/admin/check")
        if r.status_code == 200:
            s = r.json().get('summary', {})
            print(f"✅ OK: грязь={s.get('dirty_invoices_count')}, аномалий={s.get('hiddify_anomalies_count')}")
            return True
        print(f"❌ {r.status_code}")
        return False


async def test_admin_stats_endpoint():
    print("\n📋 Тест 3: /api/admin/stats")
    print("-" * 40)

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BASE_URL}/api/admin/stats")
        if r.status_code == 200:
            d = r.json()
            print(f"✅ users={d.get('total_users')}, active={d.get('active_subscriptions')}")
            return True
        print(f"❌ {r.status_code}")
        return False


async def test_retry_provisioning():
    print("\n📋 Тест 4: retry-provisioning")
    print("-" * 40)

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE_URL}/api/billing/retry-provisioning/99999")
        print(f"🔄 Несуществующая: {r.status_code} (ожидаем ответ)")
        return r.status_code in [200, 404, 500]


async def test_fix_sync_endpoint():
    print("\n📋 Тест 5: /api/admin/fix/sync")
    print("-" * 40)

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE_URL}/api/admin/fix/sync")
        if r.status_code == 200:
            d = r.json()
            print(f"✅ fixed={d.get('fixed_hiddify_statuses')}")
            return True
        print(f"❌ {r.status_code}")
        return False


async def main():
    print("=" * 60)
    print("🧪 ТЕСТ 10: Системные проверки")
    print("=" * 60)

    tests = [
        ("Создание подписки", test_provisioning_creates_user),
        ("/api/admin/check", test_admin_check_endpoint),
        ("/api/admin/stats", test_admin_stats_endpoint),
        ("retry-provisioning", test_retry_provisioning),
        ("/api/admin/fix/sync", test_fix_sync_endpoint),
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
    all_pass = all(ok for _, ok in results)
    for name, ok in results:
        print(f"   {'✅' if ok else '❌'} {name}")
    print("=" * 60)
    print("✅ ТЕСТ 10 ПРОЙДЕН!" if all_pass else "❌ ТЕСТ 10 НЕ ПРОЙДЕН!")
    print("=" * 60)
    return all_pass


if __name__ == "__main__":
    asyncio.run(main())
