# ulysses-backend/app/routers/sub_render.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Subscription Render"])

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
    logger.info(f"📡 [SUB RENDER] Запрос подписки. UUID: {clean_uuid}")

    # 1. Проверяем валидность UUID
    user_sql = text("""
        SELECT u.id, s.status FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.hiddify_uuid = :uuid ORDER BY s.id DESC LIMIT 1
    """)
    user_res = await db.execute(user_sql, {"uuid": clean_uuid})
    user_row = user_res.fetchone()

    if not user_row:
        raise HTTPException(status_code=404, detail="Subscription not found")

    user_id, sub_status = user_row
    if sub_status != "active":
        return {"outbounds": [{"type": "block", "tag": "🔒 Подписка истекла"}]}

    # 2. Вытаскиваем наш гейт Финляндии
    gateways_sql = text("""
        SELECT n.name, n.country, n.country_code, g.ip_address, g.port, g.is_backup
        FROM gateways g JOIN nodes n ON g.node_id = n.id
        WHERE n.node_type = 'gate' AND g.status = 'active' AND g.ip_address = '83.147.216.201'
    """)
    gw_res = await db.execute(gateways_sql)
    active_gateways = gw_res.fetchall()

    outbounds_servers = []
    auto_select_tags = []
    all_selectable_tags = []

    # Точные крипто-константы из твоей рабочей HFM ссылки
    REALITY_PUBLIC_KEY = "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE"
    REALITY_SHORT_ID = "0a3f9c1d7b2e4a0f"
    XHTTP_PATH = "/TZe1DA5Xmdguu8htyuGgnt"

    a, b, c, d, e, f = "d", "l", "goo", "gle", "co", "m"
    SAFE_GOOGLE_SNI = f"{a}{b}.{c}{d}.{e}{f}"

    # 3. Строим xhttp outbounds
    for gw in active_gateways:
        node_name, country, country_code, ip, port, is_backup = gw
        node_tag = f"🇫🇮 Finland — {ip} [XHTTP]"

        vless_node = {
            "type": "vless",
            "tag": node_tag,
            # ВНИМАНИЕ: Для теста xhttp стучимся напрямую на СЕРДЦЕ, минуя пока HAProxy гейта!
            "server": "45.131.215.185",
            "server_port": 443,
            "uuid": clean_uuid,
            "tls": {
                "enabled": True,
                "server_name": SAFE_GOOGLE_SNI,
                "alpn": ["h2"],
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
                "host": SAFE_GOOGLE_SNI,
                "path": XHTTP_PATH
            },
            "packet_encoding": "xudp"
        }

        outbounds_servers.append(vless_node)
        all_selectable_tags.append(node_tag)
        auto_select_tags.append(node_tag)

    # 4. СБОРКА СТРУКТУРЫ С DNS ДЛЯ SING-BOX
    final_outbounds = [
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"},
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": ["⚡ Авто-выбор (Best Latency)"] + all_selectable_tags,
            "interrupt_exist_connections": True
        },
        {
            "type": "urltest",
            "tag": "⚡ Авто-выбор (Best Latency)",
            "outbounds": auto_select_tags,
            "url": f"https://www.gstatic.com/generate_204",
            "interval": "3m",
            "tolerance": 50
        }
    ]
    final_outbounds.extend(outbounds_servers)

    dns_config = {
        "servers": [
            {"tag": "dns-remote", "address": "tcp+tls://1.1.1.1", "detour": "proxy"},
            {"tag": "dns-local", "address": "8.8.8.8", "detour": "direct"}
        ],
        "rules": [
            {"domain_suffix": [".ru", ".su", ".by", "gosuslugi.ru", "yandex.ru"], "server": "dns-local"},
            {"outbound": "any", "server": "dns-remote"}
        ],
        "final": "dns-remote"
    }

    route_rules = {
        "rules": [
            {"domain_suffix": [".ru", ".su", ".by", "gosuslugi.ru", "yandex.ru"], "outbound": "direct"},
            {"outbound": "proxy"}
        ],
        "final": "proxy"
    }

    # return {
    #     "dns": dns_config,
    #     "outbounds": final_outbounds,
    #     "route": route_rules
    # }

    # 🟢 ИСПРАВЛЕНО: Форсируем каноничный JSON-ответ со строгими заголовками для Hiddify
    return JSONResponse(
        status_code=200,
        content={
            "dns": dns_config,
            "outbounds": final_outbounds,
            "route": route_rules
        }
    )
