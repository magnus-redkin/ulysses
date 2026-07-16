# ulysses-backend/app/provisioning_service.py

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import httpx
import ssl

import os
from app.database import AsyncSessionLocal
from app.bot_messages import get_message  # Наш рабочий модуль локализации

from fastapi import BackgroundTasks, HTTPException

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


class HiddifyProvisioner:
    """
    Сервис для создания и управления пользователями в Hiddify.

    Обеспечивает:
    - Создание новых VPN-пользователей
    - Включение/отключение существующих
    - Проверку статуса пользователей
    - Управление лимитами трафика
    - Получение статистики использования
    """

    def __init__(self):
        self.headers = {
            "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
            "Content-Type": "application/json"
        }

        # Загружаем тарифы ОДИН раз при старте
        self.tariffs = self._load_tariffs()
        if not self.tariffs:
            logger.critical("❌ КРИТИЧЕСКИ: Не удалось загрузить тарифы! Сервис будет использовать значения по умолчанию")

        # Hiddify использует самоподписанный сертификат
        # Отключаем проверку SSL для работы с API
        logger.warning("⚠️ Проверка SSL отключена для Hiddify API (самоподписанный сертификат)")

        # Базовые настройки HTTP клиента
        self.client_config = {
            "timeout": 15.0,
            "verify": False,  # Самоподписанный сертификат на Hiddify
            "headers": self.headers
        }


    def _load_tariffs(self) -> Dict[str, Dict[str, Any]]:
        """
        Загрузка конфигурации тарифов из tariffs.json.
        Выполняется ОДИН раз при инициализации.

        Returns:
            Dict: Конфигурация тарифов или пустой словарь при ошибке
        """
        try:
            tariffs_path = Path(__file__).parent / "tariffs.json"

            if not tariffs_path.exists():
                logger.error(f"❌ Файл тарифов не найден: {tariffs_path}")
                return {}

            with open(tariffs_path, "r", encoding="utf-8") as f:
                tariffs = json.load(f)

            logger.info(f"✅ Загружено {len(tariffs)} тарифов из tariffs.json")

            # Логируем загруженные тарифы для отладки
            for slug, config in tariffs.items():
                logger.debug(
                    f"   📋 {slug}: {config.get('name_ru', slug)} - "
                    f"{config.get('traffic_gb', 0)}GB / {config.get('days', 0)}дней"
                )

            return tariffs

        except json.JSONDecodeError as e:
            logger.critical(f"❌ Ошибка парсинга tariffs.json: {e}")
            return {}
        except Exception as e:
            logger.critical(f"❌ Ошибка загрузки тарифов: {e}")
            return {}

    def _get_tariff_config(self, tariff_slug: str) -> Dict[str, Any]:
        """
        Получение конфигурации конкретного тарифа.

        Args:
            tariff_slug: Слаг тарифа

        Returns:
            Dict: Конфигурация тарифа или значения по умолчанию
        """
        if tariff_slug in self.tariffs:
            return self.tariffs[tariff_slug]

        # Если тариф не найден, используем значения по умолчанию
        logger.warning(f"⚠️ Тариф '{tariff_slug}' не найден в tariffs.json, использую значения по умолчанию")

        # Маппинг для обратной совместимости со старыми тарифами
        legacy_defaults = {
            "premium": {"traffic_gb": 100.0, "days": 30},
            "standard": {"traffic_gb": 50.0, "days": 30},
        }

        if tariff_slug in legacy_defaults:
            return legacy_defaults[tariff_slug]

        # Совсем неизвестный тариф - минимальные безопасные значения
        logger.error(f"❌ Неизвестный тариф '{tariff_slug}', использую минимальные значения")
        return {"traffic_gb": 10.0, "days": 7}

    async def _make_request(
        self,
        method: str,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Выполняет HTTP запрос к Hiddify API с автоматическими повторными попытками.

        Args:
            method: HTTP метод (GET, POST, PATCH, DELETE)
            url: Полный URL запроса
            json_data: Данные для отправки (для POST/PATCH)
            max_retries: Количество повторных попыток

        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: (успех, данные ответа, ошибка)
        """
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(**self.client_config, follow_redirects=True) as client:
                    if method == "GET":
                        response = await client.get(url)
                    elif method == "POST":
                        response = await client.post(url, json=json_data)
                    elif method == "PATCH":
                        response = await client.patch(url, json=json_data)
                    elif method == "DELETE":
                        response = await client.delete(url)
                    else:
                        return False, None, f"Unsupported HTTP method: {method}"

                    # Успешные статусы
                    if response.status_code in (200, 201):
                        try:
                            data = response.json()
                            return True, data, None
                        except Exception:
                            return True, None, None

                    # Пользователь не найден - не повторяем
                    elif response.status_code == 404:
                        return False, None, "Not found"

                    # Конфликт (уже существует) - не ошибка
                    elif response.status_code == 409:
                        return True, None, "Already exists"

                    # Другие ошибки
                    else:
                        error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                        logger.warning(f"⚠️ Попытка {attempt}/{max_retries}: {error_msg}")

                        if attempt < max_retries:
                            delay = 2 ** (attempt - 1)  # Экспоненциальная задержка: 1, 2, 4
                            await asyncio.sleep(delay)
                        else:
                            return False, None, error_msg

            except httpx.TimeoutException:
                error_msg = f"Timeout after {self.client_config['timeout']}s"
                logger.error(f"⏱ {error_msg} (attempt {attempt}/{max_retries})")

                if attempt < max_retries:
                    await asyncio.sleep(2 * attempt)
                else:
                    return False, None, error_msg

            except httpx.ConnectError as e:
                error_msg = f"Connection failed: {str(e)[:200]}"
                logger.error(f"🔌 {error_msg}")

                if attempt < max_retries:
                    await asyncio.sleep(2 * attempt)
                else:
                    return False, None, error_msg

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)[:200]}"
                logger.error(f"❌ {error_msg}")

                if attempt < max_retries:
                    await asyncio.sleep(2 * attempt)
                else:
                    return False, None, error_msg

        return False, None, "Max retries exceeded"

    async def create_user(
        self,
        user_uuid: str,
        email: str,
        tariff_slug: str,
        max_retries: int = 3
    ) -> Tuple[bool, Optional[str]]:
        """
        Создание нового пользователя в Hiddify панели.
        Использует конфигурацию из tariffs.json.

        Args:
            user_uuid: Уникальный идентификатор пользователя
            email: Email или идентификатор пользователя
            tariff_slug: Слаг тарифа для определения лимитов
            max_retries: Максимальное количество попыток

        Returns:
            Tuple[bool, Optional[str]]: (успех, сообщение об ошибке)
        """
        # Получаем конфигурацию тарифа из tariffs.json
        tariff_config = self._get_tariff_config(tariff_slug)

        traffic_gb = float(tariff_config.get("traffic_gb", 50.0))
        days = int(tariff_config.get("days", 30))
        tariff_name = tariff_config.get("name_ru", tariff_slug)

        payload = {
            "uuid": user_uuid,
            "name": email,
            "usage_limit_GB": traffic_gb,
            "package_days": days,
            "enable": True,
            "comment": f"Ulysses Billing | {tariff_slug} | {tariff_name}"
        }

        logger.info(
            f"🔄 Создание пользователя в Hiddify: "
            f"UUID={user_uuid[:8]}..., тариф={tariff_slug} ({tariff_name}), "
            f"лимит={traffic_gb}GB, дней={days}"
        )

        success, data, error = await self._make_request(
            method="POST",
            url=settings.HIDDIFY_API_URL,
            json_data=payload,
            max_retries=max_retries
        )

        if success:
            logger.info(f"✅ Пользователь {user_uuid[:8]}... создан в Hiddify с тарифом {tariff_slug}")
            return True, None
        else:
            logger.error(f"❌ Не удалось создать пользователя {user_uuid[:8]}...: {error}")
            return False, error

    async def get_user_by_uuid(self, user_uuid: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Поиск пользователя в Hiddify по UUID.

        Args:
            user_uuid: UUID пользователя для поиска

        Returns:
            Tuple[bool, Optional[Dict]]: (найден, данные пользователя)
        """
        logger.debug(f"🔍 Поиск пользователя {user_uuid[:8]}... в Hiddify")

        # Получаем всех пользователей и ищем нужного
        success, users_list, error = await self._make_request(
            method="GET",
            url=settings.HIDDIFY_API_URL
        )

        if not success or not users_list:
            return False, None

        # Ищем пользователя по UUID
        target_uuid = str(user_uuid).lower()
        for user in users_list:
            if isinstance(user, dict) and str(user.get("uuid", "")).lower() == target_uuid:
                logger.debug(f"✅ Пользователь {user_uuid[:8]}... найден в Hiddify")
                return True, user

        logger.debug(f"❌ Пользователь {user_uuid[:8]}... не найден в Hiddify")
        return False, None

    async def check_user_exists(self, user_uuid: str) -> bool:
        """
        Проверка существования пользователя в Hiddify.

        Args:
            user_uuid: UUID пользователя

        Returns:
            bool: True если пользователь существует
        """
        exists, _ = await self.get_user_by_uuid(user_uuid)
        return exists

    async def get_user_stats(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Получение статистики использования трафика пользователем.

        Args:
            user_uuid: UUID пользователя

        Returns:
            Optional[Dict]: Статистика или None если пользователь не найден
        """
        found, user_data = await self.get_user_by_uuid(user_uuid)

        if not found or not user_data:
            return None

        usage = float(user_data.get("current_usage_GB", 0))
        limit = float(user_data.get("usage_limit_GB", 0))
        enabled = bool(user_data.get("enable", False))

        return {
            "used_gb": round(usage, 2),
            "total_gb": round(limit, 2),
            "remaining_gb": round(max(0, limit - usage), 2),
            "percent": round((usage / limit * 100) if limit > 0 else 0, 1),
            "is_enabled": enabled,
            "last_connected": user_data.get("last_connected"),
            "created_at": user_data.get("created_at")
        }

    async def enable_user(self, uuid: str) -> bool:
        """
        Включение пользователя в Hiddify (активация VPN).

        Args:
            uuid: UUID пользователя

        Returns:
            bool: True если успешно
        """
        logger.info(f"🔓 Включение пользователя {uuid[:8]}...")

        # Сначала ищем ID пользователя в Hiddify
        found, user_data = await self.get_user_by_uuid(uuid)

        if not found or not user_data:
            logger.error(f"❌ Не могу включить: пользователь {uuid[:8]}... не найден")
            return False

        user_id = user_data.get("id")
        if not user_id:
            logger.error(f"❌ У пользователя {uuid[:8]}... нет ID в Hiddify")
            return False

        # Включаем пользователя
        success, _, error = await self._make_request(
            method="PATCH",
            url=f"{settings.HIDDIFY_API_URL}{user_id}/",
            json_data={"enable": True}
        )

        if success:
            logger.info(f"✅ Пользователь {uuid[:8]}... включен")
            return True
        else:
            logger.error(f"❌ Ошибка включения {uuid[:8]}...: {error}")
            return False

    async def disable_user(self, uuid: str) -> bool:
        """
        Отключение пользователя в Hiddify (деактивация VPN).

        Args:
            uuid: UUID пользователя

        Returns:
            bool: True если успешно
        """
        logger.info(f"🔒 Отключение пользователя {uuid[:8]}...")

        # Ищем ID пользователя в Hiddify
        found, user_data = await self.get_user_by_uuid(uuid)

        if not found or not user_data:
            logger.error(f"❌ Не могу отключить: пользователь {uuid[:8]}... не найден")
            return False

        user_id = user_data.get("id")
        if not user_id:
            logger.error(f"❌ У пользователя {uuid[:8]}... нет ID в Hiddify")
            return False

        # Отключаем пользователя
        success, _, error = await self._make_request(
            method="PATCH",
            url=f"{settings.HIDDIFY_API_URL}{user_id}/",
            json_data={"enable": False}
        )

        if success:
            logger.info(f"✅ Пользователь {uuid[:8]}... отключен")
            return True
        else:
            logger.error(f"❌ Ошибка отключения {uuid[:8]}...: {error}")
            return False

    async def update_user_limits(
        self,
        uuid: str,
        tariff_slug: Optional[str] = None,
        traffic_gb: Optional[float] = None,
        days: Optional[int] = None
    ) -> bool:
        """
        Обновление лимитов пользователя в Hiddify.
        Можно указать либо tariff_slug (взять из tariffs.json), либо конкретные значения.

        Args:
            uuid: UUID пользователя
            tariff_slug: Слаг тарифа (если указан, traffic_gb и days берутся из tariffs.json)
            traffic_gb: Новый лимит трафика в GB (если указан явно)
            days: Новое количество дней (если указано явно)

        Returns:
            bool: True если успешно
        """
        logger.info(f"📊 Обновление лимитов для {uuid[:8]}...")

        # Если указан тариф, берем значения из tariffs.json
        if tariff_slug:
            tariff_config = self._get_tariff_config(tariff_slug)
            if traffic_gb is None:
                traffic_gb = float(tariff_config.get("traffic_gb", 50.0))
            if days is None:
                days = int(tariff_config.get("days", 30))
            logger.info(f"   Использую тариф '{tariff_slug}': {traffic_gb}GB / {days}дней")

        found, user_data = await self.get_user_by_uuid(uuid)

        if not found or not user_data:
            logger.error(f"❌ Пользователь {uuid[:8]}... не найден для обновления")
            return False

        user_id = user_data.get("id")
        if not user_id:
            return False

        update_data = {}
        if traffic_gb is not None:
            update_data["usage_limit_GB"] = traffic_gb
        if days is not None:
            update_data["package_days"] = days

        if not update_data:
            logger.info("ℹ️ Нечего обновлять")
            return True

        success, _, error = await self._make_request(
            method="PATCH",
            url=f"{settings.HIDDIFY_API_URL}{user_id}/",
            json_data=update_data
        )

        if success:
            logger.info(f"✅ Лимиты обновлены для {uuid[:8]}...")
            return True
        else:
            logger.error(f"❌ Ошибка обновления лимитов: {error}")
            return False

    async def delete_user(self, uuid: str) -> bool:
        """
        Удаление пользователя из Hiddify.

        Args:
            uuid: UUID пользователя

        Returns:
            bool: True если успешно
        """
        logger.info(f"🗑 Удаление пользователя {uuid[:8]}... из Hiddify")

        found, user_data = await self.get_user_by_uuid(uuid)

        if not found:
            logger.warning(f"⚠️ Пользователь {uuid[:8]}... уже не существует")
            return True  # Уже удален

        user_id = user_data.get("id")
        if not user_id:
            return False

        # success, _, error = await self._make_request(
        #     method="DELETE",
        #     url=f"{settings.HIDDIFY_API_URL}{user_id}/"
        # )

        target_delete_url = f"{settings.HIDDIFY_API_URL}{user_id}/"
        print(f"\n[🔍 ОТЛАДКА URL] Метод DELETE отправляет запрос на адрес: {target_delete_url}")

        success, _, error = await self._make_request(
            method="DELETE",
            url=target_delete_url
        )

        if success:
            logger.info(f"✅ Пользователь {uuid[:8]}... удален из Hiddify")
            return True
        else:
            logger.error(f"❌ Ошибка удаления: {error}")
            return False

    async def get_all_users(self) -> Tuple[bool, list, Optional[str]]:
        """
        Получение списка всех пользователей из Hiddify.

        Returns:
            Tuple[bool, list, Optional[str]]: (успех, список пользователей, ошибка)
        """
        logger.info("📋 Получение списка всех пользователей Hiddify...")

        success, users_list, error = await self._make_request(
            method="GET",
            url=settings.HIDDIFY_API_URL
        )

        if success:
            users_count = len(users_list) if users_list else 0
            logger.info(f"✅ Получено {users_count} пользователей из Hiddify")
            return True, users_list or [], None
        else:
            logger.error(f"❌ Ошибка получения списка: {error}")
            return False, [], error

    async def sync_user_status(self, uuid: str, should_be_active: bool) -> bool:
        """
        Синхронизация статуса пользователя с желаемым состоянием.

        Args:
            uuid: UUID пользователя
            should_be_active: True если должен быть включен, False если выключен

        Returns:
            bool: True если статус синхронизирован
        """
        found, user_data = await self.get_user_by_uuid(uuid)

        if not found:
            logger.warning(f"⚠️ Пользователь {uuid[:8]}... не найден для синхронизации")
            return False

        current_status = user_data.get("enable", False)

        if current_status == should_be_active:
            logger.info(f"ℹ️ Статус {uuid[:8]}... уже синхронизирован")
            return True

        if should_be_active:
            return await self.enable_user(uuid)
        else:
            return await self.disable_user(uuid)

    async def bulk_enable_users(self, uuids: list[str]) -> Dict[str, bool]:
        """
        Массовое включение пользователей.

        Args:
            uuids: Список UUID пользователей

        Returns:
            Dict[str, bool]: Результаты по каждому UUID
        """
        results = {}
        for uuid in uuids:
            results[uuid] = await self.enable_user(uuid)
            await asyncio.sleep(0.1)  # Небольшая задержка между запросами
        return results

    async def bulk_disable_users(self, uuids: list[str]) -> Dict[str, bool]:
        """
        Массовое отключение пользователей.

        Args:
            uuids: Список UUID пользователей

        Returns:
            Dict[str, bool]: Результаты по каждому UUID
        """
        results = {}
        for uuid in uuids:
            results[uuid] = await self.disable_user(uuid)
            await asyncio.sleep(0.1)
        return results


class ProvisioningManager:
    """
    Менеджер provisioning процесса.
    Отвечает за координацию между БД и Hiddify API.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.provisioner = HiddifyProvisioner()

    async def provision_subscription(self, subscription_id: int) -> bool:
        """
        Активация подписки в Hiddify.

        Args:
            subscription_id: ID подписки

        Returns:
            bool: True если успешно активирована
        """
        # 1. Получаем данные подписки и пользователя
        result = await self.db.execute(text("""
            SELECT
                s.id,
                u.hiddify_uuid,
                s.tariff_slug,
                s.status,
                u.email,
                u.id AS user_id,
                u.tg_user_id
            FROM subscriptions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = :sub_id
        """), {"sub_id": subscription_id})

        sub_data = result.fetchone()
        if not sub_data:
            logger.error(f"Подписка {subscription_id} не найдена")
            return False

        sub_id, uuid, tariff, status, email, user_id, user_tg_id = sub_data  #

        # 2. Проверяем статус подписки
        if status not in ["provisioning", "pending_payment"]:
            logger.warning(f"Подписка {sub_id} в статусе {status}, пропускаем")
            return False

        # 3. Если у пользователя еще нет UUID, генерируем его
        if not uuid:
            import uuid as uuid_lib
            new_uuid = uuid_lib.uuid4()
            await self.db.execute(text("""
                UPDATE users
                SET hiddify_uuid = :uuid
                WHERE id = :user_id
            """), {"uuid": new_uuid, "user_id": user_id})
            await self.db.commit()
            uuid = new_uuid
            logger.info(f"✨ Сгенерирован новый hiddify_uuid для user_id {user_id}: {uuid}")

        # 4. Проверяем, существует ли пользователь в Hiddify
        exists = await self.provisioner.check_user_exists(str(uuid))

        if exists:
            # Пользователь уже есть в Hiddify — это продление или смена тарифа
            # Вызываем умное обновление лимитов со сбросом счетчиков трафика и даты старта пакета!
            update_success = await self.provisioner.update_user_limits(
                uuid=str(uuid),
                tariff_slug=tariff,
                reset_usage=True
            )

            if update_success:
                await self._activate_subscription(sub_id)
                logger.info(f"✅ Подписка {sub_id} успешно продлена в Hiddify со сбросом лимитов")
                return True
            else:
                logger.error(f"❌ Не удалось обновить лимиты при продлении подписки {sub_id}")
                await self._update_provisioning_attempt(sub_id, "Hiddify limits update failed on renewal")
                return False

        # 5. Создаем пользователя в Hiddify (первая покупка)
        if email and not email.endswith("@ulysses.internal"):
            display_name = email
        else:
            display_name = str(user_tg_id) if user_tg_id else f"tg_{user_id}"

        success, error = await self.provisioner.create_user(
            user_uuid=str(uuid),
            email=display_name,
            tariff_slug=tariff
        )

        if success:
            await self._activate_subscription(sub_id)
            logger.info(f"✅ Подписка {sub_id} успешно активирована в Hiddify")
            return True
        else:
            await self._update_provisioning_attempt(sub_id, error)
            logger.warning(f"⚠️ Подписка {sub_id} не активирована: {error}")
            return False

    async def _activate_subscription(self, subscription_id: int):
        """Активация подписки в БД"""
        await self.db.execute(text("""
            UPDATE subscriptions
            SET status = 'active',
                activated_at = NOW(),
                provisioning_attempts = provisioning_attempts + 1,
                last_provisioning_at = NOW(),
                provisioning_error = NULL,
                updated_at = NOW()
            WHERE id = :sub_id
        """), {"sub_id": subscription_id})
        await self.db.commit()

    async def _update_provisioning_attempt(self, subscription_id: int, error: str):
        """Обновление счетчика попыток и ошибки"""
        await self.db.execute(text("""
            UPDATE subscriptions
            SET provisioning_attempts = provisioning_attempts + 1,
                last_provisioning_at = NOW(),
                provisioning_error = :error,
                updated_at = NOW()
            WHERE id = :sub_id
        """), {
            "sub_id": subscription_id,
            "error": error[:500] if error else "Unknown error"
        })

        # Если больше 10 попыток - помечаем как failed
        result = await self.db.execute(text("""
            UPDATE subscriptions
            SET status = 'provisioning_failed',
                updated_at = NOW()
            WHERE id = :sub_id
            AND provisioning_attempts >= 10
            AND status = 'provisioning'
            RETURNING id
        """), {"sub_id": subscription_id})

        if result.fetchone():
            logger.critical(f"🚨 Подписка {subscription_id} помечена как provisioning_failed!")
            await self._notify_admin(subscription_id)

        await self.db.commit()

    async def _notify_admin(self, subscription_id: int):
        """Уведомление администратора о проблеме"""
        try:
            result = await self.db.execute(text("""
                SELECT
                    u.hiddify_uuid,
                    s.tariff_slug,
                    s.provisioning_attempts,
                    s.provisioning_error,
                    u.email
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.id = :sub_id
            """), {"sub_id": subscription_id})

            data = result.fetchone()
            if not data:
                return

            uuid, tariff, attempts, error, email = data

            logger.critical(
                f"🚨 ТРЕБУЕТСЯ ВМЕШАТЕЛЬСТВО АДМИНИСТРАТОРА\n"
                f"Подписка: {subscription_id}\n"
                f"UUID: {uuid}\n"
                f"Email: {email if email else 'Бот (Без почты)'}\n"
                f"Тариф: {tariff}\n"
                f"Попыток: {attempts}\n"
                f"Ошибка: {error}\n"
                f"Статус: provisioning_failed"
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления админа: {e}")

    async def process_pending_provisioning(self, limit: int = 20) -> int:
        """
        Обработка всех подписок в статусе provisioning.

        Args:
            limit: Максимальное количество для обработки

        Returns:
            int: Количество успешно обработанных
        """
        result = await self.db.execute(text("""
            SELECT id
            FROM subscriptions
            WHERE status = 'provisioning'
            AND (
                last_provisioning_at IS NULL
                OR last_provisioning_at < NOW() - INTERVAL '5 minutes'
            )
            AND provisioning_attempts < 10
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"limit": limit})

        pending_subs = result.fetchall()
        if not pending_subs:
            return 0

        logger.info(f"📊 Найдено {len(pending_subs)} подписок для provisioning")

        processed = 0
        for (sub_id,) in pending_subs:
            try:
                success = await self.provision_subscription(sub_id)
                if success:
                    processed += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка обработки подписки {sub_id}: {e}")

        logger.info(f"✅ Обработано {processed} из {len(pending_subs)} подписок")
        return processed

# Вставьте этот код в самый конец файла ulysses-backend/app/provisioning_service.py

async def provision_and_notify(subscription_id: int, to_email: str, hiddify_uuid: str):
    """
    Фоновая задача: активация VPN в Hiddify, отправка email или сообщения в Telegram
    """
    logger.info(f"🔄 Начало provision_and_notify для подписки {subscription_id}")

    async with AsyncSessionLocal() as db:
        try:
            manager = ProvisioningManager(db)
            success = await manager.provision_subscription(subscription_id)

            if not success:
                logger.warning(f"⚠️ Подписка {subscription_id} не активирована в Hiddify")
                return

            # ============================================================
            # ПРОВЕРКА: Если email внутренний (@ulysses.internal) → Telegram
            # ============================================================
            if to_email.endswith("@ulysses.internal"):
                logger.info("🤖 Обнаружен пользователь из Telegram-бота. Отправка email отменена.")

                sub_result = await db.execute(text("""
                    SELECT u.tg_user_id, s.tariff_slug, s.expires_at
                    FROM subscriptions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.id = :sub_id LIMIT 1
                """), {"sub_id": subscription_id})
                sub_row = sub_result.fetchone()

                if sub_row and sub_row[0]:
                    tg_user_id = sub_row[0]
                    tariff_slug = sub_row[1]
                    expires_at = sub_row[2].strftime("%d.%m.%Y") if sub_row[2] else "N/A"

                    # Подписочная ссылка на защищенный HFM (Сердце)
                    sub_link = f"https://45.131.215{hiddify_uuid}/"

                    if tariff_slug in ("sub_free", "tariff_free"):
                        text_msg = (
                            f"🎁 *Тестовый период успешно активирован!*\n\n"
                            f"Ваш VPN-туннель готов к работе.\n"
                            f"⏳ Доступ активен до: *{expires_at}*\n\n"
                            f"🔗 Ссылка для подключения (нажмите для копирования):\n"
                            f"`{sub_link}`\n\n"
                            f"Инструкция: Скопируйте ссылку выше и вставьте её в приложение *Hiddify App* в поле 'Добавить профиль'."
                        )
                    else:
                        text_msg = (
                            f"🎉 *Оплата успешно получена!*\n\n"
                            f"Ваша подписка обновлена.\n"
                            f"⏳ Новый срок действия: *{expires_at}*\n\n"
                            f"🔗 Ваша ссылка для подключения:\n"
                            f"`{sub_link}`\n\n"
                            f"_Если вы уже добавляли этот профиль в приложение, перенастраивать ничего не нужно — конфиги обновятся автоматически!_"
                        )

                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "📊 Проверить баланс", "callback_data": "action_check_balance"}],
                            [{"text": "✉️ Добавить Email для уведомлений", "callback_data": "action_prompt_add_email"}]
                        ]
                    }

                    bot_token = os.getenv("BOT_TOKEN")
                    if bot_token:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            payload = {
                                "chat_id": tg_user_id,
                                "text": text_msg,
                                "parse_mode": "Markdown",
                                "reply_markup": reply_markup
                            }
                            tg_res = await client.post(tg_url, json=payload)
                            if tg_res.status_code == 200:
                                logger.info(f"✅ Уведомление об активации успешно отправлено в Telegram для {tg_user_id}")
                            else:
                                logger.error(f"❌ Ошибка отправки в Telegram API: {tg_res.text}")
                else:
                    logger.error(f"❌ Не найден tg_user_id для подписки {subscription_id}")

            else:
                logger.info(f"📧 Пользователь с сайта. Отправляю email на {to_email}...")
                # Если у вас есть хелпер отправки писем, раскомментируйте:
                # from app.utils import send_welcome_email
                # await send_welcome_email(to_email, hiddify_uuid)

        except Exception as e:
            logger.error(f"❌ Ошибка в provision_and_notify: {e}", exc_info=True)


# Вставьте этот блок кода в конец файла ulysses-backend/app/provisioning_service.py

from fastapi import HTTPException
from app.bot_messages import get_message  # Правильный импорт локализации
from datetime import datetime, timedelta

async def _action_show_about(tg_user_id, data, db, background_tasks) -> dict:
    from app.bot_messages import MD_TEXTS # Импортируем тексты, если они лежат в бот-сообщениях
    return {"state": "info", "message": MD_TEXTS.get("service", "О сервисе"), "keyboard": "back"}

async def _action_show_rules(tg_user_id, data, db, background_tasks) -> dict:
    from app.bot_messages import MD_TEXTS
    return {"state": "info", "message": MD_TEXTS.get("rules", "Правила"), "keyboard": "back"}

async def _action_show_support(tg_user_id, data, db, background_tasks) -> dict:
    from app.bot_messages import MD_TEXTS
    return {"state": "info", "message": MD_TEXTS.get("support", "Поддержка"), "keyboard": "back"}


async def _action_check_balance(
    tg_user_id: int,
    data: dict,
    db: AsyncSession,
    background_tasks: BackgroundTasks
) -> dict:
    """Проверка баланса пользователя из бота."""
    try:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id
            ORDER BY s.expires_at DESC LIMIT 1
        """), {"tg_id": tg_user_id})
        row = result.fetchone()

        if not row:
            return {"state": "error", "message": get_message("error_unknown"), "keyboard": "back"}

        uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = (
            str(row[0]) if row[0] else None, row[1], row[2], row[3], row[4], row[5], row[6]
        )

        now = datetime.utcnow()
        days_left = 0
        if db_expires_at:
            expires_naive = db_expires_at.replace(tzinfo=None) if db_expires_at.tzinfo else db_expires_at
            days_left = max(0, (expires_naive - now).days)

        is_active = (db_status in ["active", "provisioning"]) and days_left > 0
        traffic_data = {"used_gb": 0.0, "total_gb": 0.0, "remaining_gb": 0.0, "percent": 0.0}

        if uuid:
            try:
                async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                    response = await client.get(settings.HIDDIFY_API_URL, headers={"Hiddify-API-Key": settings.HIDDIFY_API_KEY})
                    if response.status_code == 200:
                        for u in response.json():
                            if str(u.get("uuid", "")).lower() == uuid.lower():
                                usage = float(u.get("current_usage_GB", 0))
                                total = float(u.get("usage_limit_GB", 0))
                                traffic_data = {
                                    "used_gb": round(usage, 2), "total_gb": round(total, 2),
                                    "remaining_gb": round(max(0.0, total - usage), 2), "percent": round((usage / total * 100) if total > 0 else 0, 1)
                                }
                                is_active = bool(u.get("enable", True)) and days_left > 0
                                break
            except Exception as e:
                logger.error(f"❌ Ошибка Hiddify в bot/action: {e}")

        return {
            "state": "balance", "message": "balance_data", "keyboard": "back",
            "balance": {
                "status": "active" if is_active else "disabled", "email": email_db if email_db else "Бот (Без почты)",
                "uuid": uuid, "traffic": traffic_data, "days_left": days_left, "is_active": is_active
            }
        }
    except Exception as e:
        logger.error(f"❌ check_balance error: {e}")
        return {"state": "error", "message": get_message("error_unknown"), "keyboard": "back"}


async def _action_buy_tariff(
    tg_user_id: int,
    data: dict,
    db: AsyncSession,
    background_tasks: BackgroundTasks
) -> dict:
    """Покупка/активация тарифа из бота."""
    import json
    from pathlib import Path
    import uuid as uuid_lib

    tariff_slug = data.get("tariff_slug")
    tg_username = data.get("tg_username", "unknown")

    if not tariff_slug:
        raise HTTPException(status_code=400, detail="tariff_slug required")

    tariffs_path = Path(__file__).parent / "tariffs.json"
    try:
        with open(tariffs_path, "r", encoding="utf-8") as f:
            tariffs = json.load(f)
    except Exception as e:
        logger.error(f"❌ Ошибка чтения tariffs.json: {e}")
        raise HTTPException(status_code=500, detail="Tariff configuration error")

    if tariff_slug not in tariffs:
        raise HTTPException(status_code=400, detail="Unknown tariff slug")

    tariff_info = tariffs[tariff_slug]
    amount = float(tariff_info["price"])
    days_to_add = int(tariff_info["days"])

    logger.info(f"💰 Тариф: {tariff_slug} | Цена: {amount} | Срок: {days_to_add} дн.")

    result = await db.execute(text("""
        SELECT id, hiddify_uuid, email FROM users WHERE tg_user_id = :tg_id LIMIT 1
    """), {"tg_id": tg_user_id})
    user_row = result.fetchone()

    if user_row:
        user_id, hiddify_uuid, email_db = user_row
        if not hiddify_uuid:
            hiddify_uuid = uuid_lib.uuid4()
            await db.execute(text("UPDATE users SET hiddify_uuid = :uuid WHERE id = :id"), {"uuid": hiddify_uuid, "id": user_id})
        logger.info(f"👤 Существующий пользователь ID={user_id}")
    else:
        hiddify_uuid = uuid_lib.uuid4()
        insert_result = await db.execute(text("""
            INSERT INTO users (tg_user_id, tg_username, email, hiddify_uuid, created_at, updated_at)
            VALUES (:tg_id, :tg_username, NULL, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id
        """), {"tg_id": tg_user_id, "tg_username": tg_username, "uuid": hiddify_uuid})
        user_id = insert_result.fetchone()[0]
        logger.info(f"✨ Новый пользователь ID={user_id}, UUID={hiddify_uuid}")

    bot_email_alias = f"tg_bot_{tg_user_id}@ulysses.internal"
    initial_status = "success" if amount == 0.00 else "pending"
    provider_tx = "tx_free_auto" if amount == 0.00 else None
    order_id = uuid_lib.uuid4()

    await db.execute(text("""
        INSERT INTO payment_attempts (id, email, user_id, tariff_slug, amount, currency, status, provider_tx_id, created_at, updated_at)
        VALUES (:id, :email, :user_id, :tariff_slug, :amount, 'RUB', :status, :tx_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """), {"id": order_id, "email": bot_email_alias, "user_id": user_id, "tariff_slug": tariff_slug, "amount": amount, "status": initial_status, "tx_id": provider_tx})

    if amount == 0.00:
        free_check = await db.execute(text("SELECT COUNT(*) FROM subscriptions WHERE user_id = :user_id AND tariff_slug = :slug"), {"user_id": user_id, "slug": tariff_slug})
        if free_check.scalar_one() > 0:
            return {"state": "error", "message": "⚠️ *Бесплатный период уже использован!*\n\nВы уже активировали тестовый доступ.", "keyboard": "tariffs"}

        sub_check = await db.execute(text("SELECT expires_at FROM subscriptions WHERE user_id = :user_id ORDER BY expires_at DESC LIMIT 1"), {"user_id": user_id})
        last_sub_row = sub_check.fetchone()

        now = datetime.utcnow()
        starts_at = now
        if last_sub_row and last_sub_row[0]:
            last_expires_naive = last_sub_row[0].replace(tzinfo=None) if last_sub_row[0].tzinfo else last_sub_row[0]
            if last_expires_naive > now: starts_at = last_expires_naive

        expires_at = starts_at + timedelta(days=days_to_add)
        sub_result = await db.execute(text("""
            INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
            VALUES (:user_id, :tariff_slug, 'provisioning', 'main', :starts_at, :expires_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id
        """), {"user_id": user_id, "tariff_slug": tariff_slug, "starts_at": starts_at, "expires_at": expires_at})
        subscription_id = sub_result.fetchone()[0]
        await db.commit()

        background_tasks.add_task(provision_and_notify, subscription_id=subscription_id, to_email=bot_email_alias, hiddify_uuid=str(hiddify_uuid))
        return {"state": "payment_free", "message": get_message("payment_free_activated"), "keyboard": "back"}

    await db.commit()
    return {"state": "payment_pending", "message": get_message("payment_pending", order_id=str(order_id), amount=amount), "keyboard": "back", "order_id": str(order_id)}
