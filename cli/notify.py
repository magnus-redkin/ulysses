#!/usr/bin/env python3
"""
Отправка алертов администраторам в Telegram.
Использование:
  uadmin notify --message "Сервер G-1 недоступен"
  uadmin notify --test
"""

import os
import asyncio
import logging
from pathlib import Path
import click
from dotenv import load_dotenv
import httpx

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TG_ADMIN = os.getenv("TG_ADMIN", "")


async def send_telegram_message(tg_id: int, text: str) -> bool:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": tg_id, "text": text, "parse_mode": "HTML"}
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False


async def send_admin_alert(message: str) -> dict:
    if not TG_ADMIN:
        return {"status": "error", "message": "TG_ADMIN не задан в .env"}

    admin_ids = [int(x.strip()) for x in TG_ADMIN.split(",") if x.strip()]
    results = {}

    for admin_id in admin_ids:
        text = f"🚨 <b>Ulysses VPN Alert</b>\n\n{message}\n\n<code>tg://{admin_id}</code>"
        ok = await send_telegram_message(tg_id=admin_id, text=text)
        results[str(admin_id)] = "OK" if ok else "FAIL"

    return {"status": "ok", "results": results}


@click.command()
@click.option("--message", "-m", help="Текст алерта")
@click.option("--test", is_flag=True, help="Отправить тестовый алерт")
def notify(message, test):
    if test:
        message = "Тестовый алерт. Система мониторинга работает."
    if not message:
        click.echo("Укажи --message или --test")
        return

    async def _run():
        result = await send_admin_alert(message)
        if result["status"] == "ok":
            for admin_id, status in result["results"].items():
                click.echo(f"  Admin {admin_id}: {status}")
        else:
            click.echo(f"{result['message']}")

    asyncio.run(_run())
