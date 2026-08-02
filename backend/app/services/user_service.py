"""
Сервис для работы с пользователями: баланс, трафик, профиль.
"""
import httpx
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.activation_manager import get_or_create_user

logger = logging.getLogger(__name__)

async def get_user_balance(
    db: AsyncSession,
    tg_user_id: int = None,
    hiddify_uuid: str = None,
    email: str = None,
    username: str = None
) -> dict | None:
    """Получить баланс и информацию о подписке пользователя."""

    # 1. Поиск пользователя через AM
    user = None
    if tg_user_id:
        user = await get_or_create_user(db, tg_user_id=tg_user_id)
    elif email:
        user = await get_or_create_user(db, email=email)
    elif hiddify_uuid:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid"),
            {"uuid": str(hiddify_uuid).lower().strip()}
        )
        row = res.fetchone()
        if row:
            user = {"user_id": row[0], "hiddify_uuid": row[1], "email": row[2], "tg_user_id": row[3]}
    elif username:
        clean = str(username).lower().replace("@", "").strip()
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE LOWER(tg_username) = :uname"),
            {"uname": clean}
        )
        row = res.fetchone()
        if row:
            user = {"user_id": row[0], "hiddify_uuid": row[1], "email": row[2], "tg_user_id": row[3]}

    if not user:
        return None

    # 2. Последняя подписка
    sub_res = await db.execute(
        text("SELECT tariff_slug, status, expires_at FROM subscriptions WHERE user_id = :uid ORDER BY expires_at DESC LIMIT 1"),
        {"uid": user["user_id"]}
    )
    sub = sub_res.fetchone()
    # now = datetime.utcnow()
    now = datetime.now(timezone.utc)
    if not sub:
        return {
            "status": "disabled",
            "email": user["email"],
            "hiddify_uuid": user["hiddify_uuid"],
            "traffic": {"used_gb": 0.0, "total_gb": 0.0, "remaining_gb": 0.0, "percent": 0.0},
            "days_left": 0,
            "is_active": False,
            "tg_user_id": user["tg_user_id"],
            "tg_username": None,
            "db_id": user["user_id"],
            "subscription_link": _make_subscription_link(user["hiddify_uuid"]),
            "expires_at": None
        }

    tariff_slug, status, expires_at = sub
    days_left = 0
    if expires_at:
        expires_naive = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
        days_left = max(0, (expires_naive - now).days)

    is_active = status == "active" and days_left > 0
    traffic_data = await _get_hiddify_traffic(user["hiddify_uuid"]) or {
        "used_gb": 0.0, "total_gb": 0.0, "remaining_gb": 0.0, "percent": 0.0
    }

    return {
        "status": "active" if is_active else "disabled",
        "email": user["email"],
        "hiddify_uuid": user["hiddify_uuid"],
        "traffic": traffic_data,
        "days_left": days_left,
        "is_active": is_active,
        "tg_user_id": user["tg_user_id"],
        "tg_username": None,
        "db_id": user["user_id"],
        "subscription_link": _make_subscription_link(user["hiddify_uuid"]),
        "expires_at": expires_at.isoformat() if expires_at else None
    }

async def _get_hiddify_traffic(hiddify_uuid: str) -> dict | None:
    """Запрос к HFM API для получения трафика пользователя."""
    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                for u in response.json():
                    if str(u.get("uuid", "")).lower() == str(hiddify_uuid).lower():
                        usage = float(u.get("current_usage_GB", 0))
                        total = float(u.get("usage_limit_GB", 0))
                        return {
                            "used_gb": round(usage, 2),
                            "total_gb": round(total, 2),
                            "remaining_gb": round(max(0.0, total - usage), 2),
                            "percent": round((usage / total * 100) if total > 0 else 0, 1)
                        }
    except Exception as e:
        logger.error(f"❌ Hiddify API Error for uuid {hiddify_uuid}: {e}")
    return None

def _make_subscription_link(hiddify_uuid: str) -> str:
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    return f"https://{domain}/subscription/{hiddify_uuid}/#Ulysses"
