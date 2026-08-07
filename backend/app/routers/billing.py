# ulysses-backend/app/routers/billing.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional

from app.database import get_db
from app.dependencies import verify_api_key
from app.services.billing_service import create_invoice_logic
from app.services.activation_manager import get_tariffs


import logging

# curl -X POST http://127.0.0.1:8000/api/billing/create-invoice \
#   -H "Content-Type: application/json" \
#   -H "X-API-Key: 3mu6zk42E2E9v7zFoLViXbcCY4FVAYQc" \
#   -d '{"tg_user_id":880765948, "tariff_slug":"sub_24m", "currency":"RUB"}'


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ============================================================
# PYDANTIC МОДЕЛИ (Схемы валидации запросов)
# ============================================================

class InvoiceCreate(BaseModel):
    email: Optional[str] = Field(None, description="Email пользователя (необязательно, если передан tg_user_id)")
    tg_user_id: Optional[int] = Field(None, description="Telegram ID пользователя")
    tariff_slug: str = Field(..., description="Слаг тарифного плана")
    currency: Optional[str] = Field(None, description="Валюта (RUB, USD, EUR, USDT)")

class WebhookPayload(BaseModel):
    order_id: str = Field(..., description="ID инвойса в системе Ulysses")
    status: str = Field(..., description="Статус оплаты от агрегатора (success/failed)")
    provider_tx_id: str = Field(..., description="ID транзакции внутри платежной системы")


# ============================================================
# ЭНДПОИНТЫ БИЛЛИНГА
# ============================================================

@router.get("/tariffs")
async def get_tariffs_endpoint():
    """Публичный эндпоинт для получения тарифов."""
    return get_tariffs()

@router.post("/create-invoice")
async def create_invoice(
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    try:
        result = await create_invoice_logic(db, email=payload.email, tg_user_id=payload.tg_user_id, tariff_slug=payload.tariff_slug, currency=payload.currency)
        await db.commit()
        return result
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        await db.rollback()
        raise


@router.post("/webhook")
async def payment_webhook(request: Request):
    """Обработка вебхука от Platega (публичный)."""
    from app.services.platega_webhook_handler import handle_platega_webhook
    headers = dict(request.headers)
    body_str = await request.body()
    return await handle_platega_webhook(headers, body_str.decode())
