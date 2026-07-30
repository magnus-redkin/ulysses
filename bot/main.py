#!/usr/bin/env python3
"""
Ulysses VPN Bot — Main Application Runtime Bootstrapper
"""
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN, logger
from bot.handlers import common, billing

# Strict default configuration rules to prevent cross-site layout injection faults
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

async def main():
    try:
        bot_info = await bot.get_me()
        logger.info(f"🤖 Клиентский хаб маршрутизации запущен @{bot_info.username}")
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться к серверам Telegram: {e}")
        return

    commands = [
        BotCommand(command="start", description="📱 Главное меню"),
        BotCommand(command="balance", description="📊 Проверить баланс трафика"),
        BotCommand(command="buy", description="🛒 Купить / Продлить доступ"),
        BotCommand(command="support", description="🆘 Написать в техподдержку")
    ]
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    # 🌟 ИСПРАВЛЕНО: Роутер платежей биллинга обязан подключаться ПЕРВЫМ!
    # Тогда общие хэндлеры common не будут перехватывать его callback-сигналы.
    dp.include_router(billing.router)
    dp.include_router(common.router)

    logger.info("🚀 Ulysses Core тонкий клиент запущен и опрашивает updates...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Thin-client polling loops systematically halted.")
    except Exception as fatal_exception:
        print(f"❌ Critical runtime core failure notification event tracking log: {fatal_exception}")
