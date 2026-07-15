# check_user.py - положи в корень проекта
import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def check_user(tg_id: int):
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        # Проверяем пользователя
        query = text("""
            SELECT
                u.id,
                u.email,
                u.tg_user_id,
                u.tg_username,
                s.id as sub_id,
                s.hiddify_uuid,
                s.status
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id
        """)

        result = await db.execute(query, {"tg_id": tg_id})
        rows = result.fetchall()

        if rows:
            for row in rows:
                print(f"User ID: {row[0]}")
                print(f"Email: {row[1]}")
                print(f"TG ID: {row[2]}")
                print(f"TG Username: {row[3]}")
                print(f"Subscription ID: {row[4]}")
                print(f"Hiddify UUID: {row[5]}")
                print(f"Status: {row[6]}")
                print("-" * 50)
        else:
            print(f"Пользователь с tg_id={tg_id} не найден")

    await engine.dispose()

if __name__ == "__main__":
    # Твой Telegram ID
    YOUR_TG_ID = 8397318328  # 12345 Замени на свой!
    asyncio.run(check_user(YOUR_TG_ID))
