from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.config import settings
from app.services.user_service import get_user_balance
from app.dependencies import verify_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])

@router.get("/balance")
async def balance(
    tg_user_id: int = Query(None),
    hiddify_uuid: str = Query(None),
    email: str = Query(None),
    username: str = Query(None),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Получить баланс пользователя. Требует X-API-Key."""
    result = await get_user_balance(db, tg_user_id, hiddify_uuid, email, username)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return result
