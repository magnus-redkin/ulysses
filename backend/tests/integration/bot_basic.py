# ulysses-backend/tests/test_basic_commands.py

import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"

async def test_smoke_routes():
    print("🧪 [Шаг 0] Запуск смоук-тестов роутинга Ulysses API...")

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # 1. Проверяем главный health-check
            res = await client.get(f"{BASE_URL}/health")
            assert res.status_code == 200, f"Ошибка /health: {res.text}"
            print("  ✅ GET /health → 200 OK")

            # 2. Проверяем доступность тарифов
            res = await client.get(f"{BASE_URL}/api/billing/tariffs")
            assert res.status_code == 200, f"Ошибка /api/billing/tariffs: {res.text}"
            assert isinstance(res.json(), dict), "Тарифы должны быть словарем JSON"
            print("  ✅ GET /api/billing/tariffs → 200 OK")

            # 3. Проверяем стейт для несуществующего юзера бота (должен вернуть state='new')
            res = await client.get(f"{BASE_URL}/api/bot/state?tg_user_id=88889999")
            assert res.status_code == 200, f"Ошибка /api/bot/state: {res.text}"
            data = res.json()
            assert data.get("state") == "new", f"Ожидался статус 'new', получен: {data.get('state')}"
            print("  ✅ GET /api/bot/state (Новый пользователь) → 200 OK (state: new)")

            # 4. Проверяем админскую статистику
            res = await client.get(f"{BASE_URL}/api/admin/stats")
            assert res.status_code == 200, f"Ошибка /api/admin/stats: {res.text}"
            assert "total_users" in res.json(), "В статистике должно быть поле total_users"
            print("  ✅ GET /api/admin/stats → 200 OK")

            print("\n🎉 [Шаг 0] Все базовые роуты успешно прошли проверку после рефакторинга!")

        except httpx.ConnectError:
            print(f"\n❌ Ошибка подключения: Не удалось связаться с бэкендом по адресу {BASE_URL}")
            print("   Убедитесь, что сервер uvicorn запущен и слушает порт 8000.")
        except AssertionError as e:
            print(f"\n❌ Ошибка валидации данных: {e}")
        except Exception as e:
            print(f"\n❌ Непредвиденная ошибка при прогоне теста: {e}")

if __name__ == "__main__":
    asyncio.run(test_smoke_routes())
