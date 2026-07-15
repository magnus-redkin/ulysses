#!/usr/bin/env python3
"""
Ulysses VPN Bot — Тонкий клиент (вся логика в бэкенде)
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

import httpx
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    MenuButtonCommands,
    Message,
    CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Загрузка .env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
WEB_API_URL = os.getenv("WEB_API_URL", "http://127.0.0.1:5173")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден!")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# ============================================================
# КЛАВИАТУРЫ (только отображение, логика в бэкенде)
# ============================================================

def get_subscriptions_keyboard(tariffs: list = None) -> InlineKeyboardMarkup:
    """Клавиатура тарифов (данные приходят из бэкенда)"""
    buttons = []
    if tariffs:
        for t in tariffs:
            buttons.append([InlineKeyboardButton(text=t["name_ru"], callback_data=f"tariff_{t['slug']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


KEYBOARDS = {
    "tariffs": lambda: get_subscriptions_keyboard(),
    "active": lambda: InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Узнать баланс", callback_data="action_check_balance")],
        [InlineKeyboardButton(text="🛒 Купить / Продлить", callback_data="action_buy_tariff")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="action_show_about"),
         InlineKeyboardButton(text="📜 Документы", callback_data="action_show_rules")]
    ]),
    "renew": lambda: InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="action_buy_tariff")],
        [InlineKeyboardButton(text="📊 Мой баланс", callback_data="action_check_balance")],
        [InlineKeyboardButton(text="📜 Документы", callback_data="action_show_rules")]
    ]),
    "back": lambda: InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
    ]),
}


async def api_call(method: str, url: str, **kwargs) -> dict | None:
    """Единый helper для запросов к бэкенду."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "GET":
                resp = await client.get(url, **kwargs)
            else:
                resp = await client.post(url, json=kwargs.get("json"))
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"API {method} {url} → {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"API error: {e}")
    return None


def format_balance_from_state(balance: dict) -> str:
    """Форматирование баланса из данных бэкенда."""
    t = balance.get("traffic", {})
    status = "🟢 Активна" if balance.get("is_active") else "🔴 Приостановлена"
    pct = t.get("percent", 0)
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    return (
        f"📊 *Статус подписки*\n\n{status}\n"
        f"📧 `{balance.get('email', '')}`\n\n"
        f"📈 Трафик:\n`{bar}` {pct:.1f}%\n"
        f"• Использовано: *{t.get('used_gb', 0):.2f} ГБ*\n"
        f"• Осталось: *{t.get('remaining_gb', 0):.2f} ГБ*\n"
        f"• Всего: *{t.get('total_gb', 0):.1f} ГБ*\n\n"
        f"⏳ Дней осталось: *{balance.get('days_left', 0)}*"
    )


# ============================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"📥 /start от {message.from_user.id}")

    # Deep Link
    if " " in message.text:
        uuid_arg = message.text.split(" ", 1)[1].strip()
        resp = await api_call("POST", f"{BACKEND_API_URL}/api/user/link-telegram",
                              json={"uuid": uuid_arg, "tg_user_id": message.from_user.id, "tg_username": message.from_user.username})
        if resp and resp.get("status") == "success":
            await message.answer(resp.get("message", "🎉 Аккаунт привязан!"))
        else:
            await message.answer("⚠️ Не удалось привязать аккаунт.")

    # Получить состояние
    state = await api_call("GET", f"{BACKEND_API_URL}/api/bot/state?tg_user_id={message.from_user.id}")
    if not state:
        await message.answer("⚠️ Сервис временно недоступен.", reply_markup=KEYBOARDS["back"]())
        return

    keyboard = KEYBOARDS.get(state.get("keyboard", "back"), KEYBOARDS["back"])()
    await message.answer(state["message"], reply_markup=keyboard)


@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    loading = await message.answer("⏳ Загрузка...")
    state = await api_call("POST", f"{BACKEND_API_URL}/api/bot/action",
                           json={"tg_user_id": message.from_user.id, "action": "check_balance"})
    if state and state.get("balance"):
        await loading.edit_text(format_balance_from_state(state["balance"]), reply_markup=KEYBOARDS["back"]())
    else:
        await loading.edit_text("⚠️ Ошибка получения баланса.", reply_markup=KEYBOARDS["back"]())


