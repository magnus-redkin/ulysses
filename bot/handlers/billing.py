### bot/handlers/billing.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.config import BACKEND_API_URL, HOST_API_KEY, USE_CURRENCY_SCREEN, logger
from bot.keyboards import KEYBOARDS
from bot.utils import api_call, get_user_lang

from bot.localization import BILLING_LOC

router = Router()

async def _execute_invoice_creation(callback_query: CallbackQuery, tariff_slug: str, currency: str = "RUB"):
    """Внутренний слой биллинга: создание инвойса и возврат ссылки/инструкции."""
    lang = await get_user_lang(callback_query)
    loc = BILLING_LOC[lang]

    await callback_query.message.edit_text(text=loc["loading"], parse_mode="HTML")

    target_url = f"{BACKEND_API_URL}/api/billing/create-invoice"
    payload = {
        "tg_user_id": callback_query.from_user.id,
        "email": None,
        "tariff_slug": f"sub_{tariff_slug.lower()}",
        "currency": currency
    }

    result = await api_call("POST", target_url, api_key=HOST_API_KEY, json=payload)

    if not result or result.get("state") == "error":
        await callback_query.message.edit_text(text=loc["api_error"], reply_markup=KEYBOARDS["back"](lang=lang))
        return

    # 1. Бесплатный тестовый период (или прямая выдача ссылки)
    if result.get("status") == "free_tariff" or result.get("subscription_link"):
        exp_date = result.get("expires_at", "")[:10]
        msg = loc["free_success"].format(link=result['subscription_link'], exp=exp_date)
        await callback_query.message.edit_text(text=msg, reply_markup=KEYBOARDS["back"](lang=lang), parse_mode="HTML")
        return

    # 2. Платный инвойс шлюза оплаты Platega
    if result.get("status") == "payment_required":
        payment_url = result.get("payment_url")
        amount = result.get("amount", 0)

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=loc["btn_pay"], url=payment_url)],
            [InlineKeyboardButton(text=loc["btn_change"], callback_data="buy_tariff")]
        ])

        msg = loc["invoice_created"].format(amount=amount, currency=currency)
        await callback_query.message.edit_text(text=msg, reply_markup=pay_keyboard, parse_mode="HTML")
        return

    error_text = result.get("message", "Operation error.")
    await callback_query.message.edit_text(text=f"⚠️ {error_text}", reply_markup=KEYBOARDS["back"](lang=lang))

@router.message(Command("buy"))
@router.callback_query(F.data == "buy_tariff")
async def show_clean_tariffs(event):
    """ЭКРАН 1: Рендеринг доступных тарифов."""
    lang = await get_user_lang(event)
    loc = BILLING_LOC[lang]
    is_callback = isinstance(event, CallbackQuery)
    message_obj = event.message if is_callback else event

    target_url = f"{BACKEND_API_URL}/api/billing/tariffs"
    raw_tariffs = await api_call("GET", target_url, api_key=HOST_API_KEY)

    if not raw_tariffs or raw_tariffs.get("state") == "error":
        msg_text = loc["tariff_load_err"]
        if is_callback:
            await message_obj.edit_text(text=msg_text)
            await event.answer()
        else:
            await message_obj.answer(msg_text)
        return

    tariffs_list = [{"slug": k, "name_ru": v.get("name_ru", k), "name_en": v.get("name_en", k)} for k, v in raw_tariffs.items()]
    display_msg = loc["tariff_title"]
    reply_kb = KEYBOARDS["tariffs"](tariffs=tariffs_list, lang=lang)

    if is_callback:
        await message_obj.edit_text(text=display_msg, reply_markup=reply_kb, parse_mode="HTML")
        await event.answer()
    else:
        await message_obj.answer(text=display_msg, reply_markup=reply_kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("t_"))
async def process_tariff_click(callback_query: CallbackQuery):
    """ЭКРАН 2 (Управление логикой переключения): Решаем, запрашивать ли валюту."""
    lang = await get_user_lang(callback_query)
    tariff_slug = callback_query.data.replace("t_", "", 1)

    if USE_CURRENCY_SCREEN:
        # Если запасной экран включен — перенаправляем на выбор валюты
        loc = BILLING_LOC[lang]
        await callback_query.message.edit_text(
            text=loc["choose_currency"].format(slug=tariff_slug.upper()),
            reply_markup=KEYBOARDS["payment_methods"](tariff_slug=tariff_slug, lang=lang),
            parse_mode="HTML"
        )
    else:
        # По умолчанию экран выключен, Platega разберется сама → сразу шлем RUB инвойс
        await _execute_invoice_creation(callback_query, tariff_slug=tariff_slug, currency="RUB")

    await callback_query.answer()

@router.callback_query(F.data.startswith("pay:"))
async def process_currency_selected(callback_query: CallbackQuery):
    """Обработчик запасного экрана (срабатывает, только если USE_CURRENCY_SCREEN = True)."""
    _, tariff_slug, currency = callback_query.data.split(":")
    await _execute_invoice_creation(callback_query, tariff_slug=tariff_slug, currency=currency)
    await callback_query.answer()
