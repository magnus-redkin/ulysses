# backend/app/routers/admin.py

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import verify_api_key

from app.services.admin_service import (
    get_diagnostics,
    cleanup_invoices,
    get_stats,
    process_pending_provisioning,
    check_hiddify_sync          # <-- добавить
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_api_key)]
)


@router.get("/check")
async def admin_check_system(
    query: Optional[str] = Query(None, description="Поиск по TG ID, email, UUID"),
    verbose: bool = Query(False, description="Развернуть детальные списки проблем"),
    hiddify_sync: bool = Query(False, description="Выполнить сверку с Hiddify"),
    db: AsyncSession = Depends(get_db)
):
    """
    Кросс-диагностика аномалий, расхождений статусов и зависших инвойсов.
    """
    # Сценарий А: поиск конкретной сущности
    if query:
        clean_q = query.strip().lower()
        sql = """
            SELECT id, tg_user_id, tg_username, email, hiddify_uuid
            FROM users
            WHERE CAST(tg_user_id AS TEXT) = :q
               OR LOWER(email) = :q
               OR CAST(hiddify_uuid AS TEXT) = :q
            LIMIT 1
        """
        res = await db.execute(text(sql), {"q": clean_q})
        user_row = res.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        u_id, tg_id, username, email_db, hf_uuid = user_row

        sub_res = await db.execute(
            text("SELECT id, status, tariff_slug, expires_at FROM subscriptions WHERE user_id = :uid ORDER BY id DESC LIMIT 1"),
            {"uid": u_id}
        )
        sub_row = sub_res.fetchone()
        sub_data = None
        if sub_row:
            sub_data = {
                "id": sub_row[0],
                "status": sub_row[1],
                "tariff_slug": sub_row[2],
                "expires_at": sub_row[3].strftime("%Y-%m-%d %H:%M UTC") if sub_row[3] else None
            }

        return {
            "found_in_db": True,
            "account": {
                "id": u_id,
                "tg_user_id": tg_id,
                "tg_username": username,
                "email": email_db,
                "hiddify_uuid": str(hf_uuid) if hf_uuid else None
            },
            "subscription": sub_data,
            "anomaly": None,
            "hiddify_profile": None
        }

    # Сценарий Б: полная сводка
    data = await get_diagnostics(db, verbose)
    # Если запрошена синхронизация с Hiddify, добавляем результаты
    if hiddify_sync:
        sync_data = await check_hiddify_sync(db)
        data["status_mismatches"] = sync_data["status_mismatches"]
        data["anomalies"] = sync_data["anomalies"]
        # Обновляем счётчики в summary
        data["summary"]["status_mismatches_count"] = len(sync_data["status_mismatches"])
        data["summary"]["hiddify_anomalies_count"] = len(sync_data["anomalies"])

    return data


@router.post("/fix/cleanup-invoices")
async def fix_cleanup_invoices(db: AsyncSession = Depends(get_db)):
    """Удалить просроченные инвойсы (pending > 24 часов)."""
    deleted = await cleanup_invoices(db)
    logger.info(f"Очистка инвойсов: удалено {deleted} записей")
    return {"status": "cleaned", "deleted_count": deleted}

from app.services.admin_service import get_stats  # в начало файла

@router.get("/stats")
async def admin_get_stats(
    verbose: bool = Query(False, description="Показать детализацию зависших подписок"),
    db: AsyncSession = Depends(get_db)
):
    """Сбор бизнес-метрик и мониторинг очередей."""
    return await get_stats(db, verbose)

@router.post("/fix/process-pending")
async def fix_process_pending(
    limit: int = Query(50, ge=1, le=200, description="Сколько подписок обработать за раз"),
    db: AsyncSession = Depends(get_db)
):
    """Принудительно вернуть зависшие подписки в очередь на обработку."""
    processed = await process_pending_provisioning(db, limit)
    logger.info(f"👷 Обработано зависших подписок: {processed}")
    return {"status": "processed", "processed_count": processed}
