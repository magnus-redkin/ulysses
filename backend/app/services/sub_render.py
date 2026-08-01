"""
Сервис генерации подписного конфига SingBox / Hiddify.
Чистая бизнес-логика, параметры Reality/XHTTP берутся из переменных окружения.
Используется как в API-роутерах, так и в CLI (при наличии доступа к БД).
"""

import os
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# --- Параметры Reality и XHTTP, конфигурируемые через окружение ---
REALITY_PUBLIC_KEY = os.getenv("REALITY_PUBLIC_KEY")
REALITY_SHORT_ID  = os.getenv("REALITY_SHORT_ID")
XHTTP_PATH        = os.getenv("XHTTP_PATH")
DECOY_SITE        = os.getenv("DECOY_SITE")


_required = {
    "REALITY_PUBLIC_KEY": REALITY_PUBLIC_KEY,
    "REALITY_SHORT_ID": REALITY_SHORT_ID,
    "XHTTP_PATH": XHTTP_PATH,
    "DECOY_SITE": DECOY_SITE,
}

for name, value in _required.items():
    if not value:
        raise RuntimeError(
            f"❌ Обязательная переменная окружения {name} не задана. "
            f"Укажите её в .env или в окружении."
        )

async def get_active_gateways(db: AsyncSession) -> list[dict]:
    """
    Возвращает список активных шлюзов с первым IP для каждого гейта.
    Результат: список словарей с ключами:
        name, country, country_code, ip_address, port
    """
    sql = text("""
        SELECT DISTINCT ON (n.id)
            n.name, n.country, n.country_code, g.ip_address, g.port
        FROM gateways g
        JOIN nodes n ON g.node_id = n.id
        WHERE n.node_type = 'gate' AND g.status = 'active'
        ORDER BY n.id, g.id ASC
    """)
    result = await db.execute(sql)
    rows = result.fetchall()
    return [
        {
            "name": row.name,
            "country": row.country,
            "country_code": row.country_code,
            "ip_address": row.ip_address,
            "port": row.port,
        }
        for row in rows
    ]


async def generate_singbox_json(uuid: str, db: AsyncSession) -> dict:
    """
    Генерирует JSON-конфиг для SingBox/Hiddify клиента на основе UUID пользователя.
    Возвращает словарь с ключом 'outbounds'.
    Выбрасывает ValueError, если подписка не найдена.
    """
    clean_uuid = uuid.strip().lower()

    # 1. Проверка подписки пользователя
    user_sql = text("""
        SELECT u.id, s.status
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.hiddify_uuid = :uuid
        ORDER BY (s.status = 'active') DESC, s.expires_at DESC NULLS LAST, s.id DESC
        LIMIT 1
    """)
    user_result = await db.execute(user_sql, {"uuid": clean_uuid})
    user_row = user_result.fetchone()

    if not user_row:
        raise ValueError("Subscription not found")

    user_id, sub_status = user_row

    # 2. Если подписка неактивна — возвращаем заглушку
    if sub_status != "active":
        return {
            "outbounds": [
                {
                    "type": "selector",
                    "tag": "proxy",
                    "outbounds": ["🛑 ПОДПИСКА ИСТЕКЛА ИЛИ НЕАКТИВНА"],
                    "interrupt_exist_connections": True,
                },
                {
                    "type": "block",
                    "tag": "🛑 ПОДПИСКА ИСТЕКЛА ИЛИ НЕАКТИВНА",
                },
                {"type": "direct", "tag": "direct"},
                {"type": "block", "tag": "block"},
                {"type": "dns", "tag": "dns-out"},
            ]
        }

    # 3. Получаем активные шлюзы
    gateways = await get_active_gateways(db)

    outbounds_servers = []
    auto_select_tags = []      # только зарубежные ноды (не RU)
    all_selectable_tags = []   # все ноды (включая RU)

    for gw in gateways:
        node_name = gw["name"]
        country_code = str(gw["country_code"]).upper().strip()
        ip = gw["ip_address"]
        port = gw["port"]

        # 4. Эмодзи флага
        flag_map = {"FI": "🇫🇮", "SE": "🇸🇪", "RU": "🇷🇺"}
        flag = flag_map.get(country_code, "🌐")

        # 5. Формируем читаемое имя ноды
        display_name = node_name if node_name else f"{country_code}-1"
        node_tag = f"{flag} {display_name}"

        # 6. Конфигурация VLESS Reality XHTTP (параметры из окружения)
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
                    "fingerprint": "chrome",
                },
                "reality": {
                    "enabled": True,
                    "public_key": REALITY_PUBLIC_KEY,
                    "short_id": REALITY_SHORT_ID,
                },
            },
            "transport": {
                "type": "xhttp",
                "mode": "auto",
                "path": XHTTP_PATH,
            },
        }

        outbounds_servers.append(vless_node)
        all_selectable_tags.append(node_tag)

        # 7. Запрещаем российским серверам участвовать в авто-выборе
        if country_code != "RU":
            auto_select_tags.append(node_tag)

    # 8. Если нет серверов — фолбэк
    if not outbounds_servers:
        return {
            "outbounds": [
                {"type": "selector", "tag": "proxy", "outbounds": ["direct"]},
                {"type": "direct", "tag": "direct"},
                {"type": "block", "tag": "block"},
                {"type": "dns", "tag": "dns-out"},
            ]
        }

    # 9. Сборка финального списка outbounds
    final_outbounds = []

    if auto_select_tags:
        final_outbounds.append({
            "type": "selector",
            "tag": "proxy",
            "outbounds": ["🚀 Авто-выбор лучшего сервера"] + all_selectable_tags,
            "interrupt_exist_connections": True,
        })
        final_outbounds.append({
            "type": "urltest",
            "tag": "🚀 Авто-выбор лучшего сервера",
            "outbounds": auto_select_tags,
            "url": "https://gstatic.com",
            "interval": "3m0s",
            "tolerance": 50,
        })
    else:
        final_outbounds.append({
            "type": "selector",
            "tag": "proxy",
            "outbounds": all_selectable_tags,
            "interrupt_exist_connections": True,
        })

    # Системные выходы
    final_outbounds.extend([
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"},
    ])

    # Физические VLESS-серверы
    final_outbounds.extend(outbounds_servers)

    return {"outbounds": final_outbounds}
