# ulysses-backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# Импорт новых изолированных модулей-роутеров
from app.routers.bot import router as bot_router
from app.routers.user import router as user_router
from app.routers.billing import router as billing_router
from app.routers.admin import router as admin_router
from app.routers.test_billing import router as test_billing_router
from app.routers.sub_render import router as sub_render_router  # 🟢 Исправлено: Добавили импорт

app = FastAPI(title="Ulysses VPN Backend API", version="1.0.0")

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
app.include_router(test_billing_router)
app.include_router(sub_render_router)  # 🟢 Исправлено: Передали верное имя переменной

@app.get("/health")
async def health_check():
    """Базовый эндпоинт проверки доступности самого бэкенда"""
    return {"status": "ok", "service": "backend"}
