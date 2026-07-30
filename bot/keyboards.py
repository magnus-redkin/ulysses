from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_subscriptions_keyboard(tariffs: list = None) -> InlineKeyboardMarkup:
    """Step 1: Visual layout of clean tariff periods without currency radio buttons."""
    buttons = []
    if tariffs:
        for t in tariffs:
            clean_name = t["name_ru"].replace("🎁 ", "").replace("📅 ", "").replace("—", "-")
            slug = t["slug"].replace("sub_", "")
            buttons.append([InlineKeyboardButton(text=clean_name, callback_data=f"t_{slug}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_methods_keyboard(tariff_slug: str) -> InlineKeyboardMarkup:
    """Вывод 5 целевых платежных методов Platega на чистом русском языке."""
    buttons = [
        [InlineKeyboardButton(text="📱 Система Быстрых Платежей, QR (СБП)", callback_data=f"pay:{tariff_slug}:2")],
        [InlineKeyboardButton(text="💳 Банковские карты РФ (RUB)", callback_data=f"pay:{tariff_slug}:10")],
        [InlineKeyboardButton(text="🛒 Карточный эквайринг (РФ)", callback_data=f"pay:{tariff_slug}:11")],
        [InlineKeyboardButton(text="🌍 Зарубежные карты (USD/EUR)", callback_data=f"pay:{tariff_slug}:12")],
        [InlineKeyboardButton(text="🪙 Криптовалюта (USDT/TON/etc)", callback_data=f"pay:{tariff_slug}:13")],
        [InlineKeyboardButton(text="⬅️ Изменить тариф", callback_data="buy_tariff")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


KEYBOARDS = {
    "tariffs": lambda tariffs=None: get_subscriptions_keyboard(tariffs),
    "payment_methods": lambda tariff_slug: get_payment_methods_keyboard(tariff_slug),

    "active": lambda: InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Check My Status", callback_data="check_balance")],
        [InlineKeyboardButton(text="🛒 Purchase / Renew", callback_data="buy_tariff")],
        [InlineKeyboardButton(text="ℹ️ About Service", callback_data="show_about"),
         InlineKeyboardButton(text="📜 Legal / Rules", callback_data="show_rules")]
    ]),

    "renew": lambda: InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Renew Subscription", callback_data="buy_tariff")],
        [InlineKeyboardButton(text="📊 My Balance", callback_data="check_balance")],
        [InlineKeyboardButton(text="📜 Legal / Rules", callback_data="show_rules")]
    ]),

    "back": lambda: InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="back_to_menu")]
    ]),
}
