"""
CLI для отправки уведомлений.
Использование:
    uadmin notify --user TG_ID "текст"
    uadmin notify --admin "текст"
    uadmin notify --broadcast "текст"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import click

from app.database import AsyncSessionLocal
from app.services.sender import (
    send_telegram_message,
    send_admin_alert,
    broadcast_to_all,
)


@click.group(name="notify", help="Отправка уведомлений пользователям.")
def notify():
    """Команды отправки сообщений."""
    pass


@notify.command(name="user")
@click.argument("tg_id", type=int)
@click.argument("message", type=str)
def notify_user(tg_id: int, message: str):
    """Отправить сообщение конкретному пользователю."""
    ok = asyncio.run(send_telegram_message(tg_id, message))
    click.echo(f"{'✅' if ok else '❌'} Sent to {tg_id}")


@notify.command(name="admin")
@click.argument("message", type=str)
def notify_admin(message: str):
    """Отправить алерт всем админам."""
    ok = asyncio.run(send_admin_alert(message))
    click.echo(f"{'✅' if ok else '❌'} Admin alert sent")


@notify.command(name="broadcast")
@click.argument("message", type=str)
def notify_broadcast(message: str):
    """Отправить сообщение всем пользователям."""
    async def _run():
        async with AsyncSessionLocal() as session:
            result = await broadcast_to_all(session, message)
            click.echo(f"📊 Broadcast: sent={result['sent']}, failed={result['failed']}, total={result['total']}")

    asyncio.run(_run())


if __name__ == "__main__":
    notify()
