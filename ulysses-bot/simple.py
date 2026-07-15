#!/usr/bin/env python3
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Загрузка .env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8925254581:AAFoHImk964rRIk7s6IVVNB52fP9b9TnqE0")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик /start"""
    logger.info(f"✅ START получен от {message.from_user.id}")
    logger.info(f"📝 Текст: {message.text}")

    # Проверяем deep link
    if " " in message.text:
        parts = message.text.split(" ", 1)
        uuid_arg = parts[1].strip()
        logger.info(f"🔗 UUID: {uuid_arg}")
        await message.answer(f"✅ Привязка аккаунта с UUID: {uuid_arg}")
    else:
        await message.answer("👋 Привет! Я бот Ulysses VPN.")

@dp.message()
async def echo(message: types.Message):
    """Эхо для всех остальных сообщений"""
    logger.info(f"📝 Сообщение от {message.from_user.id}: {message.text}")
    await message.answer(f"Вы написали: {message.text}")

async def main():
    # Удаляем вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Бот запущен")
    logger.info(f"🤖 @{ (await bot.get_me()).username }")

    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
