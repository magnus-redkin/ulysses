# ulysses-backend/app/routers/sub_render.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Subscription Render"])

# Константы Reality и XHTTP
REALITY_PUBLIC_KEY = "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE"
REALITY_SHORT_ID = "0a3f9c1d7b2e4a0f"
XHTTP_PATH = "/TZe1DA5Xmdguu8htyuGgnt"
DECOY_SITE = getattr(settings, "DECOY_SITE", "dl.google.com")


async def get_active_gateways(db: AsyncSession):
    """Возвращает первый IP для каждого активного гейта."""
    gateways_sql = text("""
        SELECT DISTINCT ON (n.id)
            n.name, n.country, n.country_code, g.ip_address, g.port
        FROM gateways g
        JOIN nodes n ON g.node_id = n.id
        WHERE n.node_type = 'gate' AND g.status = 'active'
        ORDER BY n.id, g.id ASC
    """)
    gw_res = await db.execute(gateways_sql)
    return gw_res.fetchall()


async def generate_singbox_json(uuid: str, db: AsyncSession) -> dict:
    """
    Генерирует готовый JSON для SingBox/Hiddify клиента.
    Используется и роутером API, и CLI (uadmin user json).
    """
    clean_uuid = str(uuid).strip().lower()

    # Проверка пользователя
    user_sql = text("""
        SELECT u.id, s.status FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.hiddify_uuid = :uuid ORDER BY s.id DESC LIMIT 1
    """)
    user_res = await db.execute(user_sql, {"uuid": clean_uuid})
    user_row = user_res.fetchone()

    if not user_row:
        raise ValueError("Subscription not found")

    user_id, sub_status = user_row
    if sub_status != "active":
        return {
            "outbounds": [
                {"type": "block", "tag": "🔒 Подписка истекла"},
                {
                    "type": "selector",
                    "tag": "proxy",
                    "outbounds": ["🔒 Подписка истекла"],
                    "interrupt_exist_connections": True
                },
                {"type": "direct", "tag": "direct"},
                {"type": "block", "tag": "block"},
                {"type": "dns", "tag": "dns-out"}
            ]
        }

    active_gateways = await get_active_gateways(db)

    outbounds_servers = []
    auto_select_tags = []
    all_selectable_tags = []

    for gw in active_gateways:
        node_name, country, country_code, ip, port = gw

        if country_code == "FI":
            country_name = "Finland"
            flag = "🇫🇮"
        elif country_code == "SE":
            country_name = "Sweden"
            flag = "🇸🇪"
        else:
            country_name = "Russia"
            flag = "🇷🇺"

        node_tag = f"{flag} {country_name}"

        vless_node = {
            "type": "vless",
            "tag": node_tag,
            "server": ip,
            "server_port": 443,
            "uuid": clean_uuid,
            "tls": {
                "enabled": True,
                "server_name": DECOY_SITE,
                "utls": {
                    "enabled": True,
                    "fingerprint": "chrome"
                },
                "reality": {
                    "enabled": True,
                    "public_key": REALITY_PUBLIC_KEY,
                    "short_id": REALITY_SHORT_ID
                }
            },
            "transport": {
                "type": "xhttp",
                "mode": "auto",
                "path": XHTTP_PATH
            }
        }

        outbounds_servers.append(vless_node)
        all_selectable_tags.append(node_tag)
        auto_select_tags.append(node_tag)

    final_outbounds = [
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": ["Best Latency"] + all_selectable_tags,
            "interrupt_exist_connections": True
        },
        {
            "type": "urltest",
            "tag": "Best Latency",
            "outbounds": auto_select_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "3m0s",
            "tolerance": 50
        },
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"}
    ]

    final_outbounds.extend(outbounds_servers)

    return {"outbounds": final_outbounds}


@router.get("/X6CbExbUw2/sub/{uuid}/")
@router.get("/X6CbExbUw2/sub/{uuid}")
@router.get("/subscription/{uuid}/")
@router.get("/subscription/{uuid}")
async def render_singbox_subscription(
    uuid: str,
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db)
):
    clean_uuid = str(uuid).strip().lower()
    logger.info(f"📡 [SUB RENDER] Запрос подписки для UUID: {clean_uuid}")

    try:
        result = await generate_singbox_json(clean_uuid, db)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
