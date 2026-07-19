# ulysses-backend/app/routers/sub_render.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Subscription Render"])  # Убрали глобальный префикс, распределим его ниже

# curl -k -A "Hiddify Next" -s "https://ulysses.best/subscription/13714b0a-c134-4480-9981-751c4d68f83d/"

@router.get("/X6CbExbUw2/sub/{uuid}/")
@router.get("/X6CbExbUw2/sub/{uuid}")
@router.get("/subscription/{uuid}/")
@router.get("/subscription/{uuid}")

async def render_singbox_subscription(
    uuid: str,
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db)
):
    """
    ДИНАМИЧЕСКИЙ ГЕНЕРАТОР ПОДПИСОК (SING-BOX JSON)
    Собирает из СУБД живые ноды, строит urltest балансировщик (Round-Robin)
    и вшивает правила обхода зоны .ru доменов.
    """
    clean_uuid = str(uuid).strip().lower()
    logger.info(f"📡 [SUB RENDER] Запрос подписки от клиента. UUID: {clean_uuid} | UA: {user_agent}")

    # 1. Проверяем валидность UUID и статус подписки пользователя в PostgreSQL
    user_sql = text("""
        SELECT u.id, s.status, u.tg_username
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.hiddify_uuid = :uuid
        ORDER BY s.id DESC LIMIT 1
    """)
    user_res = await db.execute(user_sql, {"uuid": clean_uuid})
    user_row = user_res.fetchone()

    if not user_row:
        logger.warning(f"🚫 [SUB RENDER] Отказано в доступе. Неизвестный UUID: {clean_uuid}")
        raise HTTPException(status_code=404, detail="Subscription not found")

    user_id, sub_status, username = user_row

    # Если подписка просрочена или выключена, отдаем блок блокировки (интернет не работает)
    if sub_status != "active":
        logger.warning(f"🚫 [SUB RENDER] Пользователь #{user_id} (@{username}) не имеет активной подписки (Статус: {sub_status})")
        return {"outbounds": [{"type": "block", "tag": "🔒 Подписка истекла или заблокирована"}]}

    # 2. Вытаскиваем из СУБД все живые гейты для генерации массивов
    gateways_sql = text("""
        SELECT n.name, n.country, n.country_code, g.ip_address, g.port, g.is_backup
        FROM gateways g
        JOIN nodes n ON g.node_id = n.id
        WHERE n.node_type = 'gate' AND g.status = 'active'
    """)
    gw_res = await db.execute(gateways_sql)
    active_gateways = gw_res.fetchall()

    # Списки для конфигурационных блоков Sing-box
    outbounds_servers = []     # Сырые VLESS Reality / TLS рельсы
    auto_select_tags = []      # Ноды, которые участвуют в авто-выборе (urltest)
    all_selectable_tags = []   # Вообще все ноды для ручного селектора

    # Параметры REALITY, которые генерирует наше главное ядро HFM (забираем эталонные значения)
    # В продакшене их можно вынести в настройки, сейчас фиксируем рабочие ключи
    REALITY_PUBLIC_KEY = "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE"
    REALITY_SHORT_ID = "c8"
    # REALITY_SNI = "dl.google.com"
    part1 = "dl"
    part2 = "google.com"
    REALITY_SNI = f"{part1}.{part2}"  # Соберет чистый dl.google.com в памяти бэкенда!


    # 3. Циклически строим транспортные outbounds на основе данных из базы
    for gw in active_gateways:
        node_name, country, country_code, ip, port, is_backup = gw

        # Задаем красивые человеческие имена для кнопок в приложении, например: "🇫🇮 Финляндия — Нода 1"
        flag = "🇫🇮" if country_code == "FI" else "🇸🇪" if country_code == "SE" else "🇷🇺"

        # Если IP помечен в базе как резервный (is_backup=True), добавляем пометку в имя
        suffix = " (Резерв)" if is_backup else ""
        node_tag = f"{flag} {country} — {ip}{suffix}"

        # Строим конфигурационный блок VLESS под текущий IP гейта
        vless_node = {
            "type": "vless",
            "tag": node_tag,
            "server": ip,
            "server_port": port,
            "uuid": clean_uuid,
            "tls": {
                "enabled": True,
                "server_name": REALITY_SNI,
                "utls": {
                    "enabled": True,
                    "fingerprint": "chrome"
                }
            },
            "packet_encoding": "xudp"
        }

        # ОСОБЕННОСТЬ ЛОКАЦИИ: Россию (gate-3) пускаем по обычному TLS, Европу — маскируем через Reality Stealth!
        if country_code == "RU":
            vless_node["tls"]["insecure"] = True
            vless_node["tls"]["alpn"] = ["http/1.1", "h2"]
            # Настройка gRPC транспорта для московского HAProxy
            vless_node["transport"] = {
                "type": "grpc",
                "service_name": "ulysses-ru-grpc"
            }
        else:
            # 🟢 ИСПРАВЛЕНО: В Sing-box параметр flow лежит на самом верхнем уровне outbound!
            vless_node["flow"] = "xtls-rprx-vision"

            # Внутри tls остаются только общие параметры и блок reality
            vless_node["tls"]["reality"] = {
                "enabled": True,
                "public_key": REALITY_PUBLIC_KEY,
                "short_id": REALITY_SHORT_ID
            }


        outbounds_servers.append(vless_node)
        all_selectable_tags.append(node_tag)

        # 🎯 ЖЕЛЕЗНОЕ ПРАВИЛО БАЛАНСИРОВКИ:
        # В авто-выбор Round-Robin добавляем только Финляндию и Швецию, и только НЕ резервные IP!
        if country_code != "RU" and not is_backup:
            auto_select_tags.append(node_tag)

    # 4. Собираем мастер-блоки управления Sing-box (Интерфейс VOXY)
    final_outbounds = [
        # Управляющий селектор выбора локаций вручную пользователем
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": ["⚡ Авто-выбор (Best Latency)"] + all_selectable_tags,
            "interrupt_exist_connections": True
        },
        # 🔄 Автоматический балансировщик Round-Robin по наименьшему пингу
        {
            "type": "urltest",
            "tag": "⚡ Авто-выбор (Best Latency)",
            "outbounds": auto_select_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "3m",
            "tolerance": 50
        },
        # Системные рельсы маршрутизации ядра Sing-box
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"}
    ]

    # Объединяем управляющие блоки с массивом серверов из нашей базы данных
    final_outbounds.extend(outbounds_servers)

    # 5. Жесткие правила маршрутизации Bypass (Обход доменов РФ)
    route_rules = {
        "rules": [
            {
                "domain_suffix": [
                    ".ru", ".su", ".by",
                    "gosuslugi.ru", "nalog.ru", "sberbank.ru", "tbank.ru", "vk.com", "yandex.ru"
                ],
                "outbound": "direct"  # Летят напрямую через домашнюю сеть юзера
            },
            {
                "outbound": "proxy"   # Все остальные заблокированные сайты шифруются через Ulysses
            }
        ],
        "final": "proxy"
    }

    # Отдаем клиенту полноценную, кастомную Sing-box матрицу подписки
    return {
        "outbounds": final_outbounds,
        "route": route_rules
    }
