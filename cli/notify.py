"""
CLI для отправки уведомлений.
Использование:
    uv run cli/notify.py --user TG_ID "текст"
    uv run cli/notify.py --admin "текст"
    uv run cli/notify.py --broadcast "текст"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import argparse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services.sender import (
    send_telegram_message,
    send_admin_alert,
    broadcast_to_all,
)


async def main():
    parser = argparse.ArgumentParser(description="Ulysses notification sender")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--user", type=int, help="Telegram user ID")
    group.add_argument("--admin", action="store_true", help="Send to admins")
    group.add_argument("--broadcast", action="store_true", help="Send to all users")
    parser.add_argument("message", type=str, help="Message text")
    args = parser.parse_args()

    if args.user:
        ok = await send_telegram_message(args.user, args.message)
        print(f"{'✅' if ok else '❌'} Sent to {args.user}")

    elif args.admin:
        ok = await send_admin_alert(args.message)
        print(f"{'✅' if ok else '❌'} Admin alert sent")

    elif args.broadcast:
        async with AsyncSessionLocal() as session:
            result = await broadcast_to_all(session, args.message)
            print(f"📊 Broadcast: sent={result['sent']}, failed={result['failed']}, total={result['total']}")


if __name__ == "__main__":
    asyncio.run(main())
