import os
import httpx
import click
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from app.system_info import collect_system_metrics

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

WEB_API_URL = os.getenv("WEB_API_URL", "http://127.0.0.1:5173")


async def send_admin_alert(custom_message: str | None = None) -> bool:
    if custom_message:
        payload = {
            "is_healthy": "🚨" not in custom_message,
            "report_text": custom_message,
            "message": custom_message
        }
    else:
        metrics = await collect_system_metrics()
        # metrics уже содержит: status, disk_free_percent, ram_available_percent,
        # postgres_status, telegram_bot_status, backend_status
        payload = {
            "is_healthy": metrics.get("status") == "ok",
            "report_text": (
                f"💾 Диск: {metrics.get('disk_free_percent')}% | "
                f"🧠 RAM: {metrics.get('ram_available_percent')}% | "
                f"🐘 PG: {metrics.get('postgres_status')} | "
                f"🤖 Бот: {metrics.get('telegram_bot_status')} | "
                f"⚙️ API: {metrics.get('backend_status')}"
            ),
            "message": "Автоматический системный отчет"
        }

    clean_web_url = f"{WEB_API_URL.strip()}/admin/api/system"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            logger.info(f"📡 Отправка уведомления на {clean_web_url}...")
            web_res = await client.post(clean_web_url, json=payload)

            if web_res.status_code == 200:
                logger.info("✅ Уведомление доставлено в веб-админку!")
                return True
            else:
                logger.error(f"❌ Веб-API: HTTP {web_res.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        return False


@click.command()
@click.option('--message', help='Текст кастомного уведомления')
def notify(message):
    """Отправить системный отчет или кастомный текст в админку"""
    asyncio.run(send_admin_alert(message))
