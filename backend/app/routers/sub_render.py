# backend/app/routers/sub_render.py (после рефакторинга)

from fastapi import APIRouter, HTTPException
from app.services.subscription_aggregator import aggregate_subscriptions

router = APIRouter()

@router.get("/subscription/{uuid}")
async def get_subscription(uuid: str):
    """Возвращает агрегированную подписку для пользователя."""
    combined_links = await aggregate_subscriptions(uuid)
    if not combined_links:
        raise HTTPException(status_code=404, detail="Subscription not found")

    encoded = encode_subscription(combined_links)
    return encoded
