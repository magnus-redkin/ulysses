# backend/app/routers/sub_render.py (после рефакторинга)
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.sub_render import generate_singbox_json

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Subscription Render"])

@router.get("/subscription/{uuid}")
async def render_singbox_subscription(
    uuid: str,
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db)
):
    clean_uuid = uuid.strip().lower()
    logger.info(f"📡 [SUB RENDER] Запрос подписки для UUID: {clean_uuid}")
    try:
        result = await generate_singbox_json(clean_uuid, db)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
