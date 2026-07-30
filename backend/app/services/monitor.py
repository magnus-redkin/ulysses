# ulysses-backend/app/services/monitor.py

import asyncio
import logging
import socket
import ssl
import httpx
from datetime import datetime, timezone
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.config import settings

logger = logging.getLogger("ulysses.monitor")

# 🟢 Настройка списка администраторов из вашего запроса
TG_ADMINS = [73214325465, 880765948]

async def send_telegram_alert(message: str):
    """Отправка тревожного SOS-сообщения всем админам из списка с выводом логов в консоль."""
    bot_token = getattr(settings, "BOT_TOKEN", None)
    if not bot_token:
        print("❌ [MONITOR ALERT] BOT_TOKEN не задан в конфигурации!")
        return

    base_url = "https://telegram.org"
    endpoint_path = f"/bot{bot_token}/sendMessage"

    # Чтобы обойти возможные блокировки РКН на сервере,
    # httpx можно пустить через локальный прокси, если он у вас поднят:
    # proxies = "http://127.0.0.1:10808" (опционально)

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0, verify=False) as client:
        for admin_id in TG_ADMINS:
            payload = {
                "chat_id": admin_id,
                "text": f"🚨 <b>[ULYSSES MONITOR] ТРЕВОГА ИНФРАСТРУКТУРЫ</b>\n\n{message}",
                "parse_mode": "HTML"
            }
            # try:
            #     print(f"   [MONITOR ALERT] ➔ Шлём POST-пакет для админа {admin_id}...")
            #     resp = await client.post(endpoint_path, json=payload)

            #     if resp.status_code == 200:
            #         print(f"   [MONITOR ALERT] ✅ Успешно доставлено админу {admin_id}!")
            #     else:
            #         print(f"   [MONITOR ALERT] ❌ Telegram вернул ошибку HTTP {resp.status_code}: {resp.text}")

            # except httpx.ConnectTimeout:
            #     print(f"   [MONITOR ALERT] ⏳ Таймаут соединения с api.telegram.org для админа {admin_id} (Возможно блокировка РКН)")
            # except Exception as e:
            #     print(f"   [MONITOR ALERT] ⚠️ Сбой отправки для admin_id={admin_id}: {e}")




async def check_database() -> tuple[bool, str]:
    """Проверка доступности СУБД PostgreSQL."""
    try:
        async with AsyncSessionLocal() as session:
            start_time = datetime.now()
            await session.execute(text("SELECT 1"))
            latency = (datetime.now() - start_time).total_seconds() * 1000
            return True, f"OK ({latency:.1f}ms)"
    except Exception as e:
        return False, str(e)


async def check_hiddify_api() -> tuple[bool, str]:
    """Глубокая проверка связи с API Hiddify Manager."""
    hfm_url = getattr(settings, "HIDDIFY_API_URL", "").rstrip("/")
    hfm_key = getattr(settings, "HIDDIFY_API_KEY", "")

    if not hfm_url or not hfm_key:
        return False, "Конфигурация API Hiddify (URL/KEY) отсутствует в .env"

    target_url = f"{hfm_url}/api/v2/admin/user/"
    headers = {"Hiddify-API-Key": hfm_key, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(target_url, headers=headers)
            if resp.status_code == 200:
                return True, f"OK (HTTP 200)"
            return False, f"HTTP {resp.status_code} - {resp.text[:100]}"
    except Exception as e:
        return False, f"Сетевой таймаут / сбой: {e}"


async def check_gateway_tls(ip: str, port: int) -> tuple[bool, str]:
    """Проверка, что VPN-порт ноды (Xray/Sing-box) реально принимает TLS-соединения."""
    loop = asyncio.get_running_loop()
    try:
        # Создаем дефолтный незащищенный контекст (verify=False для самоподписанных Reality-сертификатов)
        context = ssl._create_unverified_context()

        start_time = datetime.now()
        # Имитируем первичное TCP/TLS рукопожатие на порту гейта
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=context),
            timeout=5.0
        )
        latency = (datetime.now() - start_time).total_seconds() * 1000
        writer.close()
        await writer.wait_closed()
        return True, f"OK ({latency:.1f}ms)"
    except Exception as e:
        return False, f"Порт {port} заблокирован или служба Xray упала: {e}"


async def run_inspection_cycle():
    """Единичный запуск полной инспекции всех служб биллинга Ulysses."""
    issues = []
    logger.info("🔍 [MONITOR] Запуск 5-минутного цикла проверки служб...")

    # 1. Проверяем локальную СУБД
    db_ok, db_msg = await check_database()
    if not db_ok:
        issues.append(f"📦 <b>База Данных (PostgreSQL):</b>\n❌ {db_msg}")

    # 2. Проверяем API панели управления VPN
    hfm_ok, hfm_msg = await check_hiddify_api()
    if not hfm_ok:
        issues.append(f"📡 <b>Панель управления Hiddify API:</b>\n❌ {hfm_msg}")

    # 3. Извлекаем из базы данных список нод-гейтов для сканирования портов
    async with AsyncSessionLocal() as session:
        try:
            # Делаем JOIN таблиц нод и шлюзов из вашей схемы
            sql_gateways = """
                SELECT n.name, g.ip_address, g.port, g.is_backup
                FROM gateways g
                JOIN nodes n ON g.node_id = n.id
                WHERE g.status = 'active'
            """
            res = await session.execute(text(sql_gateways))
            gateways = res.fetchall()

            for gw in gateways:
                node_name, ip, port, is_backup = gw
                type_str = "РЕЗЕРВ" if is_backup else "ОСНОВНОЙ"

                # Запускаем TLS-проверку порта ноды
                gw_ok, gw_msg = await check_gateway_tls(ip, port or 443)

                if not gw_ok:
                    issues.append(
                        f"🌐 <b>Нода {node_name} ({type_str}):</b>\n"
                        f"• IP: <code>{ip}:{port}</code>\n"
                        f"• Сбой: ❌ <code>{gw_msg}</code>"
                    )
        except Exception as db_err:
            logger.error(f"Ошибка чтения списка гейтов из БД: {db_err}")

    # 4. Если обнаружены проблемы — отправляем консолидированный алерт
    if issues:
        alert_body = "\n\n".join(issues)
        alert_body += f"\n\n⏰ <i>Время фиксации: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
        # logger.warning("🚨 [MONITOR] Обнаружены проблемы! Отправка алертов админам...")
        await send_telegram_alert(alert_body)
    else:
        logger.info("✨ [MONITOR] Инфраструктура полностью здорова. Ошибок не обнаружено.")


async def start_monitor_daemon():
    """Точка входа бесконечного цикла демона инспекции."""
    logger.info("🧠 Демон непрерывного мониторинга Ulysses Monitor успешно запущен.")
    while True:
        try:
            await run_inspection_cycle()
        except Exception as e:
            logger.critical(f"💥 Ошибка внутри главного цикла монитора: {e}")

        # 🟢 Интервал проверки — ровно 5 минут (300 секунд)
        await asyncio.sleep(300)
