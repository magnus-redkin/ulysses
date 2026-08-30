import logging
from fastapi import APIRouter, HTTPException
from app.services.subscription_aggregator import aggregate_subscriptions, encode_subscription

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/subscription/{uuid}")
async def get_subscription(uuid: str):
    logger.info(f"📨 Получен запрос на подписку для UUID {uuid}")
    combined_links = await aggregate_subscriptions(uuid)
    if not combined_links:
        logger.error(f"❌ Подписка не найдена для UUID {uuid}")
        raise HTTPException(status_code=404, detail="Subscription not found")

    encoded = encode_subscription(combined_links)
    logger.info(f"✅ Возвращаем подписку длиной {len(encoded)}")
    return encoded
