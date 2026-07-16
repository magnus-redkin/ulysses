# tests/lib/test_helpers.py
"""
Общие хелперы для тестов.
"""
import httpx
import asyncio

BASE_URL = "http://127.0.0.1:8000"

async def pay_invoice(order_id: str):
    """Оплатить инвойс через вебхук."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": order_id,
            "provider_tx_id": f"tx_test_{order_id[:8]}",
            "status": "success"
        })
        return resp.status_code == 200


async def create_user_tg(tg_id: int, username: str, tariff: str = "sub_free"):
    """Создать пользователя через Telegram. Для платных — автооплата."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{BASE_URL}/api/bot/action", json={
            "tg_user_id": tg_id,
            "action": "buy_tariff",
            "payload": {"tariff_slug": tariff, "tg_username": username}
        })
        data = resp.json()

        # Если платный тариф — оплатить через вебхук
        if data.get("state") == "payment_pending" and data.get("order_id"):
            await pay_invoice(data["order_id"])
            await asyncio.sleep(2)  # ждать provisioning

        return data


async def create_user_email(email: str, tariff: str = "monthly"):
    """Создать пользователя через email и оплатить."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Создать инвойс
        resp = await client.post(f"{BASE_URL}/api/billing/create-invoice", json={
            "email": email, "tariff_slug": tariff
        })
        data = resp.json()
        order_id = data.get("order_id")

        # Оплатить
        await client.post(f"{BASE_URL}/api/billing/webhook", json={
            "order_id": order_id,
            "provider_tx_id": f"tx_{email}",
            "status": "success"
        })
        return data


async def get_user_balance(identifier, by: str = "tg_id"):
    """Получить баланс пользователя."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"tg_user_id": identifier} if by == "tg_id" else \
                 {"email": identifier} if by == "email" else \
                 {"hiddify_uuid": identifier}
        resp = await client.get(f"{BASE_URL}/api/user/balance", params=params)

        # 1. Если бэкенд выдал 404, проверяем тело ответа
        if resp.status_code == 404:
            # Если бэкенд честно говорит, что не нашел подписку/юзера по этому ТГ-фильтру
            # Для шага отвязки это означает успех (ТГ-привязки больше нет!)
            try:
                detail = resp.json().get("detail", "")
                if "not found" in detail.lower():
                    return None
            except Exception:
                pass

        if resp.status_code != 200:
            print(f"\n❌ [ОШИБКА ХЕЛПЕРА] Бэкенд вернул HTTP {resp.status_code} вместо JSON! Ответ: {resp.text}")
            return {"state": "error", "message": resp.text}

        if resp.status_code == 200:
            return resp.json()
        return None


async def get_bot_state(tg_id: int):
    """Получить состояние бота."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/api/bot/state", params={"tg_user_id": tg_id})
        return resp.json() if resp.status_code == 200 else None

async def cleanup_user(tg_id: int = None, email: str = None, uuid: str = None, target: str = "all"):
    """Удалить пользователя (БД + Hiddify)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"target": target}
        if tg_id: params["tg_user_id"] = tg_id
        elif email: params["email"] = email
        elif uuid: params["uuid"] = uuid

        resp = await client.delete(f"{BASE_URL}/api/admin/account", params=params)
        return resp.status_code == 200


async def check_anomalies(query: str = None):
    """Проверить аномалии в системе."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"query": query} if query else {}
        resp = await client.get(f"{BASE_URL}/api/admin/check", params=params)
        return resp.json() if resp.status_code == 200 else None# tests/lib/test_helpers.py
