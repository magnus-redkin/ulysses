import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.services.subscription_aggregator import aggregate_subscriptions

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/subscription/{uuid}")
async def get_subscription_both(uuid: str):
    """
    Возвращает оба режима сразу:
        {"simple": {...}, "advanced": {...}}
    Используется ботом и email — чтобы сформировать две ссылки.
    Клиент VPN сюда не ходит.
    """
    config = await aggregate_subscriptions(uuid)
    if not config or (not config.get("simple") and not config.get("advanced")):
        raise HTTPException(status_code=404, detail="Subscription not found")
    return config


@router.get("/subscription/{uuid}/simple")
async def get_subscription_simple(uuid: str):
    """
    Возвращает только simple-конфиг. Для клиента VPN.
    """
    config = await aggregate_subscriptions(uuid)
    simple = (config or {}).get("simple")
    if not simple:
        raise HTTPException(status_code=404, detail="Simple subscription not found")
    return JSONResponse(content=simple)


@router.get("/subscription/{uuid}/advanced")
async def get_subscription_advanced(uuid: str):
    """
    Возвращает только advanced-конфиг. Для клиента VPN.
    """
    config = await aggregate_subscriptions(uuid)
    advanced = (config or {}).get("advanced")
    if not advanced:
        raise HTTPException(status_code=404, detail="Advanced subscription not found")
    return JSONResponse(content=advanced)
