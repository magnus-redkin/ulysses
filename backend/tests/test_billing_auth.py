# tests/test_billing_auth.py
"""
Тест: создание инвойса с авторизацией и без.
Запуск: utest backend/tests/test_billing_auth.py
"""
import httpx
import asyncio

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc"

async def test_no_auth_returns_401():
    """Без API-ключа должен вернуть 401 Unauthorized."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            json={"tg_user_id": 123, "tariff_slug": "sub_free"}
        )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    print("✅ test_no_auth_returns_401 PASSED")

async def test_with_auth_works():
    """С ключом должен вернуть 200 (или 400, если юзера нет, но не 401/403)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            headers={"X-API-Key": API_KEY},
            json={"tg_user_id": 123, "tariff_slug": "sub_free"}
        )
    assert resp.status_code not in (401, 403), f"Got {resp.status_code}: {resp.text}"
    print(f"✅ test_with_auth_works PASSED (status {resp.status_code})")


async def cleanup():
    """Удалить тестового пользователя tg_id=123."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = 123)"))
        await session.execute(text("DELETE FROM payment_attempts WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = 123)"))
        await session.execute(text("DELETE FROM users WHERE tg_user_id = 123"))
        await session.commit()

async def main():
    await test_no_auth_returns_401()
    await test_with_auth_works()
    await cleanup()
    print("🧹 Очистка завершена")

if __name__ == "__main__":
    asyncio.run(main())
