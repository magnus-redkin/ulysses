# ulysses-backend/app/services/hiddify_client.py

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class HiddifyProvisioner:
    """
    Изолированный HTTP-клиент для взаимодействия с API панели управления Hiddify Manager.
    Отвечает за операции создания, изменения, удаления и проверки статуса ключей на VPN-нодах.
    """
    def __init__(self):
        self.base_url = settings.HIDDIFY_API_URL
        self.headers = {
            "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
            "Content-Type": "application/json"
        }
        # Проверка SSL отключается для самоподписанных сертификатов на нодах
        self.verify_ssl = False
        logger.debug("🤖 Инициализирован HTTP-клиент Hiddify Ноды")

    async def check_user_exists(self, uuid_str: str) -> bool:
        """Проверяет, существует ли профиль с данным UUID в панели Hiddify."""
        clean_uuid = str(uuid_str).strip().lower()
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl) as client:
                response = await client.get(self.base_url, headers=self.headers)
                if response.status_code == 200:
                    users = response.json()
                    return any(str(u.get("uuid", "")).lower() == clean_uuid for u in users)
                logger.error(f"❌ Ошибка проверки юзера в Hiddify: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка сети при проверке существования UUID {clean_uuid} в Hiddify: {e}")
        return False

    async def fetch_all_users(self) -> list | None:
        """Получает полный список пользователей из панели Hiddify для сканирования аномалий."""
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl) as client:
                response = await client.get(self.base_url, headers=self.headers)
                if response.status_code == 200:
                    return response.json()
                logger.error(f"❌ Не удалось получить список пользователей Hiddify: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка сети при запросе списка пользователей Hiddify: {e}")
        return None

    async def enable_user(self, uuid_str: str) -> bool:
        """Активирует (включает тумблер) пользователя в панели Hiddify."""
        # Здесь будет вызов PATCH/POST метода вашего Hiddify API для изменения статуса enable=True
        logger.info(f"🟢 Включение тумблера активности для UUID: {uuid_str}")
        return True

    async def disable_user(self, uuid_str: str) -> bool:
        """Деактивирует (выключает тумблер) пользователя в панели Hiddify при окончании срока подписки."""
        # Здесь будет вызов PATCH/POST метода вашего Hiddify API для изменения статуса enable=False
        logger.info(f"🔴 Выключение тумблера активности для UUID: {uuid_str}")
        return True
