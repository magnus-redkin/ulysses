# backend/app/services/subscription_links.py

"""
Единая точка формирования ссылок подписки.
Используется и при бесплатной активации, и при оплате через Platega.
"""
import logging
from app.config import settings

logger = logging.getLogger(__name__)

def build_subscription_links(hiddify_uuid: str) -> dict:
    uuid_str = str(hiddify_uuid).strip().lower()
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    base = f"https://{domain}/subscription/{uuid_str}"

    return {
        "global_link": f"{base}#Ulysses-global",
        "ru_link": f"{base}/ru#Ulysses-ru",
        "compat_link": f"{base}/compat#Ulysses-compat",
    }
