# ulysses-backend/app/routers/sub_render.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Subscription Render"])

# Константы Reality и XHTTP
REALITY_PUBLIC_KEY = "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE"
REALITY_SHORT_ID = "0a3f9c1d7b2e4a0f"
XHTTP_PATH = "/TZe1DA5Xmdguu8htyuGgnt"
DECOY_SITE = getattr(settings, "DECOY_SITE", "://google.com")


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
    Разделяет автоматический выбор (только зарубеж) и ручной выбор (все ноды).
    """
    clean_uuid = str(uuid).strip().lower()

    # Проверка статуса подписки пользователя
    user_sql = text("""
        SELECT u.id, s.status
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.hiddify_uuid = :uuid
        ORDER BY (s.status = 'active') DESC, s.expires_at DESC NULLS LAST, s.id DESC
        LIMIT 1
    """)
    user_res = await db.execute(user_sql, {"uuid": clean_uuid})
    user_row = user_res.fetchone()

    if not user_row:
        raise ValueError("Subscription not found")

    user_id, sub_status = user_row

    # Заглушка, если подписка неактивна (безопасна для Hiddify Next)
    if sub_status != "active":
        return {
            "outbounds": [
                {
                    "type": "selector",
                    "tag": "proxy",
                    "outbounds": ["🛑 ПОДПИСКА ИСТЕКЛА ИЛИ НЕАКТИВНА"],
                    "interrupt_exist_connections": True
                },
                {
                    "type": "block",
                    "tag": "🛑 ПОДПИСКА ИСТЕКЛА ИЛИ НЕАКТИВНА"
                },
                {"type": "direct", "tag": "direct"},
                {"type": "block", "tag": "block"},
                {"type": "dns", "tag": "dns-out"}
            ]
        }

    active_gateways = await get_active_gateways(db)

    outbounds_servers = []
    auto_select_tags = []  # Только зарубежные ноды для urltest
    all_selectable_tags = []  # Абсолютно все ноды для ручного селектора

    for gw in active_gateways:
        node_name, country, country_code, ip, port = gw
        clean_country_code = str(country_code).upper().strip()

        # 1. Присваиваем эмодзи флага на основе кода страны
        if clean_country_code == "FI":
            flag = "🇫🇮"
        elif clean_country_code == "SE":
            flag = "🇸🇪"
        elif clean_country_code == "RU":
            flag = "🇷🇺"
        else:
            flag = "🌐"

        # 2. ИСПРАВЛЕНО: Рендерим красивое имя ноды (Fi-1, Ws-1/Se-1) вместо названия страны
        # Если в базе данных n.name заполнен красиво (например, Fi-1), берем его, иначе генерируем фолбэк
        # display_name = node_name if node_name else f"{clean_country_code}-1"
        display_name = f"{clean_country_code}-1"
        node_tag = f"{flag} {display_name}"

        vless_node = {
            "type": "vless",
            "tag": node_tag,
            "server": ip,
            "server_port": int(port) if port else 443,
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
        all_selectable_tags.append(node_tag) # Все ноды идут в ручной выбор (включая RU)

        # 🌟 ИСПРАВЛЕНО: Запрещаем российским гейтам участвовать в автоматическом urltest тесте скорости!
        if clean_country_code != "RU":
            auto_select_tags.append(node_tag)

    # Защитный фолбэк, если в базе данных временно нет активных серверов
    if not outbounds_servers:
        return {
            "outbounds": [
                {"type": "selector", "tag": "proxy", "outbounds": ["direct"]},
                {"type": "direct", "tag": "direct"},
                {"type": "block", "tag": "block"},
                {"type": "dns", "tag": "dns-out"}
            ]
        }

    # 3. Собираем итоговую конфигурацию outbounds
    final_outbounds = []

    # Определяем, есть ли у нас зарубежные сервера для автовыбора
    if auto_select_tags:
        # Селектор верхнего уровня содержит Автовыбор + список всех ручных серверов
        final_outbounds.append({
            "type": "selector",
            "tag": "proxy",
            "outbounds": ["🚀 Авто-выбор лучшего сервера"] + all_selectable_tags,
            "interrupt_exist_connections": True
        })
        # Сам балансировщик urltest опрашивает ТОЛЬКО зарубежные ноды (без RU)
        final_outbounds.append({
            "type": "urltest",
            "tag": "🚀 Авто-выбор лучшего сервера",
            "outbounds": auto_select_tags,
            "url": "https://gstatic.com",
            "interval": "3m0s",
            "tolerance": 50
        })
    else:
        # Если зарубежных серверов вдруг нет, а есть только RU, убираем автовыбор, чтобы не падал Sing-Box
        final_outbounds.append({
            "type": "selector",
            "tag": "proxy",
            "outbounds": all_selectable_tags,
            "interrupt_exist_connections": True
        })

    # Добавляем стандартные системные выходы
    final_outbounds.extend([
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"}
    ])

    # Дописываем физические серверы VLESS
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
