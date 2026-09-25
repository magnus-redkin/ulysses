# backend/app/routers/subscription.py

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.services.subscription_aggregator import aggregate_subscriptions

from fastapi.responses import FileResponse
from pathlib import Path


logger = logging.getLogger(__name__)
router = APIRouter()




# ---------------------------------------------------------------------------
# RF-подписка (для экспатов, только российская нода)
# ВАЖНО: этот роут должен быть объявлен ДО /subscription/{uuid},
# иначе FastAPI может некорректно матчить URL.
# ---------------------------------------------------------------------------

@router.get("/subscription/{hiddify_uuid}/ru")
async def get_rf_subscription(hiddify_uuid: str):
    """RF-подписка: только российская нода, один протокол."""
    from app.services.rf_node_config import build_rf_outbound

    rf = build_rf_outbound(hiddify_uuid)
    if not rf:
        raise HTTPException(status_code=404, detail="RF node disabled")

    leaf_tag = "VLESS Reality"
    rf["tag"] = leaf_tag

    config = {
        "outbounds": [
            {
                "type": "selector",
                "tag": "proxy",
                "outbounds": ["Auto", leaf_tag],
                "interrupt_exist_connections": True,
            },
            {
                "type": "urltest",
                "tag": "Auto",
                "outbounds": [leaf_tag],
                "url": "https://www.gstatic.com/generate_204",
                "interval": "10m",
                "tolerance": 200,
            },
            {"type": "direct", "tag": "direct"},
            rf,
        ],
        "route": {
            "auto_detect_interface": True,
            "final": "proxy",
            "default_domain_resolver": {"server": "google"},
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
            ],
        },
        "dns": {
            "servers": [
                {"type": "udp", "tag": "google", "server": "8.8.8.8"},
            ],
            "final": "google",
        },
    }

    return JSONResponse(config)


# ---------------------------------------------------------------------------
# Compat-подписка (без xhttp) — генерируется, но в боте не показывается
# ---------------------------------------------------------------------------

@router.get("/subscription/{hiddify_uuid}/compat")
async def get_subscription_compat(hiddify_uuid: str):
    """Compat-подписка: без xhttp. Для Happ, Nekoray, v2rayNG, sing-box CLI."""
    data = await aggregate_subscriptions(hiddify_uuid, mode="compat")
    if not data or "main" not in data:
        raise HTTPException(status_code=404, detail="Subscription not available")
    return JSONResponse(content=data["main"])


# ---------------------------------------------------------------------------
# Основная подписка (full, с xhttp) — для Hiddify
# ---------------------------------------------------------------------------


@router.get("/subscription/{hiddify_uuid}")
async def get_subscription(hiddify_uuid: str):
    """Основная подписка: все протоколы, включая xhttp. Для Hiddify."""
    data = await aggregate_subscriptions(hiddify_uuid, mode="full")
    if not data or "main" not in data:
        raise HTTPException(status_code=404, detail="Subscription not available")
    return JSONResponse(content=data["main"])
