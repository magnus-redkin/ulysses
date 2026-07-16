# ulysses-backend/app/routers/test_billing.py

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta
import logging

from app.database import get_db
from app.tasks.workers import provision_and_notify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test", tags=["test_billing"])

@router.post("/mock-webhook")
async def mock_payment_webhook(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Отладочный вебхук для имитации ответа от UlyssesBillingGateway.
    Принимает order_id и статус оплаты.
    """
    order_id = payload.get("order_id")
    status = payload.get("status", "success")

    if not order_id:
        raise HTTPException(status_code=400, detail="order_id required")

    logger.info(f"💳 [Mock Billing] Получен вебхук для инвойса {order_id} со статусом {status}")

    # 1. Ищем инвойс в payment_attempts
    result = await db.execute(text("""
        SELECT user_id, tariff_slug, status, email FROM payment_attempts WHERE id = :id LIMIT 1
    """), {"id": order_id})
    invoice = result.fetchone()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    user_id, tariff_slug, current_status, email = invoice

    if current_status == "success":
        return {"status": "already_processed", "message": "Этот инвойс уже был успешно оплачен ранее"}

    # 2. Обновляем статус платежа в нашей БД
    await db.execute(text("""
        UPDATE payment_attempts
        SET status = :status, updated_at = NOW()
        WHERE id = :id
    """), {"status": status, "id": order_id})

    if status == "success":
        # 3. Рассчитываем даты продления подписки
        sub_check = await db.execute(text("""
            SELECT expires_at FROM subscriptions WHERE user_id = :user_id ORDER BY expires_at DESC LIMIT 1
        """), {"user_id": user_id})
        last_sub = sub_check.fetchone()

        days_to_add = 30 if tariff_slug == "premium" else 7

        now = datetime.utcnow()
        starts_at = now
        if last_sub and last_sub[0]:
            last_expires_naive = last_sub[0].replace(tzinfo=None) if last_sub[0].tzinfo else last_sub[0]
            if last_expires_naive > now:
                starts_at = last_expires_naive

        expires_at = starts_at + timedelta(days=days_to_add)

        # 4. Создаем подписку в статусе provisioning
        sub_result = await db.execute(text("""
            INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
            VALUES (:user_id, :tariff_slug, 'provisioning', 'main', :starts_at, :expires_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            "user_id": user_id,
            "tariff_slug": tariff_slug,
            "starts_at": starts_at,
            "expires_at": expires_at
        })
        subscription_id = sub_result.fetchone()[0]
        await db.commit()

        logger.info(f"🔄 Инвойс одобрен. Запускаем фоновый провижн для подписки {subscription_id}")

        # 5. Передаем задачу в ProvisioningManager через фоновые задачи FastAPI
        user_res = await db.execute(text("SELECT hiddify_uuid FROM users WHERE id = :id"), {"id": user_id})
        hiddify_uuid = user_res.scalar_one()

        background_tasks.add_task(
            provision_and_notify,
            subscription_id=subscription_id,
            to_email=email if email else f"tg_bot_{user_id}@ulysses.internal",
            hiddify_uuid=str(hiddify_uuid)
        )

        return {"status": "success", "message": "Платеж проведен, запущен провижн в Hiddify", "subscription_id": subscription_id}

    await db.commit()
    return {"status": "failed", "message": "Платеж отклонен провайдером"}
