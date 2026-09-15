# bot utils.py

import httpx
from aiogram.types import Message, CallbackQuery
from bot.config import logger, BACKEND_API_URL, HOST_API_KEY

# Временное инмемори-хранилище для имитации бэкенда до обновления СУБД
_LANG_MOCK_DB = {}


async def api_call(method: str, url: str, api_key: str = None, **kwargs) -> dict | None:
    """Централизованный обертчик для безопасных HTTP-запросов к вашему API."""
    try:
        headers = kwargs.pop("headers", {})
        if api_key:
            headers["X-API-Key"] = api_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, **kwargs)
            else:
                resp = await client.post(url, json=kwargs.get("json"), headers=headers)

            if resp.status_code == 200:
                logger.info(f"📡 [API RAW RESPONSE] from {url} ➔ {resp.text[:200]}")
                try:
                    return resp.json()
                except Exception as parse_err:
                    logger.error(f"💥 Backend returned invalid JSON string: {parse_err}")
                    return {"state": "error", "message": resp.text, "keyboard": "back"}

            logger.error(f"API {method} {url} → HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Network transport fault during API call: {e}")
    return None


async def render_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    **kwargs,
) -> Message | None:
    """
    Удаляет сообщение, из которого пришёл callback (вместе с его кнопками),
    и отправляет новое сообщение внизу чата.

    Благодаря этому:
      • каждое новое меню всегда оказывается внизу чата;
      • служебные пуши (например, 'Оплата получена' от backend) уходят наверх,
        как только пользователь делает следующее действие.
    """
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"⚠️ Не удалось удалить сообщение {callback.message.message_id}: {e}")

    try:
        return await callback.message.answer(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            **kwargs,
        )
    except Exception as e:
        logger.error(f"❌ render_screen: ошибка отправки нового сообщения: {e}")
        return None


async def get_user_lang(event: Message | CallbackQuery) -> str:
    """
    Определяет язык пользователя.
    Сначала проверяет сохраненное значение в заглушке бэкенда,
    если его нет — берет язык Telegram-клиента (автоопределение).
    """
    tg_user_id = event.from_user.id

    if tg_user_id in _LANG_MOCK_DB:
        return _LANG_MOCK_DB[tg_user_id]

    try:
        lang_code = event.from_user.language_code
        if lang_code and lang_code.lower().startswith("ru"):
            return "ru"
    except AttributeError:
        pass

    return "en"


async def set_user_lang(tg_user_id: int, lang: str) -> bool:
    _LANG_MOCK_DB[tg_user_id] = lang
    return True
