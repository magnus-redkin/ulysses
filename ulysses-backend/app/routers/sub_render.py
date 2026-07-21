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

    # 1. Проверяем валидность UUID и статус подписки пользователя в СУБД биллинга
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
        return JSONResponse(status_code=200, content={"outbounds": [{"type": "block", "tag": "🔒 Подписка истекла"}]})

    # 2. Вытаскиваем из СУБД все активные гейты (Финляндия, Швеция, Россия)
    gateways_sql = text("""
        SELECT n.name, n.country, n.country_code, g.ip_address, g.port, g.is_backup
        FROM gateways g
        JOIN nodes n ON g.node_id = n.id
        WHERE n.node_type = 'gate' AND g.status = 'active'
        ORDER BY g.id ASC
    """)
    gw_res = await db.execute(gateways_sql)
    active_gateways = gw_res.fetchall()

    outbounds_servers = []     # Массив VLESS нод
    auto_select_tags = []      # Ноды для балансировщика Best Latency
    all_selectable_tags = []   # Полный список для селектора proxy

    # Точные криптографические константы Reality и XHTTP
    REALITY_PUBLIC_KEY = "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE"
    REALITY_SHORT_ID = "0a3f9c1d7b2e4a0f"
    XHTTP_PATH = "/TZe1DA5Xmdguu8htyuGgnt"

    # Динамический домен маскировки из настроек .env
    decoy_site = settings.DECOY_SITE if hasattr(settings, "DECOY_SITE") else "dl.google.com"

    # 3. Динамически собираем ноды гейтов на основе данных из базы
    for gw in active_gateways:
        node_name, country, country_code, ip, port, is_backup = gw

        # Задаем понятные имена тегов, как в эталонном JSON
        country_name = "Finland" if country_code == "FI" else "Sweden" if country_code == "SE" else "Russia"
        flag = "🇫🇮" if country_code == "FI" else "🇸🇪" if country_code == "SE" else "🇷🇺"

        node_tag = f"{flag} {country_name} — {ip}"

        vless_node = {
            "type": "vless",
            "tag": node_tag,
            "server": ip,
            "server_port": 443,
            "uuid": clean_uuid,
            "tls": {
                "enabled": True,
                "server_name": decoy_site,
                "alpn": "http/1.1",  # Чистая строка строго по работающему стандарту
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
                "host": decoy_site,
                "path": XHTTP_PATH
            },
            "packet_encoding": "xudp"
        }

        outbounds_servers.append(vless_node)
        all_selectable_tags.append(node_tag)
        auto_select_tags.append(node_tag)

    # 4. СБОРКА ИСТИННОЙ СТРУКТУРЫ (Порядок блоков строго соответствует вашему образцу)
    final_outbounds = [
        # 1. Управляющий селектор proxy
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": ["Best Latency"] + all_selectable_tags,
            "interrupt_exist_connections": True
        },
        # 2. Балансировщик пинга Best Latency
        {
            "type": "urltest",
            "tag": "Best Latency",
            "outbounds": auto_select_tags,
            "url": "https://www.gstatic." + "com" + "/generate_204",
            "interval": "3m0s",
            "tolerance": 50
        },
        # 3. Служебные интерфейсы по умолчанию
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"}
    ]

    # Дописываем готовые VLESS сервера в конец массива outbounds
    final_outbounds.extend(outbounds_servers)

    # Инфраструктурная DNS матрица
    dns_config = {
        "servers": [
            {"tag": "dns-remote", "address": "tcp+tls://1.1.1.1", "detour": "proxy"},
            {"tag": "dns-local", "address": "8.8.8.8", "detour": "direct"}
        ],
        "rules": [
            {"domain_suffix": [".ru", ".su", ".by", "gosuslugi.ru", "yandex.ru", "vk.com"], "server": "dns-local"},
            {"outbound": "any", "server": "dns-remote"}
        ],
        "final": "dns-remote"
    }

    # Сплит-маршрутизация трафика
    route_rules = {
        "rules": [
            {
                "domain_suffix": [
                    ".ru", ".su", ".by",
                    "gosuslugi.ru", "nalog.ru", "sberbank.ru", "tbank.ru", "vk.com", "yandex.ru"
                ],
                "outbound": "direct"
            },
            {
                "outbound": "proxy"
            }
        ],
        "final": "proxy"
    }

    return JSONResponse(
        status_code=200,
        content={
            "dns": dns_config,
            "outbounds": final_outbounds,
            "route": route_rules
        }
    )
