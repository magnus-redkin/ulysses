# app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Загружаем .env до создания Settings (приоритет поиска сохранён)
env_paths = [
    Path(__file__).parent.parent / ".env",           # ulysses-backend/.env
    Path(__file__).parent.parent.parent / ".env",    # Ulysses/.env
    Path.home() / "Ulysses" / ".env",                # ~/Ulysses/.env
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break


class Settings(BaseSettings):
    """
    Настройки приложения.
    Все значения по умолчанию берутся из .env или переменных окружения.
    """
    model_config = SettingsConfigDict(
        extra="allow",
        case_sensitive=False,
        env_file=".env"
    )

    # База данных
    DB_USER: str = "ulysses_admin"
    DB_PASS: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str = "ulysses_db"

    # Hiddify API
    HIDDIFY_API_URL: str = ""
    HIDDIFY_API_KEY: str = ""

    # SMTP
    SMTP_HOST: str = "127.0.0.1"
    SMTP_PORT: int = 587
    SMTP_USER: str = "support@ulysses.best"
    SMTP_PASS: str = ""
    SMTP_FROM: str = "Ulysses Lab Support <support@ulysses.best>"

    # Telegram
    BOT_TOKEN: str = ""

    # URLs
    BACKEND_API_URL: str = "http://127.0.0.1:8000"

    # Environment
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"
    HEALTHCHECK_PORT: int = 8081
    ADMIN_IDS: str = ""
    LOG_REQUESTS: bool = False
    INVOICE_DIRTY_HOURS: int = 24

    # Платёжные системы
    ENOT_SHOP_ID: str = ""
    ENOT_SECRET_KEY: str = ""
    ENOT_HOOK_KEY: str = ""

    AEZA_NUMBER: str = ""
    AEZA_API_KEY: str = ""

    PLATEGA_MERCHANT_ID: str = ""
    PLATEGA_API: str = ""

    # VPN / Reality
    DECOY_SITE: str = ""
    HOST_API_KEY: str = ""
    HIDDIFY_DOMAIN: str = "ulysses.best"

    @property
    def DATABASE_URL(self) -> str:
        if not self.DB_PASS:
            raise ValueError(
                "DB_PASS не установлен! Проверьте .env файл.\n"
                f"Ожидаемый путь: ~/Ulysses/.env"
            )
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
