# ulysses-bot/config.py (новый файл)
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
from dotenv import load_dotenv

@dataclass
class BotConfig:
    """Конфигурация бота"""
    bot_token: str
    bot_username: str
    database_url: str
    hiddify_base_url: str
    hiddify_api_key: str
    webhook_host: str
    webhook_path: str
    webhook_port: int
    environment: str
    log_level: str

    @classmethod
    def from_env(cls) -> 'BotConfig':
        """Загрузка конфигурации из переменных окружения"""

        # Загружаем .env файлы
        project_root = Path(__file__).parent.parent
        env_file = project_root / '.env'
        if env_file.exists():
            load_dotenv(env_file)

        # Создаем конфиг
        config = cls(
            bot_token=os.getenv("BOT_TOKEN", ""),
            bot_username=os.getenv("BOT_USERNAME", ""),
            database_url=os.getenv("DATABASE_URL", ""),
            hiddify_base_url=os.getenv("HIDDIFY_BASE_URL", ""),
            hiddify_api_key=os.getenv("HIDDIFY_API_KEY", ""),
            webhook_host=os.getenv("WEBHOOK_HOST", "http://localhost"),
            webhook_path=os.getenv("WEBHOOK_PATH", "/tg-webhook"),
            webhook_port=int(os.getenv("WEBHOOK_PORT", "8080")),
            environment=os.getenv("ENVIRONMENT", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

        # Валидация
        config.validate()
        return config

    def validate(self):
        """Проверка обязательных полей"""
        required = {
            'bot_token': self.bot_token,
            'database_url': self.database_url,
            'hiddify_api_key': self.hiddify_api_key,
        }

        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Отсутствуют обязательные настройки: {missing}")

# Использование в main.py:
# from config import BotConfig
# config = BotConfig.from_env()
# bot = Bot(token=config.bot_token)
