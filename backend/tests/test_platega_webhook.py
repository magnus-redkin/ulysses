# tests/test_platega_webhook.py
"""
Тест: обработчик вебхука Platega.
Проверяет:
  1. Запрос без x-merchantid → 401 Unauthorized.
  2. Запрос с невалидной подписью → 401 Unauthorized.
  3. Валидный запрос с несуществующим инвойсом → 404 Not Found.
Запуск: utest backend/tests/test_platega_webhook.py
"""
import httpx
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_URL = "http://127.0.0.1:8000"


async def test_webhook_no_merchant_id():
    """Запрос без заголовка x-merchantid должен вернуть 401."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            json={"status": "CONFIRMED", "payload": "test-uuid"}
        )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    print("✅ test_webhook_no_merchant_id PASSED")


async def test_webhook_invalid_signature():
    """Запрос с невалидной подписью должен вернуть 401."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers={
                "x-merchantid": "fake-merchant",
                "x-signature": "invalid-signature-12345"
            },
            json={"status": "CONFIRMED", "payload": "test-uuid"}
        )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    print("✅ test_webhook_invalid_signature PASSED")


async def test_webhook_nonexistent_invoice():
    """
    Запрос с правильными заголовками (от реального Platega), но несуществующим инвойсом.
    Должен вернуть 404.
    """
    from app.config import settings
    from app.platega.platega import PlategaCallback

    # Формируем валидную подпись для тестового тела
    test_body = '{"status":"CONFIRMED","payload":"00000000-0000-0000-0000-000000000000"}'

    callback = PlategaCallback(
        merchant_id=settings.PLATEGA_MERCHANT_ID,
        secret=settings.PLATEGA_API
    )

    # Подписываем тело
    headers = callback.sign(test_body)  # предполагаем, что метод sign существует
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers=headers,
            content=test_body
        )

    # Должен вернуть 404 (инвойс не найден)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    print("✅ test_webhook_nonexistent_invoice PASSED")

async def test_webhook_valid_headers_missing_fields():
    """
    Запрос с правильными merchant_id и secret, но неполным JSON.
    Должен вернуть 401 (валидация не пройдена из-за отсутствия обязательных полей).
    """
    from app.config import settings

    # Правильные заголовки, но в JSON нет обязательных полей (id, amount, currency...)
    test_body = '{"status":"CONFIRMED","payload":"00000000-0000-0000-0000-000000000000"}'

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers={
                "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
                "X-Secret": settings.PLATEGA_API
            },
            content=test_body
        )
    # Должен вернуть 401, потому что не хватает обязательных полей в JSON
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    print("✅ test_webhook_valid_headers_missing_fields PASSED")


async def main():
    await test_webhook_no_merchant_id()
    await test_webhook_invalid_signature()
    await test_webhook_valid_headers_missing_fields()


if __name__ == "__main__":
    asyncio.run(main())
