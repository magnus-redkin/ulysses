# ulysses-backend/app/services/hiddify_client.py

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class HiddifyProvisioner:
    """
    Изолированный HTTP-клиент для взаимодействия с API панели управления Hiddify Manager.
    Формирует целевой путь /admin/api/v1/user/ на основе базового URL из настроек.
    """
    def __init__(self):
        # Гарантируем чистую склейку базового адреса с системным эндпоинтом
        base = settings.HIDDIFY_API_URL.rstrip("/")
        self.base_url = f"{base}/api/v2/admin/user/"

        self.headers = {
            "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
            "Content-Type": "application/json"
        }
        self.verify_ssl = False

    async def check_user_exists(self, uuid_str: str) -> bool:
        """Проверяет, существует ли профиль с данным UUID в панели Hiddify."""
        clean_uuid = str(uuid_str).strip().lower()
        logger.info(f"📡 [HIDDIFY CLIENT] GET Запрос ➔ URL: '{self.base_url}'")
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.get(self.base_url, headers=self.headers)
                if response.status_code == 200:
                    users = response.json()
                    return any(str(u.get("uuid", "")).lower() == clean_uuid for u in users)
                logger.error(f"❌ Ошибка check_user_exists: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Ошибка сети в check_user_exists: {e}")
        return False

    async def fetch_all_users(self) -> list | None:
        """Получает полный список пользователей из панели Hiddify."""
        logger.info(f"📡 [HIDDIFY CLIENT] GET Запрос ➔ URL: '{self.base_url}'")
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.get(self.base_url, headers=self.headers)
                if response.status_code == 200:
                    return response.json()
                logger.error(f"❌ Ошибка fetch_all_users: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Ошибка сети в fetch_all_users: {e}")
        return None

    async def create_user(self, uuid: str, name: str) -> bool:
        """Физически создает нового пользователя на ноде VPN."""
        logger.info(f"📡 [HIDDIFY CLIENT] POST Запрос ➔ URL: '{self.base_url}'")
        payload = {
            "uuid": str(uuid),
            "name": name,
            "usage_limit_GB": 0,
            "package_days": 30,
            "mode": "no_reset",
            "enable": True
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.post(self.base_url, headers=self.headers, json=payload)
                if response.status_code in (200, 201):
                    logger.info(f"✅ [HIDDIFY CLIENT] Профиль {name} успешно создан на ноде VPN.")
                    return True
                logger.error(f"❌ Ошибка create_user: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Сетевой сбой в create_user: {e}")
        return False
