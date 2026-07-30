# ulysses-backend/app/routers/billing.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import verify_api_key
from app.services.billing_service import create_invoice_logic
from app.services.activation_manager import get_tariffs
from app.models import PaymentAttempt  # если нужен для invoice-status

from pydantic import BaseModel, Field
from typing import Optional

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
    currency: Optional[str] = Field("RUB", description="Валюта (RUB, USD, EUR, USDT)")

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
    """Создание инвойса (требует X-API-Key)."""
    try:
        result = await create_invoice_logic(
            db,
            email=payload.email,
            tg_user_id=payload.tg_user_id,
            tariff_slug=payload.tariff_slug,
            currency=payload.currency
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook")
async def payment_webhook(request: Request):
    """Обработка вебхука от Platega (публичный)."""
    from app.services.platega_webhook_handler import handle_platega_webhook
    headers = dict(request.headers)
    body_str = await request.body()
    return await handle_platega_webhook(headers, body_str.decode())




@router.get("/invoice-status/{order_id}")
async def get_invoice_status(order_id: str, db: AsyncSession = Depends(get_db)):
    """Проверка статуса инвойса и связанной с ним подписки для бота."""
    try:
        invoice_id = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    result = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == invoice_id))
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Invoice not found")

    subscription_info = None
    if attempt.user_id:
        sub_result = await db.execute(text("""
            SELECT id, status, expires_at, tariff_slug
            FROM subscriptions WHERE user_id = :user_id
            ORDER BY expires_at DESC LIMIT 1
        """), {"user_id": attempt.user_id})
        sub_row = sub_result.fetchone()
        if sub_row:
            subscription_info = {
                "subscription_id": sub_row[0],
                "status": sub_row[1],
                "expires_at": sub_row[2].isoformat() if sub_row[2] else None,
                "tariff_slug": sub_row[3]
            }

    return {
        "status": attempt.status,
        "order_id": str(attempt.id),
        "amount": float(attempt.amount),
        "tariff_slug": attempt.tariff_slug,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        "subscription": subscription_info
    }


@router.get("/subscription/{hiddify_uuid}")
async def get_subscription_status(hiddify_uuid: str, db: AsyncSession = Depends(get_db)):
    """Получение статуса последней подписки по UUID пользователя."""
    try:
        target_uuid = uuid.UUID(hiddify_uuid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    user_result = await db.execute(select(User).where(User.hiddify_uuid == target_uuid))
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User with this VPN profile not found")

    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.expires_at.desc()).limit(1)
    )
    subscription = sub_result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription history is empty for this user")

    return subscription.to_dict()


@router.post("/retry-provisioning/{subscription_id}")
async def retry_provisioning(subscription_id: int, db: AsyncSession = Depends(get_db)):
    """Ручной повтор provisioning (для администратора)"""
    manager = ProvisioningManager(db)
    success = await manager.provision_subscription(subscription_id)

    if success:
        return {"status": "activated", "subscription_id": subscription_id}
    else:
        return {
            "status": "failed",
            "subscription_id": subscription_id,
            "message": "Не удалось активировать. Проверьте логи бэкенда."
        }
