import logging
from fastapi import APIRouter, HTTPException
from app.services.subscription_aggregator import aggregate_subscriptions

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/subscription/{uuid}")
async def get_subscription(uuid: str):
    config = await aggregate_subscriptions(uuid)
    if not config:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return config
