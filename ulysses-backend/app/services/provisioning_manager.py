# ulysses-backend/app/services/provisioning_manager.py
# ============================================================
# ЧАСТЬ 1: ИМПОРТЫ И ОСНОВНОЙ КЛАСС МЕНЕДЖЕРА
# ============================================================

import json
import logging
import httpx
import uuid as uuid_lib
from pathlib import Path
from datetime import datetime, timedelta
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

        success = await self.provisioner.enable_user(uuid_str)
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

async def _action_show_about(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    # Используем штатную функцию локализации вместо словаря
    return {"state": "info", "message": get_message("about", default="ℹ️ Информация о сервисе Ulysses VPN"), "keyboard": "back"}

async def _action_show_rules(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    return {"state": "info", "message": get_message("rules", default="📜 Правила использования сервиса"), "keyboard": "back"}

async def _action_show_support(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    return {"state": "info", "message": get_message("support", default="✉️ Поддержка пользователей"), "keyboard": "back"}

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

async def _action_buy_tariff(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    """Покупка/активация тарифа из бота."""
    tariff_slug = data.get("tariff_slug")
    tg_username = data.get("tg_username", "unknown")

    if not tariff_slug:
        raise HTTPException(status_code=400, detail="tariff_slug required")

    tariffs_path = Path(__file__).parent.parent / "tariffs.json"
    with open(tariffs_path, "r", encoding="utf-8") as f:
        tariffs = json.load(f)

    if tariff_slug not in tariffs:
        raise HTTPException(status_code=400, detail="Unknown tariff slug")

    tariff_info = tariffs[tariff_slug]
    amount = float(tariff_info["price"])
    days_to_add = int(tariff_info["days"])

    result = await db.execute(text("SELECT id, hiddify_uuid FROM users WHERE tg_user_id = :tg_id LIMIT 1"), {"tg_id": tg_user_id})
    user_row = result.fetchone()

    if user_row:
        user_id, hiddify_uuid = user_row[0], user_row[1]
        if not hiddify_uuid:
            hiddify_uuid = uuid_lib.uuid4()
            await db.execute(text("UPDATE users SET hiddify_uuid = :uuid WHERE id = :id"), {"uuid": hiddify_uuid, "id": user_id})
    else:
        hiddify_uuid = uuid_lib.uuid4()
        insert_result = await db.execute(text("""
            INSERT INTO users (tg_user_id, tg_username, email, hiddify_uuid, created_at, updated_at)
            VALUES (:tg_id, :tg_username, NULL, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id
        """), {"tg_id": tg_user_id, "tg_username": tg_username, "uuid": hiddify_uuid})
        user_id = insert_result.fetchone()[0]

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
            if last_expires_naive > now:
                starts_at = last_expires_naive

        expires_at = starts_at + timedelta(days=days_to_add)
        sub_result = await db.execute(text("""
            INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
            VALUES (:user_id, :tariff_slug, 'provisioning', 'main', :starts_at, :expires_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id
        """), {"user_id": user_id, "tariff_slug": tariff_slug, "starts_at": starts_at, "expires_at": expires_at})
        subscription_id = sub_result.fetchone()[0]
        await db.commit()

        from app.tasks.workers import provision_and_notify
        background_tasks.add_task(provision_and_notify, subscription_id=subscription_id, to_email=bot_email_alias, hiddify_uuid=str(hiddify_uuid))
        return {"state": "payment_free", "message": get_message("payment_free_activated"), "keyboard": "back"}

    await db.commit()
    return {"state": "payment_pending", "message": get_message("payment_pending", order_id=str(order_id), amount=amount), "keyboard": "back", "order_id": str(order_id)}
