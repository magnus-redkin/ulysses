# bot/handlers/common.py

import httpx
import html

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.config import BACKEND_API_URL, WEB_API_URL, HOST_API_KEY, logger
from bot.keyboards import KEYBOARDS
from bot.utils import api_call, get_user_lang, set_user_lang

from bot.localization import LOCALIZATION

router = Router()

# ============================================================
# СЛОВАРЬ ЛОКАЛИЗАЦИИ И СЕРВИСНЫЙ СЛОЙ
# ============================================================

def format_balance_from_state(balance: dict, lang: str = "ru") -> str:
    """Форматирование метрик трафика из бэкенда в чистый HTML для Telegram с поддержкой локализации."""
    loc = LOCALIZATION[lang]
    t = balance.get("traffic", {})
    status = loc["status_active"] if balance.get("is_active") else loc["status_paused"]
    pct = t.get("percent", 0)
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))

    # Забираем чистый UUID из ответа сервера
    user_uuid = str(balance.get("hiddify_uuid", "UNKNOWN_UUID")).strip()

    # Безопасная сборка строк БЕЗ использования f-строк
    # Это гарантирует, что пути /account/ и параметры не исказятся
    sub_url = "https://ulysses.best/subscription/" + user_uuid + "#Ulysses"
    acc_url = "https://ulysses.best/account/" + user_uuid
    bot_url = "https://t.me/ulysses_vpn_bot?start=" + user_uuid

    if lang == "en":
        links_header = (
            "🔗 <b>Subscription link:</b>\n"
            "<code>" + sub_url + "</code>\n\n"
            "📊 <b>Personal Account:</b>\n"
            + acc_url + "\n\n"
            "🤖 <b>Telegram Support:</b>\n"
            + bot_url + "\n\n"
            "───────────────────\n\n"
        )
    else:
        links_header = (
            "🔗 <b>Ссылка для подключения:</b>\n"
            "<code>" + sub_url + "</code>\n\n"
            "📊 <b>Личный кабинет:</b>\n"
            + acc_url + "\n\n"
            "🤖 <b>Поддержка в Telegram:</b>\n"
            + bot_url + "\n\n"
            "───────────────────\n\n"
        )

    return (
        links_header +
        f"{loc['status_title']}"
        f"{loc['status_lbl']}: {status}\n"
        f"{loc['profile_lbl']}: <code>{balance.get('email', '')}</code>\n\n"
        f"{loc['traffic_lbl']}<code>{bar}</code> {pct:.1f}%\n"
        f"• {loc['used_lbl']}: <b>{t.get('used_gb', 0):.2f} GB</b>\n"
        f"• {loc['rem_lbl']}: <b>{t.get('remaining_gb', 0):.2f} GB</b>\n"
        f"• {loc['total_lbl']}: <b>{t.get('total_gb', 0):.1f} GB</b>\n\n"
        f"{loc['days_lbl']}: <b>{balance.get('days_left', 0)} {loc['days_unit']}</b>"
    )



# ============================================================
# ХЭНДЛЕРЫ КОМАНД И CALLBACK-ЗАПРОСОВ
# ============================================================

from aiogram.filters import Command, CommandObject # <-- Убедитесь, что CommandObject импортирован

@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    lang = await get_user_lang(message)
    tg_user_id = message.from_user.id
    tg_username = message.from_user.username or "unknown"

    # Получаем UUID из ссылки (если он передан)
    uuid_argument = command.args

    if uuid_argument:
        uuid_argument = uuid_argument.strip()
        logger.info(f"📥 [DEEP LINK] User {tg_user_id} started bot with UUID: {uuid_argument}")

        # Отправляем на бэкенд запрос связывания аккаунта
        # Мы передаем и tg_user_id, и hiddify_uuid, чтобы бэкенд объединил записи
        await api_call(
            "POST",
            f"{BACKEND_API_URL}/api/bot/register", # ВНИМАНИЕ: уберите пробелы вокруг слэшей
            api_key=HOST_API_KEY,
            json={
                "tg_user_id": tg_user_id,
                "tg_username": tg_username,
                "hiddify_uuid": uuid_argument # Передаем UUID для связывания в БД
            }
        )
    else:
        logger.info(f"📥 [MENU START] Standard/start for user {tg_user_id}")
        await api_call(
            "POST",
            f"{BACKEND_API_URL}/api/bot/register", # ВНИМАНИЕ: уберите пробелы вокруг слэшей
            api_key=HOST_API_KEY,
            json={"tg_user_id": tg_user_id, "tg_username": tg_username}
        )

    safe_name = html.escape(message.from_user.first_name or "User")
    welcome_text = LOCALIZATION[lang]["welcome"].format(name=safe_name)
    await message.answer(text=welcome_text, reply_markup=KEYBOARDS["menu"](lang=lang), parse_mode="HTML")



