# backend/app/services/subscription_links.py

"""
Единая точка формирования ссылок подписки.
Используется и при бесплатной активации, и при оплате через Platega.
"""
import logging
from app.config import settings

logger = logging.getLogger(__name__)


def build_subscription_links(hiddify_uuid: str) -> dict:
    """
    Возвращает {'simple_link': ..., 'advanced_link': ...}.
    Никаких обращений к нодам — только формирование URL.
    Реальная агрегация конфига происходит на стороне FastAPI-роутера
    /subscription/{uuid}/simple и /advanced.
    """
    uuid_str = str(hiddify_uuid).strip().lower()
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    base = f"https://{domain}/subscription/{uuid_str}"

    return {
        "simple_link": f"{base}/simple#Ulysses-simple",
        "advanced_link": f"{base}/advanced#Ulysses-advanced",
    }
