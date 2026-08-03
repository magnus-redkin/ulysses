# bot/main.py

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from bot.config import BOT_TOKEN, logger
from bot.handlers import common, billing

async def set_bot_commands(bot: Bot):
    """Регистрация списка команд в большой синей кнопке 'Меню' на двух языках."""
    # Команды по умолчанию (для английского языка и всех остальных локалей)
    commands_en = [
        BotCommand(command="start", description="Main menu and status"),
        BotCommand(command="lang", description="Change interface language"),
        BotCommand(command="balance", description="Check subscription & traffic balance"),
        BotCommand(command="support", description="Contact tech support")
    ]

    # Команды для русскоязычных пользователей
    commands_ru = [
        BotCommand(command="start", description="Главное меню и статус VPN"),
        BotCommand(command="lang", description="Изменить язык интерфейса"),
        BotCommand(command="balance", description="Проверить баланс трафика"),
        BotCommand(command="support", description="Связаться с техподдержкой")
    ]

    try:
        # Устанавливаем дефолтные английские команды
        await bot.set_my_commands(commands=commands_en, scope=BotCommandScopeAllPrivateChats())

        # Устанавливаем русские команды конкретно для локали 'ru'
        await bot.set_my_commands(commands=commands_ru, scope=BotCommandScopeAllPrivateChats(), language_code="ru")

        logger.info("✅ Bot commands successfully registered in the Telegram Menu button.")
    except Exception as e:
        logger.error(f"❌ Failed to set bot commands: {e}")

async def main():
    logger.info("Starting Ulysses VPN Telegram Bot...")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрация роутеров хэндлеров
    dp.include_router(common.router)
    dp.include_router(billing.router)

    # Автоматически обновляем список команд в синей кнопке при каждом запуске
    await set_bot_commands(bot)

    # Пропуск накопившихся апдейтов и запуск пуллинга
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
