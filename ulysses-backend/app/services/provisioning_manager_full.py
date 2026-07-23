# ulysses-backend/app/services/provisioning_manager.py
# ============================================================
# ЧАСТЬ 1: ИМПОРТЫ И ОСНОВНОЙ КЛАСС МЕНЕДЖЕРА
# ============================================================

import json
import logging
import httpx
import uuid as uuid_lib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, BackgroundTasks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.hiddify_client import HiddifyProvisioner
from app.bot_messages import get_message

logger = logging.getLogger(__name__)

class ProvisioningManager:
    """
    Бизнес-логика координации учетных записей и подписок в локальной базе данных PostgreSQL.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.provisioner = HiddifyProvisioner()

    async def provision_subscription(self, subscription_id: int) -> bool:
        """Синхронизация подписки с удаленной панелью VPN и перевод в active."""
        logger.info(f"⚙️ Запуск синхронизации подписки #{subscription_id}")

        sub_query = await self.db.execute(text("""
            SELECT s.id, s.tariff_slug, s.status, u.hiddify_uuid, u.id as user_id, u.email
            FROM subscriptions s JOIN users u ON s.user_id = u.id
            WHERE s.id = :sub_id LIMIT 1
        """), {"sub_id": subscription_id})
        sub = sub_query.fetchone()

        if not sub:
            logger.error(f"❌ Подписка #{subscription_id} не найдена в базе")
            return False

        sub_id, tariff_slug, current_status, hiddify_uuid, user_id, user_email = sub
        uuid_str = str(hiddify_uuid).lower()

        tariffs_path = Path(__file__).parent.parent / "tariffs.json"
        try:
            with open(tariffs_path, "r", encoding="utf-8") as f:
                tariffs = json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка чтения тарифов: {e}")
            return False

        if tariff_slug not in tariffs:
            return False

        if current_status == "active":
            exists = await self.provisioner.check_user_exists(uuid_str)
            if exists:
                return True

        success = await self.provisioner.enable_user(str(uuid_str))
        if success:
            await self.db.execute(text("""
                UPDATE subscriptions SET status = 'active', provisioning_error = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = :sub_id
            """), {"sub_id": subscription_id})
            await self.db.commit()
            return True
        else:
            await self.db.execute(text("""
                UPDATE subscriptions SET status = 'provisioning_failed', provisioning_error = 'Hiddify API Error', updated_at = CURRENT_TIMESTAMP
                WHERE id = :sub_id
            """), {"sub_id": subscription_id})
            await self.db.commit()
            return False

    async def process_pending_provisioning(self, limit: int = 20) -> int:
        """Обработка зависших подписок."""
        result = await self.db.execute(text("""
            SELECT id FROM subscriptions WHERE status = 'provisioning'
            ORDER BY created_at ASC LIMIT :limit
        """), {"limit": limit})
        processed = 0
        for row in result.fetchall():
            if await self.provision_subscription(row[0]):
                processed += 1
        return processed
# ============================================================
# ЧАСТЬ 2: ВСПОМОГАТЕЛЬНЫЕ ЭКШЕНЫ И ПРОВЕРКА БАЛАНСА
# ============================================================

# Замените эти три функции в Части 2 на следующий рабочий вариант:

# Внутри ulysses-backend/app/services/provisioning_manager.py

async def _action_show_about(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    text_about = get_message(
        "about",
        default="ℹ️ <b>О сервисе Ulysses VPN</b>\n\nМы используем передовой протокол VLESS и распределенную сеть серверов-щитов для защиты вашего трафика."
    )
    return {"state": "info", "message": text_about, "keyboard": "back"}


async def _action_show_rules(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    text_rules = get_message(
        "rules",
        default="📜 <b>Официальные документы Ulysses VPN</b>\n\n• Пользовательское соглашение\n• Политика конфиденциальности\n• Правила триал-доступа."
    )
    return {"state": "info", "message": text_rules, "keyboard": "back"}


async def _action_show_support(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    text_support = get_message(
        "support",
        default="✉️ <b>Техническая поддержка</b>\n\nЕсли у вас возникли вопросы по настройке туннеля, напишите саппорту: @ulysses_support_bot"
    )
    return {"state": "info", "message": text_support, "keyboard": "back"}

async def _action_check_balance(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    """Проверка баланса пользователя из бота с запросом метрик из Hiddify."""
    try:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id
            FROM users u LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id ORDER BY s.expires_at DESC LIMIT 1
        """), {"tg_id": tg_user_id})
        row = result.fetchone()

        if not row:
            return {"state": "error", "message": get_message("error_unknown"), "keyboard": "back"}

        uuid, email_db, db_expires_at, db_status, user_id = row
        uuid_str = str(uuid) if uuid else None

        now = datetime.utcnow()
        days_left = max(0, (db_expires_at.replace(tzinfo=None) - now).days) if db_expires_at else 0
        is_active = db_status in ["active", "provisioning"] and days_left > 0
        traffic_data = {"used_gb": 0.0, "total_gb": 0.0, "remaining_gb": 0.0, "percent": 0.0}

        if uuid_str:
            provisioner = HiddifyProvisioner()
            users = await provisioner.fetch_all_users()
            if users:
                for u in users:
                    if str(u.get("uuid", "")).lower() == uuid_str.lower():
                        usage = float(u.get("current_usage_GB", 0))
                        total = float(u.get("usage_limit_GB", 0))
                        traffic_data = {
                            "used_gb": round(usage, 2), "total_gb": round(total, 2),
                            "remaining_gb": round(max(0.0, total - usage), 2),
                            "percent": round((usage / total * 100) if total > 0 else 0, 1)
                        }
                        is_active = bool(u.get("enable", True)) and days_left > 0
                        break

        return {
            "state": "balance", "message": "balance_data", "keyboard": "back",
            "balance": {
                "status": "active" if is_active else "disabled", "email": email_db or "Бот (Без почты)",
                "uuid": uuid_str, "traffic": traffic_data, "days_left": days_left, "is_active": is_active
            }
        }
    except Exception as e:
        logger.error(f"❌ Ошибка check_balance: {e}")
        return {"state": "error", "message": get_message("error_unknown"), "keyboard": "back"}
