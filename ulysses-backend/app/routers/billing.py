# ulysses-backend/app/routers/billing.py

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from datetime import datetime, timedelta
import uuid
import json
from pathlib import Path
import logging

from app.database import get_db
from app.config import settings
from app.models import User, Subscription, PaymentAttempt  # Ваши ORM модели
from app.provisioning_service import ProvisioningManager, provision_and_notify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

# ============================================================
# PYDANTIC МОДЕЛИ (Схемы валидации запросов)
# ============================================================

class InvoiceCreate(BaseModel):
    email: str = Field(..., description="Email пользователя или заглушка бота")
    tariff_slug: str = Field(..., description="Слаг тарифного плана")

class WebhookPayload(BaseModel):
    order_id: str = Field(..., description="ID инвойса в системе Ulysses")
    status: str = Field(..., description="Статус оплаты от агрегатора (success/failed)")
    provider_tx_id: str = Field(..., description="ID транзакции внутри платежной системы")


# ============================================================
# ЭНДПОИНТЫ БИЛЛИНГА
# ============================================================

@router.get("/tariffs")
async def get_tariffs_endpoint():
    """Открытый эндпоинт для получения актуальной тарифной сетки.
    Используется ботом и фронтендом сайта.
    """
    try:
        tariffs_path = Path(__file__).parent.parent / "tariffs.json"
        with open(tariffs_path, "r", encoding="utf-8") as f:
            tariffs = json.load(f)
        return tariffs
    except Exception as e:
        logger.error(f"❌ Ошибка при чтении тарифов для API: {e}")
        raise HTTPException(status_code=500, detail="Unable to load tariffs")


@router.post("/create-invoice")
async def create_invoice(payload: InvoiceCreate, db: AsyncSession = Depends(get_db)):
    """Создание нового счета (инвойса) в БД для бота или веб-страницы."""
    try:
        tariffs_path = Path(__file__).parent.parent / "tariffs.json"
        with open(tariffs_path, "r", encoding="utf-8") as f:
            tariffs = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка чтения tariffs.json: {e}")
        raise HTTPException(status_code=500, detail="Tariff configuration error")

    tariff_config = tariffs.get(payload.tariff_slug, {})
    amount = float(tariff_config.get("price", 490.00))

    logger.info(f"💰 Создание инвойса: тариф={payload.tariff_slug}, цена={amount}")

    new_attempt = PaymentAttempt(
        email=payload.email,
        tariff_slug=payload.tariff_slug,
        amount=amount,
        status="pending"
    )
    db.add(new_attempt)
    await db.commit()
    await db.refresh(new_attempt)

    if amount == 0.00:
        return {
            "status": "free_tariff",
            "order_id": new_attempt.id,
            "amount": new_attempt.amount,
            "currency": new_attempt.currency,
            "message": "Бесплатный тариф. Оплата не требуется."
        }

    return {
        "status": "success",
        "order_id": new_attempt.id,
        "amount": new_attempt.amount,
        "currency": new_attempt.currency
    }


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


@router.post("/webhook")
async def payment_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Обработка успешного вебхука от абстрактного платежного агрегатора (UlyssesBillingGateway)."""
    try:
        invoice_id = uuid.UUID(payload.order_id) if isinstance(payload.order_id, str) else payload.order_id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    result = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == invoice_id))
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if attempt.status == "success":
        return {"status": "already_processed"}

    if payload.status != "success":
        attempt.status = "failed"
        await db.commit()
        return {"status": "failed_marked"}

    attempt.status = "success"
    attempt.provider_tx_id = payload.provider_tx_id
    attempt.updated_at = datetime.utcnow()

    user = None
    if attempt.user_id:
        user_result = await db.execute(select(User).where(User.id == attempt.user_id))
        user = user_result.scalar_one_or_none()
        logger.info(f"👤 [WEBHOOK] Юзер найден по привязанному user_id: {attempt.user_id}")

    if not user:
        user_result = await db.execute(select(User).where(User.email == attempt.email))
        user = user_result.scalar_one_or_none()

        if not user:
            user = User(email=attempt.email, hiddify_uuid=uuid.uuid4())
            db.add(user)
            await db.flush()
            logger.info(f"👤 [WEBHOOK] Создан новый пользователь сайта {user.email} с ключом {user.hiddify_uuid}")
        else:
            if not user.hiddify_uuid:
                user.hiddify_uuid = uuid.uuid4()
                await db.flush()

        attempt.user_id = user.id

    try:
        tariffs_path = Path(__file__).parent.parent / "tariffs.json"
        with open(tariffs_path, "r", encoding="utf-8") as f:
            tariffs = json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Tariff parse error")

    tariff_config = tariffs.get(attempt.tariff_slug, {})
    days_to_add = int(tariff_config.get("days", 30))

    logger.info(f"📅 Тариф {attempt.tariff_slug}: +{days_to_add} дней")

    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.expires_at.desc()).limit(1)
    )
    last_subscription = sub_result.scalar_one_or_none()

    now = datetime.utcnow()
    starts_at = now
    expires_at = now + timedelta(days=days_to_add)

    if last_subscription and last_subscription.expires_at:
        last_expires_naive = last_subscription.expires_at.replace(tzinfo=None) if last_subscription.expires_at.tzinfo else last_subscription.expires_at
        if last_expires_naive > now:
            starts_at = last_expires_naive
            expires_at = starts_at + timedelta(days=days_to_add)
            logger.info(f"🔄 Продление активной подписки юзера {user.id}. +{days_to_add} дней к {starts_at}")
        else:
            logger.info(f"⏳ Старая подписка юзера {user.id} уже истекла. Активируем новую.")
    else:
        logger.info(f"⏳ Новая активация подписки для юзера {user.id} на {days_to_add} дней.")

    subscription = Subscription(
        user_id=user.id,
        tariff_slug=attempt.tariff_slug,
        status="provisioning",
        starts_at=starts_at,
        expires_at=expires_at
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    logger.info(f"📝 Создана запись подписки {subscription.id} в статусе provisioning")

    background_tasks.add_task(
        provision_and_notify,
        subscription_id=subscription.id,
        to_email=attempt.email,
        hiddify_uuid=str(user.hiddify_uuid)
    )

    return {
        "status": "provisioning",
        "hiddify_uuid": str(user.hiddify_uuid),
        "message": "Оплата подтверждена. Срок подписки обновлен."
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
