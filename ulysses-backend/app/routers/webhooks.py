# ulysses-backend/app/routers/webhooks.py

from fastapi import APIRouter, Request, Response
from app.private.platega_service import PlategaWebhookProcessor

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.post("/platega-callback")
async def platega_webhook_handler(request: Request):
    """
    Открытый эндпоинт-маршрутизатор для Platega.io.
    Вся логика полностью делегирована в изолированный защищенный контур.
    """
    # Считываем сырые сетевые данные
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")
    headers = dict(request.headers)

    # Передаем выполнение в private сектор
    processor = PlategaWebhookProcessor()
    return await processor.process_incoming_callback(headers=headers, body_str=body_str)
