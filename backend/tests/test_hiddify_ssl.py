# tests/test_hiddify_ssl.py
"""
Тест: SSL-верификация при соединении с Hiddify.
Проверяет, что httpx.AsyncClient с verify=True (по умолчанию) успешно подключается к HFM API.
Запуск: utest backend/tests/test_hiddify_ssl.py
"""
import httpx
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings

async def test_hiddify_ssl_connection():
    """
    Явно создаём httpx.AsyncClient с verify=True и делаем запрос к HFM.
    Если сертификат невалидный — упадёт с ошибкой SSL.
    """
    base_url = settings.HIDDIFY_API_URL.rstrip("/")
    url = f"{base_url}/api/v2/admin/user/"

    headers = {
        "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
        "Accept": "application/json"
    }

    print(f"  URL: {url}")

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
            resp = await client.get(url, headers=headers)
        print(f"  Статус: {resp.status_code}")
        # 200 — список пользователей, 401/403 — нет прав, но SSL работает
        # Главное — нет исключения SSL error
        assert resp.status_code in (200, 401, 403), f"Неожиданный статус: {resp.status_code}"
        print("✅ test_hiddify_ssl_connection PASSED")
    except httpx.ConnectError as e:
        if "SSL" in str(e) or "certificate" in str(e).lower():
            raise AssertionError(f"❌ SSL-верификация не пройдена: {e}")
        raise  # другая ошибка соединения

async def main():
    await test_hiddify_ssl_connection()

if __name__ == "__main__":
    asyncio.run(main())
