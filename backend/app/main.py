# ulysses-backend/app/main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

import asyncio
from contextlib import asynccontextmanager

import logging
logging.getLogger("app.routers.billing").setLevel(logging.INFO)
logging.getLogger("app.services.activation_manager").setLevel(logging.INFO)
logging.getLogger("app.email_service").setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# Импорт новых изолированных модулей-роутеров
from app.routers.bot import router as bot_router
from app.routers.user import router as user_router
from app.routers.billing import router as billing_router

from app.routers.subscription import router as subscription_router

from app.routers.sub_render import router as sub_render_router
from app.routers import admin

from app.services.subscription_monitor import check_expiring_subscriptions

# Создаем lifespan обработчик событий старта/остановки сервера (без монитора)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Проверять раз в 24 часа
    asyncio.create_task(_run_daily_subscription_check())
    yield

async def _run_daily_subscription_check():
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            await check_expiring_subscriptions()
        except Exception as e:
            logger.error(f"Subscription monitor error: {e}")


app = FastAPI(title="Ulysses VPN Backend API", version="1.0.0", lifespan=lifespan)

@app.middleware("http")
async def log_all_requests(request: Request, call_next):
    # Логируем только в dev-окружении или если явно включено
    if settings.ENVIRONMENT == "development" or getattr(settings, "LOG_REQUESTS", False):
        logger.info(f"🔥 INCOMING: {request.method} {request.url} from {request.client.host}")
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ulysses.best",
        "https://web.telegram.org",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Регистрация роутеров в приложении
app.include_router(bot_router)
app.include_router(user_router)
app.include_router(billing_router)
app.include_router(subscription_router)

app.include_router(sub_render_router)
app.include_router(admin.router)

@app.get("/health")
async def health_check():
    """Базовый эндпоинт проверки доступности самого бэкенда"""
    return {"status": "ok", "service": "backend"}
