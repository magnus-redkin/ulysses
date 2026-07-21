# app/config.py
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Загружаем .env до создания Settings
env_paths = [
    Path(__file__).parent.parent / ".env",           # ulysses-backend/.env
    Path(__file__).parent.parent.parent / ".env",    # Ulysses/.env
    Path.home() / "Ulysses" / ".env",                # ~/Ulysses/.env
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        print(f"📂 Загружен .env из: {env_path}")
        break

class Settings(BaseSettings):
    """
    Настройки приложения.
    Все значения по умолчанию берутся из .env или переменных окружения.
    """

    # База данных
    DB_USER: str = os.getenv("DB_USER", "ulysses_admin")
    DB_PASS: str = os.getenv("DB_PASS", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "ulysses_db")

    # Hiddify API
    # Извлекаем базовый URL из .env и гарантируем, что он превратится в полный путь к API пользователей
    HIDDIFY_API_URL: str = os.getenv("HIDDIFY_API_URL", "").strip()
    HIDDIFY_API_KEY: str = os.getenv("HIDDIFY_API_KEY", "").strip()

    # SMTP
    SMTP_HOST: str = os.getenv("SMTP_HOST", "127.0.0.1")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "support@ulysses.best")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "Ulysses Lab Support <support@ulysses.best>")

    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # URLs
    BACKEND_API_URL: str = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HEALTHCHECK_PORT: int = int(os.getenv("HEALTHCHECK_PORT", "8081"))
    ADMIN_IDS: str = os.getenv("ADMIN_IDS", "")

    ENOT_SHOP_ID: str = os.getenv("ENOT_SHOP_ID", "")
    ENOT_SECRET_KEY: str = os.getenv("ENOT_SECRET_KEY", "")
    ENOT_HOOK_KEY: str = os.getenv("ENOT_HOOK_KEY", "")

    AEZA_NUMBER: str = ""
    AEZA_API_KEY: str = ""

    DECOY_SITE: str = ""

    @property
    def DATABASE_URL(self) -> str:
        if not self.DB_PASS:
            raise ValueError(
                "DB_PASS не установлен! Проверьте .env файл.\n"
                f"Ожидаемый путь: ~/Ulysses/.env"
            )
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        extra = "allow"  # Разрешаем дополнительные переменные из .env
        case_sensitive = False

settings = Settings()

# Отладочный вывод
print(f"🔧 Конфигурация загружена:")
print(f"   DB: {settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
print(f"   DB_PASS: {'✅ установлен' if settings.DB_PASS else '❌ ОТСУТСТВУЕТ!'}")
print(f"   ENV: {settings.ENVIRONMENT}")
