import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import BACKEND_API_URL, WEB_API_URL, HOST_API_KEY, logger
from bot.keyboards import KEYBOARDS
from bot.utils import api_call

router = Router()

def format_balance_from_state(balance: dict) -> str:
    """Форматирование метрик трафика из бэкенда в чистый HTML для Telegram."""
    t = balance.get("traffic", {})
    status = "🟢 Активна" if balance.get("is_active") else "🔴 Приостановлена"
    pct = t.get("percent", 0)
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    return (
        f"📊 <b>Статус подписки</b>\n\n"
        f"Статус: {status}\n"
        f"📧 Профиль: <code>{balance.get('email', '')}</code>\n\n"
        f"📈 Потребление трафика:\n<code>{bar}</code> {pct:.1f}%\n"
        f"• Использовано: <b>{t.get('used_gb', 0):.2f} ГБ</b>\n"
        f"• Осталось: <b>{t.get('remaining_gb', 0):.2f} ГБ</b>\n"
        f"• Выделенная емкость: <b>{t.get('total_gb', 0):.1f} ГБ</b>\n\n"
        f"⏳ Срок действия: <b>{balance.get('days_left', 0)} дн.</b>"
    )

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Мягкая регистрация пользователя на бэкенде и вывод главного меню бота."""
    tg_user_id = message.from_user.id
    tg_username = message.from_user.username or "unknown"

    logger.info(f"📥 [MENU START] Запуск процесса обработки /start для {tg_user_id}")

    # Фиксируем паспорт пользователя в СУБД (там автоматически сгенерируется UUID)
    await api_call(
        "POST",
        f"{BACKEND_API_URL}/api/bot/register",
        api_key=HOST_API_KEY,
        json={"tg_user_id": tg_user_id, "tg_username": tg_username}
    )

    full_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Купить / Продлить подписку", callback_data="buy_tariff")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="show_about"),
         InlineKeyboardButton(text="📜 Документы", callback_data="show_rules")],
        [InlineKeyboardButton(text="✉️ Тех. Поддержка", callback_data="show_support")]
    ])

    welcome_text = (
        f"👋 <b>Добро пожаловать в Ulysses VPN, {message.from_user.first_name}!</b>\n\n"
        f"Ваш персональный защищенный туннель полностью готов к работе.\n"
        f"Используйте интерактивное меню ниже для управления подпиской:\n\n"
        f"👉 <i>Выберите интересующий вас раздел:</i>"
    )
    await message.answer(text=welcome_text, reply_markup=full_keyboard)


@router.message(Command("support"))
async def cmd_support(message: Message):
    """Прямая команда вызова саппорта."""
    await message.answer("🆘 Пожалуйста, напишите ваш вопрос в ответ на это сообщение. Инженеры поддержки сразу получат его:", reply_markup=KEYBOARDS["back"]())


@router.message(F.text, ~F.text.startswith("/"))
async def handle_text_tickets(message: Message):
    """Перехват обычного текста и отправка тикета на бэкенд техподдержки."""
    logger.info(f"📝 Отправка тикета в поддержку от: {message.from_user.id}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{WEB_API_URL}/api/tickets", json={
                "tg_user_id": message.from_user.id,
                "username": message.from_user.username or "unknown",
                "text": message.text
            })
            if resp.status_code == 200:
                data = resp.json()
                await message.answer(f"✅ Ваше обращение успешно зарегистрировано под №{data.get('ticket_number', '')} и передано дежурному инженеру!",
                                     reply_markup=KEYBOARDS["back"]())
                return
    except Exception as e:
        logger.error(f"❌ Не удалось проксировать тикет на веб-бэкенд: {e}")
    await message.answer("⚠️ Сервис техподдержки временно перегружен. Пожалуйста, попробуйте отправить сообщение чуть позже.", reply_markup=KEYBOARDS["back"]())
