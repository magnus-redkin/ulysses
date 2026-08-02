# /app/platega/platega_service.py

import asyncio
import httpx
from typing import Dict, Any, Optional
from app.config import settings

class PlategaPaymentService:
    """Провайдер Platega – прямой HTTP без SDK, создаёт универсальную ссылку."""

    def __init__(self):
        self.merchant_id = settings.PLATEGA_MERCHANT_ID
        self.secret = settings.PLATEGA_API
        self.api_url = "https://app.platega.io/v2/transaction/process"

    async def create_invoice_link(
        self,
        amount: float,
        attempt_id: str,
        tariff_name: str,
        currency: Optional[str] = None,
        user_telegram_id: Optional[int] = None,
        username: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Генерирует платёжную ссылку БЕЗ paymentMethod.
        Плательщик на стороне Platega сам выберет способ оплаты.
        """
        base_domain = "ulysses.best"
        final_currency = str(currency).upper().strip() if currency else "RUB"

        payload = {
            "paymentDetails": {
                "amount": float(amount),
                "currency": final_currency
            },
            "description": f"Оплата подписки Ulysses VPN: {tariff_name}",
            "return": f"https://{base_domain}/payment/success",
            "failedUrl": f"https://{base_domain}/payment/fail",
            "payload": str(attempt_id)
        }

        if user_telegram_id is not None:
            payload["metadata"] = {
                "userId": str(user_telegram_id),
                "userName": f"@{username}" if username else ""
            }

        headers = {
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.api_url, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                else:
                    print(f"❌ [PLATEGA] HTTP {resp.status_code}: {resp.text}")
                    return None
        except Exception as e:
            print(f"❌ [PLATEGA SERVICE] Ошибка при запросе к API: {e}")
            return None
