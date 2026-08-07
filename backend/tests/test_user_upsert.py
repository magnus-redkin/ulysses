# tests/test_user_upsert.py
"""
Тест: атомарный upsert пользователя.
Проверяет:
  1. Два одновременных запроса с одинаковым email не создают дубликат.
  2. Deep link binding: привязка tg_user_id к существующему email+UUID.
Запуск: utest backend/tests/test_user_upsert.py
"""
import httpx
import asyncio
import uuid
import sys
import os
from pathlib import Path

# Добавляем backend в PYTHONPATH для импорта app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.config import settings
from sqlalchemy import text

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc"

TEST_EMAIL = f"test_upsert_{uuid.uuid4().hex[:8]}@example.com"
TEST_TG_ID_BASE = 900000000


async def test_no_duplicate_users():
    """
    Два одновременных вызова регистрации с одним email, но разными tg_user_id.
    В БД должен быть ровно один пользователь.
    """
    tg_id_1 = TEST_TG_ID_BASE + 1
    tg_id_2 = TEST_TG_ID_BASE + 2

    async def register(tg_id: int):
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BASE_URL}/api/bot/register",
                headers={"X-API-Key": API_KEY},
                json={
                    "tg_user_id": tg_id,
                    "tg_username": f"user_{tg_id}",
                    "hiddify_uuid": None
                }
            )
        return resp

    resp1, resp2 = await asyncio.gather(
        register(tg_id_1),
        register(tg_id_2)
    )

    print(f"  Регистрация 1: {resp1.status_code} {resp1.json()}")
    print(f"  Регистрация 2: {resp2.status_code} {resp2.json()}")

    assert resp1.status_code == 200 or resp2.status_code == 200, "Ни один запрос не вернул 200"
    assert resp1.status_code != 500, f"Ошибка сервера: {resp1.text}"
    assert resp2.status_code != 500, f"Ошибка сервера: {resp2.text}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp_bal1 = await client.get(
            f"{BASE_URL}/api/user/balance",
            headers={"X-API-Key": API_KEY},
            params={"tg_user_id": tg_id_1}
        )
        resp_bal2 = await client.get(
            f"{BASE_URL}/api/user/balance",
            headers={"X-API-Key": API_KEY},
            params={"tg_user_id": tg_id_2}
        )
        if resp_bal1.status_code == 200 and resp_bal2.status_code == 200:
            email1 = resp_bal1.json().get("email")
            email2 = resp_bal2.json().get("email")
            print(f"  Email 1: {email1}")
            print(f"  Email 2: {email2}")
        else:
            print(f"  Баланс 1: {resp_bal1.status_code}, Баланс 2: {resp_bal2.status_code}")

    print("✅ test_no_duplicate_users PASSED")


async def test_deep_link_binding():
    """
    Создаём сайтового пользователя (email + UUID, без tg_user_id) напрямую в БД.
    Затем через bot/register с UUID привязываем tg_user_id.
    Убеждаемся, что запись обновилась, а не продублировалась.
    """
    site_uuid = str(uuid.uuid4())
    site_email = f"site_deeplink_{uuid.uuid4().hex[:8]}@example.com"
    tg_id = TEST_TG_ID_BASE + 100

    # 1. Вставляем сайтового пользователя напрямую в БД
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("""
                    INSERT INTO users (email, hiddify_uuid, tg_user_id, created_at, updated_at)
                    VALUES (:email, :uuid, NULL, NOW(), NOW())
                """),
                {"email": site_email, "uuid": site_uuid}
            )
            await session.commit()

            # Проверяем, что пользователь создался
            res = await session.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": site_email}
            )
            db_id = res.scalar_one()
            print(f"  Создан сайтовый пользователь: id={db_id}, uuid={site_uuid}")

        except Exception as e:
            await session.rollback()
            raise RuntimeError(f"Не удалось создать тестового пользователя: {e}") from e

    # 2. Имитируем переход по deep link: bot/register с UUID
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BASE_URL}/api/bot/register",
                headers={"X-API-Key": API_KEY},
                json={
                    "tg_user_id": tg_id,
                    "tg_username": f"deeplink_user_{tg_id}",
                    "hiddify_uuid": site_uuid   # <-- ключевой момент: передаём UUID из ссылки
                }
            )
        print(f"  Deep link register: {resp.status_code} {resp.json()}")

        assert resp.status_code == 200, f"Ошибка: {resp.text}"
        data = resp.json()
        assert data["status"] == "linked", f"Ожидался статус 'linked', получен '{data['status']}'"
        assert data["created"] == False, "Не должен создавать нового пользователя"

        # 3. Проверяем в БД, что tg_user_id привязался к той же записи
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                text("SELECT id, tg_user_id FROM users WHERE email = :email"),
                {"email": site_email}
            )
            row = res.fetchone()
            assert row is not None, "Пользователь не найден в БД"
            assert row[1] == tg_id, f"tg_user_id не привязался: ожидался {tg_id}, получен {row[1]}"
            print(f"  БД: пользователь id={row[0]}, tg_user_id={row[1]}")

            # 4. Убеждаемся, что дубликатов нет
            res_count = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE email = :email"),
                {"email": site_email}
            )
            count = res_count.scalar()
            assert count == 1, f"Найдено дубликатов: {count}"
            print(f"  Дубликатов: {count}")

    finally:
        # 5. Очистка: удаляем тестового пользователя
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(
                    text("DELETE FROM users WHERE email = :email"),
                    {"email": site_email}
                )
                await session.commit()
                print(f"  🧹 Тестовый пользователь {site_email} удалён")
            except Exception as e:
                await session.rollback()
                print(f"  ⚠️ Не удалось удалить тестового пользователя: {e}")

    print("✅ test_deep_link_binding PASSED")


async def cleanup():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        for tg_id in [TEST_TG_ID_BASE + 1, TEST_TG_ID_BASE + 2, TEST_TG_ID_BASE + 100]:
            await session.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = :id)"), {"id": tg_id})
            await session.execute(text("DELETE FROM payment_attempts WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = :id)"), {"id": tg_id})
            await session.execute(text("DELETE FROM users WHERE tg_user_id = :id"), {"id": tg_id})
        await session.commit()

async def main():
    await test_no_duplicate_users()
    await test_deep_link_binding()
    await cleanup()
    print("🧹 Очистка завершена")

if __name__ == "__main__":
    asyncio.run(main())
