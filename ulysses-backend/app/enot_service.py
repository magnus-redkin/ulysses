import httpx
import hashlib
from app.config import settings

ENOT_API_URL = "https://api.enot.io"


async def get_invoice_info(order_id: str) -> dict:
    """
    Запрашивает статус инвойса у Enot API.
    Возвращает стандартизированный словарь.
    """
    shop_id = settings.ENOT_SHOP_ID
    secret_key = settings.ENOT_SECRET_KEY

    if not shop_id or not secret_key:
        return {
            "status": "not_configured",
            "error": "Enot не настроен (ENOT_SHOP_ID, ENOT_SECRET_KEY)",
            "amount": "-",
            "currency": "RUB",
            "provider": "Enot.io",
            "created_at": "-"
        }

    sign = hashlib.md5(f"{shop_id}{order_id}{secret_key}".encode()).hexdigest()

    params = {
        "shop_id": shop_id,
        "order_id": order_id,
        "sign": sign
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{ENOT_API_URL}/invoice/status", params=params)

            if response.status_code != 200:
                return {
                    "status": "error",
                    "error": f"Enot API вернул {response.status_code}",
                    "amount": "-",
                    "currency": "RUB",
                    "provider": "Enot.io",
                    "created_at": "-"
                }

            data = response.json()
            enot_status = data.get("status", "unknown")

            status_map = {
                "paid": "success",
                "success": "success",
                "wait": "pending",
                "pending": "pending",
                "fail": "failed",
                "expired": "expired"
            }

            return {
                "status": status_map.get(enot_status, enot_status),
                "amount": data.get("amount", "-"),
                "currency": data.get("currency", "RUB"),
                "provider": "Enot.io",
                "created_at": data.get("created_at", "-"),
                "raw_status": enot_status
            }

    except httpx.ConnectError:
        return {
            "status": "error",
            "error": "Enot API недоступен",
            "amount": "-",
            "currency": "RUB",
            "provider": "Enot.io",
            "created_at": "-"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "amount": "-",
            "currency": "RUB",
            "provider": "Enot.io",
            "created_at": "-"
        }