@router.message(Command("lang"))
async def cmd_lang(message: Message):
    lang = await get_user_lang(message)
    # ИСПРАВЛЕНО: Теперь вызывается точечная клавиатура выбора языка lang_screen
    await message.answer(
        text=LOCALIZATION[lang]["choose_lang_title"],
        reply_markup=KEYBOARDS["lang_screen"](lang=lang),
        parse_mode="HTML"
    )

@router.message(Command("info"))
@router.callback_query(F.data == "check_balance")
async def show_user_balance(event):
    """Выводит или обновляет актуальный баланс трафика и статус подписки пользователя."""
    lang = await get_user_lang(event)
    is_callback = isinstance(event, CallbackQuery)
    message_obj = event.message if is_callback else event
    tg_user_id = event.from_user.id

    target_url = f"{BACKEND_API_URL}/api/user/balance?tg_user_id={tg_user_id}"
    raw_balance = await api_call("GET", target_url, api_key=HOST_API_KEY)

    if not raw_balance:
        await message_obj.answer("❌ Не удалось получить данные. Попробуйте позже.")
        return

    if raw_balance:
        print(f"DEBUG BALANCE DATA: {raw_balance}") # <-- Добавьте эту строчку для проверки полей


    balance_text = format_balance_from_state(raw_balance, lang=lang)

    if is_callback:
        try:
            await message_obj.edit_text(text=balance_text, reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")
        except Exception:
            await event.answer()
        await event.answer()
    else:
        await message_obj.answer(text=balance_text, reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")




@router.callback_query(F.data.startswith("set_lang:"))
async def process_language_switch(callback_query: CallbackQuery):
    new_lang = callback_query.data.split(":")[1]
    await set_user_lang(callback_query.from_user.id, new_lang)

    await callback_query.answer(LOCALIZATION[new_lang]["lang_changed"])

    welcome_text = LOCALIZATION[new_lang]["welcome"].format(name=callback_query.from_user.first_name)
    await callback_query.message.edit_text(text=welcome_text, reply_markup=KEYBOARDS["menu"](lang=new_lang), parse_mode="HTML")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: CallbackQuery):
    lang = await get_user_lang(callback_query)
    welcome_text = LOCALIZATION[lang]["welcome"].format(name=callback_query.from_user.first_name)
    await callback_query.message.edit_text(text=welcome_text, reply_markup=KEYBOARDS["menu"](lang=lang), parse_mode="HTML")
    await callback_query.answer()

@router.message(Command("support"))
async def cmd_support(message: Message):
    lang = await get_user_lang(message)
    await message.answer(LOCALIZATION[lang]["support_prompt"], reply_markup=KEYBOARDS["back"](lang=lang))

@router.callback_query(F.data == "show_about")
async def show_about(callback_query: CallbackQuery):
    lang = await get_user_lang(callback_query)
    await callback_query.message.edit_text(text=LOCALIZATION[lang]["about_text"], reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")
    await callback_query.answer()

@router.callback_query(F.data == "show_rules")
async def show_rules(callback_query: CallbackQuery):
    lang = await get_user_lang(callback_query)
    await callback_query.message.edit_text(text=LOCALIZATION[lang]["rules_text"], reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML", disable_web_page_preview=True)
    await callback_query.answer()

@router.callback_query(F.data == "show_support")
async def show_support(callback_query: CallbackQuery):
    lang = await get_user_lang(callback_query)
    await callback_query.message.edit_text(text=LOCALIZATION[lang]["support_text"], reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")
    await callback_query.answer()

@router.message(F.text, ~F.text.startswith("/"))
async def handle_text_tickets(message: Message):
    lang = await get_user_lang(message)
    logger.info(f"📝 Sending tech support ticket from: {message.from_user.id}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{WEB_API_URL}/api/tickets", json={
                "tg_user_id": message.from_user.id,
                "username": message.from_user.username or "unknown",
                "text": message.text
            })
            if resp.status_code == 200:
                data = resp.json()
                success_msg = LOCALIZATION[lang]["ticket_success"].format(num=data.get('ticket_number', ''))
                await message.answer(success_msg, reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")
                return
    except Exception as e:
        logger.error(f"❌ Failed to proxy ticket to web backend: {e}")

    await message.answer(LOCALIZATION[lang]["ticket_error"], reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")
