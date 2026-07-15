# Создаем временный скрипт для проверки
# tests/debug_config.py
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings

print("=== Проверка загрузки конфигурации ===")
print(f"DB_USER: {settings.DB_USER}")
print(f"DB_PASS: {'***' if settings.DB_PASS else 'EMPTY!'}")
print(f"DB_HOST: {settings.DB_HOST}")
print(f"DB_NAME: {settings.DB_NAME}")
print(f"DATABASE_URL: {settings.DATABASE_URL.replace(settings.DB_PASS, '***') if settings.DB_PASS else settings.DATABASE_URL}")
print(f"ENVIRONMENT: {getattr(settings, 'ENVIRONMENT', 'NOT SET')}")
