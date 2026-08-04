# bot/keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """ЭКРАН 0: Главное интерактивное меню управления подпиской."""
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text="🚀 Buy / Renew Subscription", callback_data="buy_tariff")],
            [InlineKeyboardButton(text="ℹ️ Info & Balance", callback_data="check_balance")],
            [InlineKeyboardButton(text="ℹ️ About Service", callback_data="show_about"),
             InlineKeyboardButton(text="📜 Documents / Rules", callback_data="show_rules")],
            [InlineKeyboardButton(text="✉️ Tech Support", callback_data="show_support")],
            [InlineKeyboardButton(text="🇷🇺 Изменить язык на RU", callback_data="set_lang:ru")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="🚀 Купить / Продлить подписку", callback_data="buy_tariff")],
            [InlineKeyboardButton(text="ℹ️ Информация", callback_data="check_balance")],
            [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="show_about"),
             InlineKeyboardButton(text="📜 Документы", callback_data="show_rules")],
            [InlineKeyboardButton(text="✉️ Тех. Поддержка", callback_data="show_support")],
            [InlineKeyboardButton(text="🇺🇸 Change language to EN", callback_data="set_lang:en")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_subscriptions_keyboard(tariffs: list = None, lang: str = "ru") -> InlineKeyboardMarkup:
    """ЭКРАН 1: Сетка доступных тарифных планов."""
    buttons = []
    if tariffs:
        for t in tariffs:
            name_key = "name_en" if lang == "en" else "name_ru"
            raw_name = t.get(name_key, t.get("name_ru", ""))
            clean_name = raw_name.replace("🎁 ", "").replace("📅 ", "").replace("—", "-")
            slug = t["slug"].replace("sub_", "")
            buttons.append([InlineKeyboardButton(text=clean_name, callback_data=f"t_{slug}")])

    back_text = "⬅️ Back to Main Menu" if lang == "en" else "⬅️ В главное меню"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_methods_keyboard(tariff_slug: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """ЭКРАН 2 (Запасной): Выбор конкретной валюты платежа."""
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text="💳 Pay in RUB (RU Cards, SBP, Crypto)", callback_data=f"pay:{tariff_slug}:RUB")],
            [InlineKeyboardButton(text="💲 Pay in USD (Intl Cards, Crypto)", callback_data=f"pay:{tariff_slug}:USD")],
            [InlineKeyboardButton(text="💶 Pay in EUR (Intl Cards, Crypto)", callback_data=f"pay:{tariff_slug}:EUR")],
            [InlineKeyboardButton(text="⬅️ Change Plan", callback_data="buy_tariff")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="💳 Оплатить в RUB (карты РФ, СБП, крипта)", callback_data=f"pay:{tariff_slug}:RUB")],
            [InlineKeyboardButton(text="💲 Оплатить в USD (зарубежные карты, крипта)", callback_data=f"pay:{tariff_slug}:USD")],
            [InlineKeyboardButton(text="💶 Оплатить в EUR (зарубежные карты, крипта)", callback_data=f"pay:{tariff_slug}:EUR")],
            [InlineKeyboardButton(text="⬅️ Изменить тариф", callback_data="buy_tariff")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Стандартная кнопка возврата в главное меню."""
    text = "⬅️ Back to Main Menu" if lang == "en" else "⬅️ В главное меню"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="back_to_menu")]])

def get_lang_inline_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Кнопки для быстрого переключения языка интерфейса (ЭКРАН НАСТРОЙКИ ЯЗЫКА)."""
    if lang == "en":
        buttons = [
            [InlineKeyboardButton(text="🇷🇺 Изменить язык на RU", callback_data="set_lang:ru")],
            [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="back_to_menu")]
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="🇺🇸 Change language to EN", callback_data="set_lang:en")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_menu")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Не забудь обновить словарь KEYBOARDS в самом низу файла keyboards.py:
KEYBOARDS = {
    "menu": get_main_menu_keyboard,
    "tariffs": get_subscriptions_keyboard,
    "payment_methods": get_payment_methods_keyboard,
    "back": get_back_keyboard,
    "lang_screen": get_lang_inline_keyboard,  # <-- Добавили новую строчку
}
