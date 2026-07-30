import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import BACKEND_API_URL, HOST_API_KEY, logger
from bot.keyboards import KEYBOARDS
from bot.utils import api_call
from bot.handlers.common import format_balance_from_state

router = Router()

# ============================================================
# ВНУТРЕННИЙ СЕРВИСНЫЙ СЛОЙ (ОБРАБОТКА ЗАПРОСОВ)
# ============================================================

async def _execute_invoice_creation(callback_query: CallbackQuery, tariff_slug: str, method_id: str):
    """
    Централизованная функция отправки запроса в биллинг бэкенда.
    Безопасно перерисовывает интерфейс Telegram без изменения frozen-объектов.
    """
    # Сопоставляем методы с ISO-валютами шлюзов
    currency_map = {"2": "RUB", "10": "RUB", "11": "RUB", "12": "USD", "13": "USDT"}
    selected_currency = currency_map.get(method_id, "RUB")

    # ИСПРАВЛЕНО: Безопасный вызов Telegram API без мутации frozen-объектов Pydantic!
    await callback_query.message.edit_text(
        text="⏳ <i>Формирую безопасный запрос к серверу, пожалуйста, подождите...</i>"
    )

    target_url = f"{BACKEND_API_URL}/api/billing/create-invoice"
    payload = {
        "tg_user_id": callback_query.from_user.id,
        "email": None,
        "tariff_slug": f"sub_{tariff_slug.lower()}", # Превращаем 'free' в 'sub_free', '24m' в 'sub_24m'
        "currency": selected_currency
    }

    result = await api_call("POST", target_url, api_key=HOST_API_KEY, json=payload)

    if not result or result.get("state") == "error":
        await callback_query.message.edit_text(
            text="❌ Сервер биллинга отклонил операцию. Попробуйте позже.",
            reply_markup=KEYBOARDS["back"]()
        )
        return

    # Сценарий А: Требуется оплата (Платный тариф)
    if result.get("status") == "payment_required":
        payment_url = result.get("payment_url")
        amount = result.get("amount", 0)

        pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton(text="⬅️ Изменить способ оплаты", callback_data=f"t_{tariff_slug}")]
        ])
        await callback_query.message.edit_text(
            text=f"💳 <b>Счет на оплату успешно сформирован!</b>\n\nСумма к оплате: <b>{amount:.2f} {selected_currency}</b>\n\nИспользуйте официальную кнопку ниже для перехода на безопасную страницу оплаты шлюза Platega:",
            reply_markup=pay_keyboard
        )

    # Сценарий Б: Бесплатный тариф (Выдаем готовый профиль туннеля Ulysses)
    elif result.get("status") == "free_tariff" or result.get("subscription_link"):
        msg = (
            f"🎉 <b>Ваш бесплатный тест-драйв Ulysses VPN успешно активирован!</b>\n\n"
            f"🔑 <b>Ваша персональная ссылка подписки:</b>\n"
            f"<code>{result['subscription_link']}</code>\n\n"
            f"⏳ Срок действия: до <b>{result.get('expires_at', '')[:10]}</b>\n\n"
            f"📥 <b>Краткая инструкция по подключению:</b>\n"
            f"1. Нажмите на поле со ссылкой выше, чтобы скопировать её.\n"
            f"2. Скачайте и запустите приложение <b>Hiddify Next</b> на вашем устройстве.\n"
            f"3. Нажмите кнопку <b>'Добавить профиль'</b> (или значок Плюса) ➔ выберите вариант <b>'Из буфера обмена'</b>.\n"
            f"4. Нажмите круглую кнопку подключения в центре экрана.\n\n"
            f"🚀 Приятного и безопасного полета без блокировок!"
        )
        await callback_query.message.edit_text(text=msg, reply_markup=KEYBOARDS["back"]())

    else:
        # Обработка ошибок валидации ("Бесплатный тариф можно активировать только один раз")
        error_text = result.get("message", "Ошибка проведения операции.")
        await callback_query.message.edit_text(text=f"⚠️ {error_text}", reply_markup=KEYBOARDS["back"]())


# ============================================================
# АСИНХРОННЫЕ ХЭНДЛЕРЫ КНОПОК И КОМАНД
# ============================================================

