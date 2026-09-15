# backend/app/services/rf_node_config.py
"""
Локальное построение sing-box outbound для RF-ноды.
Никаких HTTP-запросов — все параметры берутся из settings.
"""

import logging
from app.config import settings

logger = logging.getLogger(__name__)


def build_rf_outbound(user_uuid: str) -> dict | None:
    """
    Возвращает sing-box outbound для RF-ноды или None, если нода выключена.
    Используется и для Simple, и для Advanced.
    """
    if not getattr(settings, "RF_NODE_ENABLED", False):
        return None

    if not all([
        settings.RF_NODE_HOST,
        settings.RF_NODE_PUBLIC_KEY,
        settings.RF_NODE_SHORT_ID,
        settings.RF_NODE_SNI,
    ]):
        logger.warning("⚠️ [RF-NODE] не хватает параметров для outbound")
        return None

    tag = getattr(settings, "RF_NODE_TAG", None) or "🇷🇺 RU — VLESS Reality"

    return {
        "type": "vless",
        "tag": tag,
        "server": settings.RF_NODE_HOST,
        "server_port": settings.RF_NODE_PORT,
        "uuid": str(user_uuid),
        "flow": settings.RF_NODE_FLOW or "xtls-rprx-vision",
        "tls": {
            "enabled": True,
            "server_name": settings.RF_NODE_SNI,
            "utls": {"enabled": True, "fingerprint": "chrome"},
            "reality": {
                "enabled": True,
                "public_key": settings.RF_NODE_PUBLIC_KEY,
                "short_id": settings.RF_NODE_SHORT_ID,
            },
        },
    }
