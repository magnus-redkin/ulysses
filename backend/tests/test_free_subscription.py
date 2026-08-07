# tests/test_free_subscription.py
"""
Тест: активация бесплатного тарифа sub_free.
Проверяет:
  1. Создание подписки через /api/billing/create-invoice с sub_free.
  2. Наличие активной подписки в ответе и в БД.
  3. Очистка: удаление тестового пользователя из БД и с Hiddify.
Запуск: utest backend/tests/test_free_subscription.py
"""
import httpx
import asyncio
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.config import settings
from app.services.hiddify_client import HiddifyProvisioner
from sqlalchemy import text

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc"

TEST_TG_ID = 900001000  # уникальный tg_id для этого теста


async def test_free_subscription_activation():
    """
    Активируем sub_free через API, проверяем результат, чистим за собой.
    """
    tg_id = TEST_TG_ID
    hiddify_uuid = None

    try:
        # 1. Регистрируем тестового пользователя через бота
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BASE_URL}/api/bot/register",
                headers={"X-API-Key": API_KEY},
                json={
                    "tg_user_id": tg_id,
                    "tg_username": f"test_free_{tg_id}",
                    "hiddify_uuid": None
                }
            )
        print(f"  Регистрация: {resp.status_code} {resp.json()}")
        assert resp.status_code == 200, f"Ошибка регистрации: {resp.text}"

        # 2. Получаем UUID пользователя через баланс
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BASE_URL}/api/user/balance",
                headers={"X-API-Key": API_KEY},
                params={"tg_user_id": tg_id}
            )
        assert resp.status_code == 200, f"Ошибка получения баланса: {resp.text}"
        balance = resp.json()
        hiddify_uuid = balance.get("hiddify_uuid")
        assert hiddify_uuid, "UUID не найден в ответе"
        print(f"  UUID пользователя: {hiddify_uuid}")

        # 3. Активируем sub_free через billing
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BASE_URL}/api/billing/create-invoice",
                headers={"X-API-Key": API_KEY},
                json={
                    "tg_user_id": tg_id,
                    "tariff_slug": "sub_free"
                }
            )
        print(f"  Активация: {resp.status_code}")
        assert resp.status_code == 200, f"Ошибка активации: {resp.text}"
        data = resp.json()
        assert data.get("status") == "free_tariff", f"Неожиданный статус: {data.get('status')}"
        assert data.get("subscription_link"), "Отсутствует subscription_link"
        print(f"  Ссылка: {data['subscription_link']}")

        # 4. Проверяем в БД, что подписка активна
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                text("""
                    SELECT s.status, s.tariff_slug, s.expires_at
                    FROM subscriptions s
                    JOIN users u ON s.user_id = u.id
                    WHERE u.tg_user_id = :tg_id
                    ORDER BY s.id DESC LIMIT 1
                """),
                {"tg_id": tg_id}
            )
            sub = res.fetchone()
            assert sub is not None, "Подписка не найдена в БД"
            assert sub[0] == "active", f"Статус подписки не active: {sub[0]}"
            assert sub[1] == "sub_free", f"Тариф не sub_free: {sub[1]}"
            print(f"  БД: статус={sub[0]}, тариф={sub[1]}, истекает={sub[2]}")

        print("✅ test_free_subscription_activation PASSED")

    finally:
        # 5. Очистка: удаляем пользователя из БД и с Hiddify
        if hiddify_uuid:
            provisioner = HiddifyProvisioner()
            delete_result = await provisioner.delete_user(hiddify_uuid)
            print(f"  🧹 Hiddify: удаление пользователя {hiddify_uuid} — {'успешно' if delete_result['success'] else 'ошибка'}")

        async with AsyncSessionLocal() as session:
            try:
                await session.execute(
                    text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = :tg_id)"),
                    {"tg_id": tg_id}
                )
                await session.execute(
                    text("DELETE FROM users WHERE tg_user_id = :tg_id"),
                    {"tg_id": tg_id}
                )
                await session.commit()
                print(f"  🧹 БД: тестовый пользователь tg_id={tg_id} удалён")
            except Exception as e:
                await session.rollback()
                print(f"  ⚠️ Не удалось удалить тестового пользователя: {e}")


async def main():
    await test_free_subscription_activation()


if __name__ == "__main__":
    asyncio.run(main())
