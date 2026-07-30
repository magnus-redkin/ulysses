# ulysses-backend/app/services/aeza_client.py

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class AezaApiClient:
    """
    HTTP-клиент для взаимодействия с официальным API хостинга Aéza.
    Запрашивает актуальный статус виртуальных машин и их IP-адресов.
    """
    def __init__(self):
        # API Ключ берется из переменных окружения .env
        self.api_key = getattr(settings, "AEZA_API_KEY", "MOCK_TOKEN")
        self.base_url = "https: / / my.aeza.net / api / v1 / "
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

    async def fetch_vps_servers(self) -> list | None:
        """
        Запрашивает полный список активных услуг (VPS) из личного кабинета Aéza.
        """
        # Эндпоинт получения списка серверов
        target_url = f"{self.base_url}services / vps"
        logger.info(f"📡 [AEZA API] Запрос состояния серверов ➔ {target_url}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(target_url, headers=self.headers)

                if response.status_code == 200:
                    data = response.json()
                    # Возвращаем массив серверов из ответа API
                    return data.get("data", {}).get("items", [])

                logger.error(f"❌ Ошибка API Aéza: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Сетевой сбой при обращении к API Aéza: {e}")
        return None