@router.message(Command("buy"))
@router.callback_query(F.data == "buy_tariff")
async def show_clean_tariffs(event):
    """ЭКРАН 1: Загрузка тарифной сетки из СУБД и вывод чистых кнопок тарифов."""
    is_callback = isinstance(event, CallbackQuery)
    message_obj = event.message if is_callback else event

    target_url = f"{BACKEND_API_URL}/api/billing/tariffs"
    raw_tariffs = await api_call("GET", target_url, api_key=HOST_API_KEY)

    if not raw_tariffs or raw_tariffs.get("state") == "error":
        msg_text = "❌ Не удалось загрузить тарифную сетку с сервера."
        if is_callback:
            await message_obj.edit_text(text=msg_text)
            await event.answer()
        else:
            await message_obj.answer(msg_text)
        return

    tariffs_list = [{"slug": k, "name_ru": v["name_ru"]} for k, v in raw_tariffs.items()]
    display_msg = "🔌 <b>Доступные тарифные планы Ulysses VPN:</b>\n\n<i>Выберите интересующий вас период подписки:</i>"
    reply_kb = KEYBOARDS["tariffs"](tariffs=tariffs_list)

    if is_callback:
        await message_obj.edit_text(text=display_msg, reply_markup=reply_kb)
        await event.answer()
    else:
        await message_obj.answer(text=display_msg, reply_markup=reply_kb)

@router.callback_query(F.data.startswith("t_"))
async def process_tariff_click(callback_query: CallbackQuery):
    """ЭКРАН 2: Перехват выбранного тарифа. Сквозная мгновенная активация для Free."""
    tariff_slug = callback_query.data.replace("t_", "", 1)

    if tariff_slug.lower() == "free":
        logger.info(f"🎁 Пользователь {callback_query.from_user.id} запросил тест-драйв. Минуем Platega меню...")

        # ИСПРАВЛЕНО: Явно передаем 'free', чтобы функция ниже сгенерировала верный sub_free инвойс
        await _execute_invoice_creation(callback_query, tariff_slug="free", method_id="2")
        await callback_query.answer()
        return

    # Логика для платных тарифов (выводит 5 красивых русских кнопок Platega)
    await callback_query.message.edit_text(
        text=f"💳 <b>Выбран тарифный план: {tariff_slug.upper()}</b>\n\nТеперь выберите наиболее удобный метод оплаты шлюза Platega:",
        reply_markup=KEYBOARDS["payment_methods"](tariff_slug=tariff_slug)
    )
    await callback_query.answer()

@router.callback_query(F.data.startswith("pay:"))
async def process_payment_send(callback_query: CallbackQuery):
    """ФИНАЛ: Обработка клика по одной из 5 платежных кнопок для платных тарифов."""
    _, tariff_slug, method_id = callback_query.data.split(":")
    await _execute_invoice_creation(callback_query, tariff_slug=tariff_slug, method_id=method_id)
    await callback_query.answer()

# ============================================================
# ⚙️ НАВИГАЦИОННЫЙ СЛОЙ И ИНФОРМАЦИОННЫЕ ЭКРАНЫ
# ============================================================

