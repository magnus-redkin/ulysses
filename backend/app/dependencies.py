import secrets  # <-- ДОБАВЛЕНО для защиты от атак по времени
from fastapi import Header, HTTPException
from app.config import settings

async def verify_api_key(x_api_key: str = Header(None)):
    # 1. Защита от отсутствия заголовка
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header is missing")

    # 2. ИСПРАВЛЕНО: Безопасное сравнение строк за постоянное время (Constant-time comparison)
    # Теперь злоумышленник не сможет подобрать ключ по задержкам ответа сервера
    is_valid = secrets.compare_digest(x_api_key, settings.HOST_API_KEY)

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    return x_api_key
