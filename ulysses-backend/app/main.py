# ulysses-backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

import asyncio
from contextlib import asynccontextmanager
from app.services.monitor import start_monitor_daemon


# Импорт новых изолированных модулей-роутеров
from app.routers.bot import router as bot_router
from app.routers.user import router as user_router
from app.routers.billing import router as billing_router
from app.routers.admin import router as admin_router
from app.routers.test_billing import router as test_billing_router
from app.routers.sub_render import router as sub_render_router
from app.routers.webhooks import router as webhooks_router


# Создаем lifespan обработчик событий старта/остановки сервера
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🧠 Запускаем демона мониторинга асинхронной фоновой задачей при старте сервера
    monitor_task = asyncio.create_task(start_monitor_daemon())

    yield  # Здесь бэкенд крутится и принимает запросы

    # При остановке сервера uvicorn аккуратно гасим фоновый таск
    monitor_task.cancel()


app = FastAPI(title="Ulysses VPN Backend API", version="1.0.0", lifespan=lifespan)

# Настройки CORS для работы фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация роутеров в приложении
app.include_router(bot_router)
app.include_router(user_router)
app.include_router(billing_router)
app.include_router(admin_router)
# app.include_router(test_billing_router)
app.include_router(sub_render_router)  # 🟢 Исправлено: Передали верное имя переменной
app.include_router(webhooks_router)

@app.get("/health")
async def health_check():
    """Базовый эндпоинт проверки доступности самого бэкенда"""
    return {"status": "ok", "service": "backend"}
