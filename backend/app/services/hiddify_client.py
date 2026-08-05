# app/services/hiddify_client.py

import logging
import httpx
import asyncio # <-- Добавлено для фонового планирования
from app.config import settings

logger = logging.getLogger(__name__)

class HiddifyProvisioner:
    def __init__(self):
        base = settings.HIDDIFY_API_URL.rstrip("/")
        # ИСПРАВЛЕНО: Убрали слэш с конца, чтобы собирать URL безопасно
        self.base_url = f"{base}/api/v2/admin/user"
        self.admin_base_url = f"{base}/api/v2/admin/"

        self.headers = {
            "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.verify_ssl = False

    async def apply_config(self) -> bool:
        """Принудительно заставить HFM применить настройки ядра."""
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

    async def create_user(self, uuid: str, name: str, package_days: int = 3, usage_limit_gb: int = 500) -> bool:
        """Физически создает нового пользователя на ноде VPN."""
        # ИСПРАВЛЕНО: Безопасный URL без двойных слэшей
        target_url = f"{self.base_url}/"
        logger.info(f"📡 [HIDDIFY CLIENT] POST Запрос ➔ URL: '{target_url}'")

        payload = {
            "uuid": str(uuid),
            "name": str(name), # Гарантируем строку
            "usage_limit_GB": usage_limit_gb,
            "package_days": package_days,
            "mode": "no_reset",
            "enable": True
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.post(target_url, headers=self.headers, json=payload)
                if response.status_code in (200, 201):
                    logger.info(f"✅ [HIDDIFY CLIENT] Профиль {name} успешно создан на ноде VPN.")
                    # ИСПРАВЛЕНО: Вызываем тяжелый apply_config асинхронно в фоне, не блокируя поток запроса
                    # asyncio.create_task(self.apply_config())
                    return True
                elif response.status_code == 400 and "exists" in response.text.lower():
                    logger.info(f"ℹ️ [HIDDIFY CLIENT] Пользователь {name} уже существует на ноде VPN.")
                    return True
                logger.error(f"❌ Ошибка create_user: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            logger.error(f"❌ Сетевой сбой в create_user: {e}")
        return False

    async def enable_user(self, uuid_str: str) -> bool:
        """Активирует пользователя в панели Hiddify v2 через PATCH."""
        # ИСПРАВЛЕНО: Убран двойной слэш
        target_url = f"{self.base_url}/{str(uuid_str).strip().lower()}/"
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.patch(target_url, headers=self.headers, json={"enable": True})
                if response.status_code in (200, 204):
                    asyncio.create_task(self.apply_config()) # В фон
                    return True
        except Exception as e:
            logger.error(f"❌ Сбой enable_user: {e}")
        return False

    async def disable_user(self, uuid_str: str) -> bool:
        """Деактивирует пользователя в панели Hiddify v2 через PATCH."""
        # ИСПРАВЛЕНО: Убран двойной слэш
        target_url = f"{self.base_url}/{str(uuid_str).strip().lower()}/"
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.patch(target_url, headers=self.headers, json={"enable": False})
                if response.status_code in (200, 204):
                    asyncio.create_task(self.apply_config()) # В фон
                    return True
        except Exception as e:
            logger.error(f"❌ Сбой disable_user: {e}")
        return False

    async def delete_user(self, uuid: str) -> dict:
        """
        Физически удаляет пользователя на HFM API v2.
        Возвращает словарь со статусом выполнения.
        """
        clean_uuid = str(uuid).strip().lower()
        # ИСПРАВЛЕНО: Безопасная сборка URL без двойных слэшей (self.base_url не должен иметь слэша на конце)
        target_url = f"{self.base_url}/{clean_uuid}/"
        logger.info(f"🗑️ [HIDDIFY CLIENT] DELETE ➔ {target_url}")

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl) as client:
                response = await client.delete(target_url, headers=self.headers)

                if response.status_code in (200, 204):
                    logger.info(f"✅ Пользователь {clean_uuid} успешно удалён на HFM.")
                    # Сбрасываем конфиг ядра в фоне
                    asyncio.create_task(self.apply_config())
                    return {"success": True, "not_found": False}

                elif response.status_code == 404:
                    logger.warning(f"ℹ️ Пользователь {clean_uuid} не найден на HFM (404). Считаем удаленным.")
                    return {"success": True, "not_found": True}

                else:
                    logger.error(f"❌ Ошибка удаления {clean_uuid}: HTTP {response.status_code} - {response.text[:200]}")
                    return {"success": False, "not_found": False}

        except Exception as e:
            logger.error(f"❌ Сетевая ошибка при удалении {clean_uuid} из HFM: {e}")
            return {"success": False, "not_found": False}

    async def check_user_exists(self, uuid_str: str) -> bool:
        """
        Проверяет, существует ли профиль с данным UUID в панели Hiddify.
        Делает точечный запрос к эндпоинту пользователя, не нагружая память.
        """
        clean_uuid = str(uuid_str).strip().lower()
        # Формируем прямой URL к конкретному пользователю
        target_url = f"{self.base_url}/{clean_uuid}/"

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_ssl, follow_redirects=True) as client:
                response = await client.get(target_url, headers=self.headers)

                # Если панель вернула 200 OK, пользователь существует
                if response.status_code == 200:
                    return True

                # Если вернулся 500 (маскировка 404 для кривых UUID) или честный 404
                if response.status_code in [500, 404]:
                    logger.debug(f"Пользователь {clean_uuid} не найден в Hiddify (Статус {response.status_code})")
                    return False

        except Exception as e:
            logger.error(f"❌ Ошибка check_user_exists: {e}")

        return False
