# tests/lib/test_helpers.py
"""
Общие хелперы для тестов.
"""
import httpx
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.hiddify_client import HiddifyProvisioner
from sqlalchemy import text

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc"


async def pay_invoice(order_id: str):
    """Оплатить инвойс через вебхук."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/webhook",
            headers={
                "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
                "X-Secret": settings.PLATEGA_API
            },
            json={
                "id": f"tx_test_{order_id[:8]}",
                "amount": 499.0,
                "currency": "RUB",
                "status": "CONFIRMED",
                "paymentMethod": 10,
                "payload": order_id
            }
        )
        return resp.status_code == 200

async def create_user_tg(tg_id: int, username: str, tariff: str = "sub_free"):
    """Создать пользователя через Telegram. Для платных — автооплата."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Для sub_free передаём payment_type сразу, чтобы не получать select_payment_type
        payload = {"tariff_slug": tariff, "tg_username": username}
        if tariff == "sub_free":
            payload["payment_type"] = "rub"

        resp = await client.post(
            f"{BASE_URL}/api/bot/action",
            headers={"X-API-Key": API_KEY},
            json={
                "tg_user_id": tg_id,
                "action": "buy_tariff",
                "payload": payload
            }
        )
        data = resp.json()

        if data.get("state") == "payment_pending" and data.get("order_id"):
            await pay_invoice(data["order_id"])
            await asyncio.sleep(2)

        return data



async def create_user_email(email: str, tariff: str = "monthly"):
    """Создать пользователя через email и оплатить."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BASE_URL}/api/billing/create-invoice",
            headers={"X-API-Key": API_KEY},
            json={"email": email, "tariff_slug": tariff}
        )
        data = resp.json()
        order_id = data.get("order_id")

        if order_id:
            await pay_invoice(order_id)
        return data


async def get_user_balance(identifier, by: str = "tg_id"):
    """Получить баланс пользователя."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"tg_user_id": identifier} if by == "tg_id" else \
                 {"email": identifier} if by == "email" else \
                 {"hiddify_uuid": identifier}
        resp = await client.get(
            f"{BASE_URL}/api/user/balance",
            headers={"X-API-Key": API_KEY},
            params=params
        )

        if resp.status_code == 404:
            try:
                detail = resp.json().get("detail", "")
                if "not found" in detail.lower():
                    return None
            except Exception:
                pass

        if resp.status_code != 200:
            return None

        return resp.json()


async def get_bot_state(tg_id: int):
    """Получить состояние бота."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{BASE_URL}/api/bot/state",
            headers={"X-API-Key": API_KEY},
            params={"tg_user_id": tg_id}
        )
        return resp.json() if resp.status_code == 200 else None


async def cleanup_user(tg_id: int = None, email: str = None, uuid: str = None, target: str = "all"):
    """Удалить пользователя: БД + Hiddify (прямой доступ)."""
    hiddify_uuid = None

    # 1. Получаем UUID если есть tg_id или email
    if tg_id or email or uuid:
        async with AsyncSessionLocal() as session:
            if tg_id:
                res = await session.execute(
                    text("SELECT hiddify_uuid, email FROM users WHERE tg_user_id = :id"),
                    {"id": tg_id}
                )
            elif email:
                res = await session.execute(
                    text("SELECT hiddify_uuid, email FROM users WHERE email = :email"),
                    {"email": email}
                )
            elif uuid:
                res = await session.execute(
                    text("SELECT hiddify_uuid, email FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid"),
                    {"uuid": uuid}
                )
            row = res.fetchone()
            if row:
                hiddify_uuid = str(row[0])

            # Удаляем из БД
            try:
                if tg_id:
                    await session.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = :id)"), {"id": tg_id})
                    await session.execute(text("DELETE FROM payment_attempts WHERE user_id IN (SELECT id FROM users WHERE tg_user_id = :id)"), {"id": tg_id})
                    await session.execute(text("DELETE FROM users WHERE tg_user_id = :id"), {"id": tg_id})
                elif email:
                    await session.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email = :email)"), {"email": email})
                    await session.execute(text("DELETE FROM payment_attempts WHERE user_id IN (SELECT id FROM users WHERE email = :email)"), {"email": email})
                    await session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
                elif uuid:
                    await session.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid)"), {"uuid": uuid})
                    await session.execute(text("DELETE FROM payment_attempts WHERE user_id IN (SELECT id FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid)"), {"uuid": uuid})
                    await session.execute(text("DELETE FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid"), {"uuid": uuid})
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"   ⚠️ Ошибка удаления из БД: {e}")
                return False

    # 2. Удаляем из Hiddify
    if hiddify_uuid:
        try:
            provisioner = HiddifyProvisioner()
            await provisioner.delete_user(hiddify_uuid)
        except Exception as e:
            print(f"   ⚠️ Ошибка удаления из Hiddify: {e}")

    return True


async def check_anomalies(query: str = None):
    """Проверить аномалии в системе."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"query": query} if query else {}
        resp = await client.get(
            f"{BASE_URL}/api/admin/check",
            headers={"X-API-Key": API_KEY},
            params=params
        )
        return resp.json() if resp.status_code == 200 else None