# ============================================================
# ЧАСТЬ 3: АКТИВАЦИЯ И ПОКУПКА ТАРИФОВ
# ============================================================

# Внутри ulysses-backend/app/services/provisioning_manager.py

async def _action_buy_tariff(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    """
    Универсальный обработчик экшена покупки и активации тарифов.
    Разделяет вызов тарифной сетки и непосредственную транзакцию активации услуг.
    Бронебойно извлекает параметры из JSON-пакета любой вложенности.
    """
    if not isinstance(data, dict):
        data = {}

    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    # 🔍 МНОГОУРОВНЕВЫЙ СБОР ПАРАМЕТРОВ: ищем слаг тарифа во всех возможных секциях JSON
    tariff_slug = data.get("tariff_slug") or payload.get("tariff_slug") or data.get("action")

    # Если в качестве слага по ошибке прилетело общее имя экшена, сбрасываем его
    if tariff_slug == "buy_tariff":
        tariff_slug = None

    # Если слаг прилетел в коротком формате кнопки бота (t_free, t_1m), восстанавливаем в sub_free/sub_1m
    if tariff_slug and tariff_slug.startswith("t_"):
        short_name = tariff_slug.replace("t_", "")
        tariff_slug = short_name if short_name.startswith("sub_") else f"sub_{short_name}"

    tg_username = payload.get("tg_username") or data.get("tg_username") or "unknown"

    # 🌟 ШАГ 1: Если после всех проверок слага нет — это 100% первичный вызов меню.
    # Вместо ошибки 400 Bad Request возвращаем команду переключения на экран тарифов.
    if not tariff_slug:
        logger.info(f"🛒 Пользователь TG {tg_user_id} открыл интерактивное меню тарифов")
        return {
            "state": "tariffs",
            "message": "🛒 Выберите подходящий тарифный план для старта Ulysses VPN:",
            "keyboard": "tariffs"
        }

    logger.info(f"💰 [БЭКЕНД] Запуск транзакции активации тарифа '{tariff_slug}' для TG {tg_user_id} (@{tg_username})")

    # 🌟 ШАГ 2: Извлекаем локальный ID пользователя по его Telegram ID
    user_res = await db.execute(
        text("SELECT id, hiddify_uuid FROM users WHERE tg_user_id = :tg_id"),
        {"tg_id": tg_user_id}
    )
    user_row = user_res.fetchone()
    if not user_row:
        logger.error(f"❌ Сбой активации: Пользователь TG {tg_user_id} не найден в СУБД!")
        return {
            "state": "error",
            "message": "⚠️ <b>Профиль не найден.</b>\n\nОтправьте команду /start для повторной инициализации аккаунта.",
            "keyboard": "back"
        }

    user_internal_id, hiddify_uuid_str = user_row

    # 🌟 ШАГ 3: Если пользователь запрашивает бесплатный триал ('sub_free'),
    # проверяем историю подписок, чтобы исключить повторную халяву.
    if tariff_slug == "sub_free":
        check_history_sql = """
            SELECT id FROM subscriptions
            WHERE user_id = :uid AND tariff_slug = 'sub_free' AND status != 'cancelled'
            LIMIT 1
        """
        history_res = await db.execute(text(check_history_sql), {"uid": user_internal_id})
        if history_res.fetchone():
            logger.warning(f"🚫 Блокировка: Пользователь TG {tg_user_id} пытается повторно получить тариф Free!")
            return {
                "state": "error",
                "message": "⚠️ <b>Бесплатный период уже был активирован ранее!</b>\n\nПовторная выдача тестового тарифа заблокирована системой биллинга. Пожалуйста, выберите платный тарифный план.",
                "keyboard": "back"
            }

    # 🌟 ШАГ 4: Формируем сроки подписки (для триала даем 3 дня, для коммерческих — 30 дней)
    now = datetime.now(timezone.utc)
    days_to_add = 3 if tariff_slug == "sub_free" else 30
    expires_at = now + timedelta(days=days_to_add)

    # 🌟 ШАГ 5: Фиксируем подписку в базе данных со стартовым статусом 'provisioning'
    sql_insert_sub = """
        INSERT INTO subscriptions (
            user_id, tariff_slug, status, node_id, starts_at, expires_at,
            created_at, updated_at, provisioning_attempts, provisioning_error
        )
        VALUES (
            :uid, :tariff, 'provisioning', 'main', :starts, :expires,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, NULL
        )
        RETURNING id
    """
    try:
        sub_res = await db.execute(text(sql_insert_sub), {
            "uid": user_internal_id,
            "tariff": tariff_slug,
            "starts": now,
            "expires": expires_at
        })
        new_subscription_id = sub_res.scalar_one()
        await db.commit()
        logger.info(f"💾 Подписка #{new_subscription_id} успешно создана в PostgreSQL. Запуск конвейера провижна...")
    except Exception as db_err:
        await db.rollback()
        logger.error(f"❌ Ошибка записи подписки в PostgreSQL: {db_err}")
        return {
            "state": "error",
            "message": "⚠️ <b>Ошибка СУБД при оформлении подписки.</b>\n\nПожалуйста, попробуйте позже.",
            "keyboard": "back"
        }

    # 🌟 ШАГ 6: Передаем тяжелую задачу связи с нодой Hiddify v2 и отправки ссылки
    # в изолированный асинхронный воркер, полностью защищая UI бота от фризов.
    from app.tasks.workers import provision_and_notify
    background_tasks.add_task(
        provision_and_notify,
        subscription_id=new_subscription_id,
        tg_user_id=tg_user_id,
        hiddify_uuid=str(hiddify_uuid_str),
        expires_at=expires_at
    )

    # Возвращаем мгновенный промежуточный ответ, переключая интерфейс в режим ожидания
    return {
        "state": "info",
        "message": (
            "🎁 <b>Запрос успешно принят в обработку!</b>\n\n"
            "⚙️ Наш кластер настраивает ваш персональный защищённый туннель на ноде...\n\n"
            "<i>Пожалуйста, подождите несколько секунд. Конфигурационная карточка со ссылкой подключения автоматически прилетит в этот чат!</i>"
        ),
        "keyboard": "back"
    }

# Добавьте в ulysses-backend/app/services/provisioning_manager.py:

async def _action_start_registration(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    """🌟 МЯГКАЯ РЕГИСТРАЦИЯ: Гарантирует наличие пользователя в БД при вызове /start."""
    payload = data.get("payload", {}) or {}
    tg_username = payload.get("tg_username", "unknown")

    # Проверяем, существует ли пользователь в PostgreSQL
    res = await db.execute(text("SELECT id FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_user_id})
    if not res.fetchone():
        import uuid as uuid_lib
        new_uuid = uuid_lib.uuid4()

        # Создаем чистую запись с UUID под новый тест с нуля
        sql_insert = """
            INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
            VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        await db.execute(text(sql_insert), {"tg_id": tg_user_id, "username": tg_username, "uuid": new_uuid})
        await db.commit()
        logger.info(f"👤 [МЯГКАЯ РЕГИСТРАЦИЯ] Пользователь {tg_user_id} (@{tg_username}) успешно занесен в PostgreSQL")

    return {"state": "main_menu", "message": "OK", "keyboard": "active"}


# Не забудьте зарегистрировать имя функции в глобальном словаре действий actions в этом же файле:
actions = {
    "start": _action_start_registration,  # 🌟 РЕГИСТРИРУЕМ НАШ ЭКШЕН СТАРТА
    "buy_tariff": _action_buy_tariff,
    "check_balance": _action_check_balance,
    "show_about": _action_show_about,
    "show_rules": _action_show_rules,
    "show_support": _action_show_support,
}