@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    state = await api_call("GET", f"{BACKEND_API_URL}/api/billing/tariffs")
    if state:
        tariffs = [{"slug": k, "name_ru": v["name_ru"]} for k, v in state.items()]
        await message.answer("🛒 Выберите тариф:", reply_markup=get_subscriptions_keyboard(tariffs))
    else:
        await message.answer("⚠️ Сервис временно недоступен.", reply_markup=KEYBOARDS["back"]())


@dp.message(Command("support"))
async def cmd_support(message: Message):
    await message.answer("🆘 Напишите ваш вопрос в ответ на это сообщение.", reply_markup=KEYBOARDS["back"]())


@dp.message(Command("logout"))
async def cmd_logout(message: Message):
    resp = await api_call("POST", f"{BACKEND_API_URL}/api/user/unlink-telegram",
                          json={"tg_user_id": message.from_user.id, "uuid": ""})
    await message.answer("🚪 Вы вышли из аккаунта." if resp else "⚠️ Не удалось выйти.")

    state = await api_call("GET", f"{BACKEND_API_URL}/api/bot/state?tg_user_id={message.from_user.id}")
    keyboard = KEYBOARDS.get(state["keyboard"], KEYBOARDS["back"])() if state else KEYBOARDS["back"]()
    await message.answer(state["message"] if state else "👋 Вы не авторизованы.", reply_markup=keyboard)


# ============================================================
# CALLBACK — все действия через bot/action
# ============================================================

@dp.callback_query(F.data == "back_to_menu")
async def btn_back(callback: CallbackQuery):
    await callback.answer()
    state = await api_call("GET", f"{BACKEND_API_URL}/api/bot/state?tg_user_id={callback.from_user.id}")
    keyboard = KEYBOARDS.get(state["keyboard"], KEYBOARDS["back"])() if state else KEYBOARDS["back"]()
    await callback.message.edit_text(state["message"] if state else "📋 Меню", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("action_"))
async def btn_action(callback: CallbackQuery):
    await callback.answer()
    action = callback.data.replace("action_", "")
    await callback.message.edit_text("⏳ Загрузка...")

    state = await api_call("POST", f"{BACKEND_API_URL}/api/bot/action",
                           json={"tg_user_id": callback.from_user.id, "action": action})

    if not state:
        await callback.message.edit_text("⚠️ Сервис временно недоступен.", reply_markup=KEYBOARDS["back"]())
        return

    keyboard = KEYBOARDS.get(state.get("keyboard", "back"), KEYBOARDS["back"])()

    if state.get("state") == "balance" and state.get("balance"):
        await callback.message.edit_text(format_balance_from_state(state["balance"]), reply_markup=keyboard)
    else:
        await callback.message.edit_text(state.get("message", "OK"), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("tariff_"))
async def btn_tariff(callback: CallbackQuery):
    await callback.answer()
    tariff_slug = callback.data.replace("tariff_", "")

    state = await api_call("POST", f"{BACKEND_API_URL}/api/bot/action",
                           json={
                               "tg_user_id": callback.from_user.id,
                               "action": "buy_tariff",
                               "payload": {
                                   "tariff_slug": tariff_slug,
                                   "tg_username": callback.from_user.username or "unknown"
                               }
                           })

    keyboard = KEYBOARDS.get(state["keyboard"], KEYBOARDS["back"])() if state else KEYBOARDS["back"]()
    await callback.message.edit_text(state["message"] if state else "⚠️ Ошибка.", reply_markup=keyboard)


# ============================================================
# ТИКЕТЫ (отдельный эндпоинт веб-админки)
# ============================================================

@dp.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message):
    logger.info(f"📝 Тикет от {message.from_user.id}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{WEB_API_URL}/api/tickets", json={
                "tg_user_id": message.from_user.id,
                "username": message.from_user.username or "unknown",
                "text": message.text
            })
            if resp.status_code == 200:
                data = resp.json()
                await message.answer(f"✅ Обращение №{data.get('ticket_number', '')} передано в поддержку!",
                                     reply_markup=KEYBOARDS["back"]())
                return
    except Exception as e:
        logger.error(f"❌ Тикет: {e}")
    await message.answer("⚠️ Сервис поддержки временно перегружен.", reply_markup=KEYBOARDS["back"]())


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    try:
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот: @{bot_info.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {e}")
        return

    commands = [
        BotCommand(command="start", description="📱 Главное меню"),
        BotCommand(command="balance", description="📊 Проверить баланс"),
        BotCommand(command="buy", description="🛒 Купить доступ"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="logout", description="🚪 Выйти из аккаунта"),
    ]
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    logger.info("🚀 Бот готов")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
