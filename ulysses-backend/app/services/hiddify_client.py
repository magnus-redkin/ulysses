# ulysses-backend/app/services/hiddify_client.py

import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

class HiddifyProvisioner:
    """
    Изолированный HTTP-клиент для взаимодействия с API панели управления Hiddify Manager v2.
    """
    def __init__(self):
        # Базовый адрес до эндпоинта управления пользователями
        base = settings.HIDDIFY_API_URL.rstrip("/")
        self.base_url = f"{base}/api/v2/admin/user/"

        # Общий корень API для вызова служебных команд панели (применение конфигов)
        self.admin_base_url = f"{base}/api/v2/admin/"

        self.headers = {
            "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.verify_ssl = False

    async def apply_config(self) -> bool:
        """Принудительно заставить HFM применить настройки ядра и обновить кэш Xray."""
        target_url = f"{self.admin_base_url}config/action/"
        logger.info(f"🔄 [HIDDIFY CLIENT] Применение конфигурации ядра... POST ➔ '{target_url}'")
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl) as client:
                response = await client.post(target_url, headers=self.headers, json={"action": "apply"})
                if response.status_code in (200, 201):
                    logger.info("✅ [HIDDIFY CLIENT] Конфигурация ядра успешно применена нодой.")
                    return True
                logger.error(f"❌ Ошибка apply_config: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Сетевой сбой при apply_config: {e}")
        return False

    async def check_user_exists(self, uuid_str: str) -> bool:
        """Проверяет, существует ли профиль с данным UUID в панели Hiddify."""
        clean_uuid = str(uuid_str).strip().lower()
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.get(self.base_url, headers=self.headers)
                if response.status_code == 200:
                    users = response.json()
                    return any(str(u.get("uuid", "")).lower() == clean_uuid for u in users)
        except Exception as e:
            logger.error(f"❌ Ошибка check_user_exists: {e}")
        return False

    async def fetch_all_users(self) -> list | None:
        """Получает полный список пользователей из панели Hiddify."""
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.get(self.base_url, headers=self.headers)
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"❌ Ошибка fetch_all_users: {e}")
        return None

    async def create_user(self, uuid: str, name: str) -> bool:
        """Физически создает нового пользователя на ноде VPN."""
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
                    # Принудительно коммитим кэш, чтобы ядро Xray на Сердце мгновенно увидело юзера
                    await self.apply_config()
                    return True
                logger.error(f"❌ Ошибка create_user: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Сетевой сбой в create_user: {e}")
        return False

    async def enable_user(self, uuid_str: str) -> bool:
        """Активирует пользователя в панели Hiddify v2 через PATCH."""
        clean_uuid = str(uuid_str).strip().lower()
        target_url = f"{self.base_url}{clean_uuid}/"
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.patch(target_url, headers=self.headers, json={"enable": True})
                if response.status_code in (200, 204):
                    await self.apply_config()
                    return True
        except Exception as e:
            logger.error(f"❌ Сбой enable_user: {e}")
        return False

    async def disable_user(self, uuid_str: str) -> bool:
        """Деактивирует пользователя в панели Hiddify v2 через PATCH."""
        clean_uuid = str(uuid_str).strip().lower()
        target_url = f"{self.base_url}{clean_uuid}/"
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.patch(target_url, headers=self.headers, json={"enable": False})
                if response.status_code in (200, 204):
                    await self.apply_config()
                    return True
        except Exception as e:
            logger.error(f"❌ Сбой disable_user: {e}")
        return False

    async def delete_user(self, uuid: str) -> bool:
        """Физически удалить пользователя из ядра Hiddify Manager v2 через DELETE."""
        clean_uuid = str(uuid).strip().lower()
        # 🟢 ИСПРАВЛЕНО: Чистый ровный эндпоинт без дублирования путей
        target_url = f"{self.base_url}{clean_uuid}/"
        logger.info(f"🗑️ [HIDDIFY CLIENT] DELETE Запрос ➔ URL: '{target_url}'")

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                # 🟢 ИСПРАВЛЕНО: Используем готовый self.headers без AttributeError
                response = await client.delete(target_url, headers=self.headers)

                if response.status_code == 200 or response.status_code == 204:
                    logger.info(f"✅ [HIDDIFY CLIENT] Пользователь {clean_uuid} успешно стерт из HFM.")
                    # Синхронно заставляем Xray обновить таблицы маршрутов
                    await self.apply_config()
                    return True

                logger.error(f"❌ [HIDDIFY API] Ошибка удаления {clean_uuid}: Статус {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ [HIDDIFY API] Транспортный сбой при DELETE {clean_uuid}: {e}")
            return False
