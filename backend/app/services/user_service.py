# backend/app/services/user_service.py

"""
Сервис для работы с пользователями: баланс, трафик, профиль.
"""
import asyncio
import httpx
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.node_manager import node_manager

logger = logging.getLogger(__name__)


def _make_links(hiddify_uuid: str) -> dict:
    domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
    base = f"https://{domain}/subscription/{hiddify_uuid}"
    return {
        "simple_link": f"{base}/simple#Ulysses-simple",
        "advanced_link": f"{base}/advanced#Ulysses-advanced",
    }


async def get_user_balance(
    db: AsyncSession,
    tg_user_id: int = None,
    hiddify_uuid: str = None,
    email: str = None,
    username: str = None,
) -> dict | None:
    user = None

    if tg_user_id:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE tg_user_id = :tg_id"),
            {"tg_id": tg_user_id},
        )
        row = res.fetchone()
        if row:
            user = {"user_id": row[0], "hiddify_uuid": row[1], "email": row[2], "tg_user_id": row[3]}

    elif email:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE LOWER(email) = :email"),
            {"email": str(email).lower().strip()},
        )
        row = res.fetchone()
        if row:
            user = {"user_id": row[0], "hiddify_uuid": row[1], "email": row[2], "tg_user_id": row[3]}

    elif hiddify_uuid:
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE CAST(hiddify_uuid AS TEXT) = :uuid"),
            {"uuid": str(hiddify_uuid).lower().strip()},
        )
        row = res.fetchone()
        if row:
            user = {"user_id": row[0], "hiddify_uuid": row[1], "email": row[2], "tg_user_id": row[3]}

    elif username:
        clean = str(username).lower().replace("@", "").strip()
        res = await db.execute(
            text("SELECT id, hiddify_uuid, email, tg_user_id FROM users WHERE LOWER(tg_username) = :uname"),
            {"uname": clean},
        )
        row = res.fetchone()
        if row:
            user = {"user_id": row[0], "hiddify_uuid": row[1], "email": row[2], "tg_user_id": row[3]}

    if not user:
        logger.debug(f"🔍 Пользователь не найден в БД (tg_id={tg_user_id}, uuid={hiddify_uuid})")
        return None

    sub_res = await db.execute(
        text("SELECT tariff_slug, status, expires_at FROM subscriptions WHERE user_id = :uid ORDER BY expires_at DESC LIMIT 1"),
        {"uid": user["user_id"]},
    )
    sub = sub_res.fetchone()
    now = datetime.now(timezone.utc)

    links = _make_links(user["hiddify_uuid"])

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
            "simple_link": links["simple_link"],
            "advanced_link": links["advanced_link"],
            "expires_at": None,
        }

    tariff_slug, status, expires_at = sub
    days_left = 0
    if expires_at:
        if expires_at.tzinfo is None:
            expires_aware = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_aware = expires_at.astimezone(timezone.utc)
        days_left = max(0, (expires_aware - now).days)

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
        "simple_link": links["simple_link"],
        "advanced_link": links["advanced_link"],
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


async def _get_hiddify_traffic(hiddify_uuid: str) -> dict | None:
    """
    Запрашивает usage у первой доступной HFM-ноды.
    """
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        logger.warning("⚠️ Нет активных HFM нод для запроса трафика")
        return None

    clean_uuid = str(hiddify_uuid).strip().lower()

    async def _one(node):
        url = f"https://{node['domain']}/{node['proxy_path_admin']}/api/v2/admin/user/{clean_uuid}/"
        headers = {"Hiddify-API-Key": node.get("admin_uuid", "")}
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False, follow_redirects=True) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    u = r.json()
                    usage = float(u.get("current_usage_GB", 0))
                    total = float(u.get("usage_limit_GB", 0))
                    return {
                        "used_gb": round(usage, 2),
                        "total_gb": round(total, 2),
                        "remaining_gb": round(max(0.0, total - usage), 2),
                        "percent": round((usage / total * 100) if total > 0 else 0, 1),
                    }
                if r.status_code == 404:
                    return None
                logger.error(f"❌ [{node['id']}] traffic HTTP {r.status_code}: {r.text[:150]}")
        except Exception as e:
            logger.error(f"❌ [{node['id']}] traffic error: {e}")
        return None

    results = await asyncio.gather(*(_one(n) for n in nodes))
    for r in results:
        if r is not None:
            return r
    return None
