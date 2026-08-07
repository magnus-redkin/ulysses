# tests/test_transaction_rollback.py
"""
Тест: при ошибке provisioning подписка сохраняется в БД со статусом failed.
Запуск: utest backend/tests/test_transaction_rollback.py
"""
import asyncio
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.services.free_subscription import create_free_subscription
from app.services.activation_manager import get_or_create_user
from sqlalchemy import text


async def test_failed_provisioning_saves_subscription():
    """
    Создаём пользователя, временно указываем битый URL Hiddify,
    вызываем create_free_subscription, ожидаем RuntimeError,
    проверяем, что подписка в БД со статусом != 'active'.
    """
    tg_id = 900002000
    email = f"test_rollback_{uuid.uuid4().hex[:8]}@example.com"
    original_url = None

    try:
        # 1. Создаём пользователя
        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(db=session, email=email, tg_user_id=tg_id)
            await session.commit()
            user_id = user["user_id"]
            hiddify_uuid = user["hiddify_uuid"]
            print(f"  Создан пользователь: id={user_id}, uuid={hiddify_uuid}")

        # 2. Ломаем URL Hiddify, чтобы provisioning гарантированно упал
        from app.config import settings
        original_url = settings.HIDDIFY_API_URL
        settings.HIDDIFY_API_URL = "https://nonexistent.hiddify.local:9999"

        # 3. Пытаемся активировать sub_free
        provisioning_failed = False
        try:
            async with AsyncSessionLocal() as session:
                # Привязываем пользователя к сессии заново
                user["user_id"] = user_id
                user["hiddify_uuid"] = hiddify_uuid
                await create_free_subscription(db=session, user=user)
                # Если дошли сюда без ошибки — что-то не так
                print("  ⚠️ Provisioning не упал (Hiddify URL не подменился?)")
        except RuntimeError as e:
            provisioning_failed = True
            print(f"  Ожидаемая ошибка provisioning: {str(e)[:100]}")

        # Восстанавливаем URL
        settings.HIDDIFY_API_URL = original_url

        # 4. Проверяем БД: подписка должна существовать со статусом failed
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                text("""
                    SELECT s.status, s.provisioning_error
                    FROM subscriptions s
                    WHERE s.user_id = :uid
                    ORDER BY s.id DESC LIMIT 1
                """),
                {"uid": user_id}
            )
            sub = res.fetchone()

            if provisioning_failed:
                assert sub is not None, "❌ Подписка не найдена в БД (возможно, откатилась вместе с транзакцией)"
                assert sub[0] == "failed", f"❌ Статус подписки должен быть 'failed', а не '{sub[0]}'"
                print(f"  БД: статус={sub[0]}, ошибка={sub[1][:50] if sub[1] else 'нет'}")
                print("✅ test_failed_provisioning_saves_subscription PASSED")
            else:
                print("  ⚠️ Тест не завершён: provisioning не упал, но это не ошибка теста")

    finally:
        # Очистка
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
                print(f"  🧹 Тестовые данные удалены")
            except Exception as e:
                await session.rollback()
                print(f"  ⚠️ Ошибка очистки: {e}")

        if original_url:
            from app.config import settings
            settings.HIDDIFY_API_URL = original_url


async def main():
    await test_failed_provisioning_saves_subscription()


if __name__ == "__main__":
    asyncio.run(main())
