# backend/app/services/rf_node_client.py
"""
Клиент для RF-ноды (российский exit).
Тонкая обёртка над HTTP-API /opt/rf-node-api/main.py на RF-ноде.

Все методы — best-effort: никогда не выбрасывают исключение,
чтобы недоступность RF-ноды не ломала создание/активацию подписок.
"""

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 5.0


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.RF_NODE_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _is_enabled() -> bool:
    return (
        getattr(settings, "RF_NODE_ENABLED", False)
        and bool(getattr(settings, "RF_NODE_API_URL", ""))
        and bool(getattr(settings, "RF_NODE_API_TOKEN", ""))
    )


async def add_user(uuid: str, flow: str | None = None) -> bool:
    """Добавить UUID в sing-box на RF-ноде. Идемпотентно."""
    if not _is_enabled():
        logger.debug("🇷🇺 [RF-NODE] disabled, skip add")
        return False

    payload = {
        "uuid": str(uuid),
        "flow": flow or settings.RF_NODE_FLOW,
    }
    url = f"{settings.RF_NODE_API_URL.rstrip('/')}/users"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=_headers())
            if r.status_code in (200, 201):
                data = r.json()
                logger.info(f"🇷🇺 [RF-NODE] add {uuid} → {data.get('status')}")
                return True
            logger.warning(
                f"⚠️ [RF-NODE] add {uuid}: HTTP {r.status_code}: {r.text[:200]}"
            )
            return False
    except Exception as e:
        logger.warning(f"⚠️ [RF-NODE] add {uuid}: недоступна ({e})")
        return False


async def remove_user(uuid: str) -> bool:
    """Удалить UUID из sing-box на RF-ноде."""
    if not _is_enabled():
        return False

    url = f"{settings.RF_NODE_API_URL.rstrip('/')}/users/{uuid}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.delete(url, headers=_headers())
            if r.status_code == 200:
                data = r.json()
                logger.info(f"🇷🇺 [RF-NODE] remove {uuid} → {data.get('status')}")
                return True
            logger.warning(
                f"⚠️ [RF-NODE] remove {uuid}: HTTP {r.status_code}: {r.text[:200]}"
            )
            return False
    except Exception as e:
        logger.warning(f"⚠️ [RF-NODE] remove {uuid}: недоступна ({e})")
        return False


async def sync_users(uuids: list[str]) -> bool:
    """Полная замена списка UUID на RF-ноде."""
    if not _is_enabled():
        return False

    payload = {"uuids": [str(u) for u in uuids]}
    url = f"{settings.RF_NODE_API_URL.rstrip('/')}/sync"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, json=payload, headers=_headers())
            if r.status_code == 200:
                data = r.json()
                logger.info(f"🇷🇺 [RF-NODE] sync → {data.get('count')} uuids")
                return True
            logger.warning(
                f"⚠️ [RF-NODE] sync: HTTP {r.status_code}: {r.text[:200]}"
            )
            return False
    except Exception as e:
        logger.warning(f"⚠️ [RF-NODE] sync: недоступна ({e})")
        return False


async def list_users() -> list[dict] | None:
    """Список UUID на RF-ноде (для диагностики)."""
    if not _is_enabled():
        return None

    url = f"{settings.RF_NODE_API_URL.rstrip('/')}/users"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url, headers=_headers())
            if r.status_code == 200:
                return r.json().get("users", [])
            return None
    except Exception:
        return None