@router.callback_query(F.data.in_(["show_about", "show_rules", "show_support", "back_to_menu"]))
async def process_menu_navigation(callback_query: CallbackQuery):
    """
    Глобальный обработчик информационных кнопок и возврата назад.
    Читает Markdown-тексты напрямую с диска из папки bot/sections/, исключая зависания!
    """
    action = callback_query.data

    # --- Сценарий А: Пользователь нажал кнопку "Назад в меню" ---
    if action == "back_to_menu":
        target_url = f"{BACKEND_API_URL}/api/bot/state?tg_user_id={callback_query.from_user.id}"
        state = await api_call("GET", target_url, api_key=HOST_API_KEY)

        if not state or state.get("state") == "error":
            await callback_query.answer("⚠️ Ошибка синхронизации главного меню. Попробуйте ввести /start")
            return

        # Определяем, какую клавиатуру вернуть пользователю на основе его статуса в бэкенде
        kb_name = state.get("keyboard", "back")
        if kb_name == "tariffs":
            tariffs_resp = await api_call("GET", f"{BACKEND_API_URL}/api/billing/tariffs", api_key=HOST_API_KEY)
            t_list = [{"slug": k, "name_ru": v["name_ru"]} for k, v in tariffs_resp.items()] if tariffs_resp else []
            keyboard = KEYBOARDS["tariffs"](t_list)
        else:
            keyboard = KEYBOARDS.get(kb_name, KEYBOARDS["back"])()

        await callback_query.message.edit_text(
            text=state.get("message", "📋 <b>Главное меню Ulysses VPN:</b>"),
            reply_markup=keyboard
        )
        await callback_query.answer()
        return

    # --- Сценарий Б: Клиент нажал кнопки "О сервисе", "Документы" или "Поддержка" ---
    import os
    from pathlib import Path

    # Вычисляем путь к папке bot/sections/ относительно текущего файла billing.py
    # Path(__file__).resolve().parent -> bot/handlers/
    # .parent.parent -> корень bot/
    BOT_ROOT = Path(__file__).resolve().parent.parent

    files_map = {
        "show_about": BOT_ROOT / "sections" / "service.md",
        "show_rules": BOT_ROOT / "sections" / "rules.md",
    }

    target_file = files_map.get(action)
    selected_message = None

    # Пытаемся прочитать Markdown-файл с диска
    if target_file and os.path.exists(target_file):
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                selected_message = f.read()
        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла контента ботом: {e}")

    # Заглушки на случай, если файлы markdown физически отсутствуют на сервере
    if not selected_message:
        if action == "show_about":
            selected_message = (
                "ℹ️ <b>О сервисе Ulysses VPN</b>\n\n"
                "Наш сервис предоставляет безопасные удаленные прокси-каналы для ИТ-специалистов, разработчиков и сетевых администраторов.\n\n"
                "• Безопасное тестирование веб-приложений из различных локаций.\n"
                "• Шифрование исходящего интернет-трафика при работе в незащищенных публичных сетях Wi-Fi.\n"
                "• Организация защищенных туннелей для удаленного администрирования серверов.\n\n"
                "После аренды доступа вы получаете индивидуальный токен для подключения к удаленному узлу."
            )
        elif action == "show_rules":
            selected_message = (
                "📜 <b>Пользовательское соглашение и правила</b>\n\n"
                "1. Запрещено использовать прокси-каналы для совершения противоправных действий (DDoS, спам, взлом).\n"
                "2. Одна подписка (один ключ) предназначена строго для личного использования на ваших устройствах.\n"
                "3. Сервис гарантирует аптайм серверов на уровне 99.9%."
            )
        else:
            # show_support сценарий
            selected_message = (
                "✉️ <b>Техническая поддержка Ulysses Lab</b>\n\n"
                "Дежурная смена инженеров на связи 24/7/365.\n\n"
                "👉 Чтобы отправить официальное обращение, просто <b>напишите ваш вопрос обычным текстовым сообщением</b> прямо сюда, в диалог с ботом.\n\n"
                "<i>Система автоматически создаст тикет и передаст его в работу дежурной смене. Нажмите кнопку 'Назад', чтобы вернуться в меню.</i>"
            )

    # Прикрепляем инлайн-кнопку "Назад в меню" под текстом
    kb_markup = KEYBOARDS["back"]()
    await callback_query.message.edit_text(text=selected_message, reply_markup=kb_markup)
    await callback_query.answer()

# BALANCE

@router.callback_query(F.data == "check_balance")
async def process_balance_click(callback_query: CallbackQuery):
    """
    Обработчик клика по inline-кнопке '📊 Мой баланс'.
    Считывает актуальные метрики трафика с бэкенда и рендерит HTML-карточку.
    """
    # Выводим промежуточный статус, чтобы пользователь видел реакцию бота
    await callback_query.message.edit_text("⏳ <i>Считываю метрики нод, пожалуйста, подождите...</i>")

    target_url = f"{BACKEND_API_URL}/api/bot/action"

    # Запрашиваем данные у бэкенда через наш асинхронный helper
    state = await api_call(
        "POST",
        target_url,
        api_key=HOST_API_KEY,
        json={"tg_user_id": callback_query.from_user.id, "action": "check_balance"}
    )

    if state and state.get("balance"):
        # Если бэкенд отдал данные, форматируем их через готовую функцию
        # Функция format_balance_from_state уже импортирована в этот файл выше!
        balance_html = format_balance_from_state(state["balance"])

        await callback_query.message.edit_text(
            text=balance_html,
            reply_markup=KEYBOARDS["back"]()
        )
    else:
        # Если бэкенд вернул ошибку или ноды не ответили
        await callback_query.message.edit_text(
            text="❌ Не удалось получить состояние баланса. Проверьте статус подписки позже.",
            reply_markup=KEYBOARDS["back"]()
        )

    await callback_query.answer()
