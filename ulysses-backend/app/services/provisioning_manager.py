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
from app.email_service import email_service

logger = logging.getLogger(__name__)

class ProvisioningManager:
    """
    Бизнес-логика координации учетных записей и подписок в локальной базе данных PostgreSQL.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.provisioner = HiddifyProvisioner()

        tariffs_path = Path(__file__).parent.parent / "tariffs.json"
        try:
            with open(tariffs_path, "r", encoding="utf-8") as f:
                self.tariffs = json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка чтения тарифов: {e}")
            return False


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



async def _action_buy_tariff(tg_user_id: int, data: dict, db: AsyncSession, background_tasks: BackgroundTasks) -> dict:
    """
    💰 ИСПРАВЛЕННЫЙ МУЛЬТИВАЛЮТНЫЙ ОБРАБОТЧИК КЛИКА ПО ТАРИФУ
    Интегрирует Platega.io: разделяет бесплатный триал и мультивалютные инвойсы.
    """
    tariff_slug = data.get("tariff_slug", "sub_1m").lower().strip()
    # 🟢 Считываем ISO-код валюты, который прислал нам обновленный ТГ-бот
    chosen_currency = data.get("currency", "RUB").upper().strip()

    logger.info(f"🛒 [MANAGER] Запрос на покупку: TG={tg_user_id} | Тариф={tariff_slug} | Валюта={chosen_currency}")

    # 1. Считываем параметры тарифа из tariffs.json
    manager = ProvisioningManager(db)
    tariff_config = manager.tariffs.get(tariff_slug)

    if not tariff_config:
        return {
            "state": "error",
            "message": f"⚠️ <b>Ошибка:</b> Тарифный план <code>{tariff_slug}</code> не найден в конфигурации.",
            "keyboard": "back"
        }

    amount = float(tariff_config.get("price", 199.00))

    # -----------------------------------------------------------------
    # РЕЖИМ А: БЕСПЛАТНЫЙ ТАРИФ (Мгновенная автоактивация)
    # -----------------------------------------------------------------
    # Вызываем общую функцию активации (она создаст пользователя и подписку, если нужно)
    email = f"tg_{tg_user_id}@ulysses.internal"
    success = await activate_free_subscription(db, email, tariff_slug)

    if success:
        uuid_res = await db.execute(text("SELECT hiddify_uuid FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_user_id})
        uuid_row = uuid_res.fetchone()
        hiddify_uuid = str(uuid_row[0]) if uuid_row else None

        # Срок действия всегда 3 дня от текущего момента
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(days=3)
        expires_str = expires_at.strftime('%Y-%m-%d %H:%M')

        domain = getattr(settings, "HIDDIFY_DOMAIN", None) or "ulysses.best"
        subscription_link = f"https://{domain}/X6CbExbUw2/sub/{hiddify_uuid}/"

        message = get_message("free_activated", subscription_link=subscription_link, expires=expires_str)
        return {"state": "info", "message": message, "keyboard": "back"}
    else:
        return {
            "state": "error",
            "message": get_message("error_api"),
            "keyboard": "back"
        }


    # -----------------------------------------------------------------
    # РЕЖИМ Б: ПЛАТНЫЕ ТАРИФЫ (Генерация мультивалютных ссылок через Platega SDK)
    # -----------------------------------------------------------------
    from app.private.platega_service import PlategaPaymentService
    from app.private.platega import Platega

    # 1. Генерируем UUID и записываем инвойс в СУБД в статусе 'pending'
    attempt_id = str(uuid_lib.uuid4())

    sql_invoice = """
        INSERT INTO payment_attempts (id, user_id, tariff_slug, amount, currency, status, created_at, updated_at, email)
        VALUES (:id, (SELECT id FROM users WHERE tg_user_id = :tg_id), :tariff, :amount, :currency, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'tg_bot@ulysses.internal')
    """
    try:
        await db.execute(text(sql_invoice), {
            "id": attempt_id, "tg_id": tg_user_id, "tariff": tariff_slug, "amount": amount, "currency": chosen_currency
        })
        await db.commit()
    except Exception as db_err:
        logger.error(f"❌ [MANAGER] Ошибка записи инвойса в СУБД: {db_err}")
        return {"state": "error", "message": "⚠️ Локальный сбой базы данных биллинга.", "keyboard": "back"}

    # 2. Вычисляем метод Platega на основе выбранного направления
    # СБП (2) для RUB, Крипта (13) для USDT, Международные карты (12) для USD/EUR
    pay_method = Platega.METHOD_SBP_QR
    if chosen_currency == "USDT":
        pay_method = Platega.METHOD_CRYPTO
    elif chosen_currency in ("USD", "EUR"):
        pay_method = Platega.METHOD_INTERNATIONAL

    # 3. Вызываем асинхронный сервис Platega (внутри пула потоков asyncio.to_thread)
    pay_service = PlategaPaymentService()
    invoice_data = await pay_service.create_invoice_link(
        amount=amount,
        currency=chosen_currency,
        attempt_id=attempt_id,
        tariff_name=tariff_slug,
        method=pay_method
    )

    if invoice_data and "redirect" in invoice_data:
        pay_url = invoice_data["redirect"]

        # Название тарифа на русском для красивого вывода
        tariff_ru_name = manager.tariffs[tariff_slug].get("name_ru", tariff_slug)

        msg_text = (
            f"💳 <b>Счёт на оплату успешно сформирован!</b>\n\n"
            f"• 📋 <b>Тариф:</b> {tariff_ru_name}\n"
            f"• 💰 <b>К оплате:</b> <code>{amount} {chosen_currency}</code>\n\n"
            f"Для завершения активации нажмите на кнопку ниже и оплатите счёт в защищенном окне эквайринга **Platega.io**.\n\n"
            f"🔗 <a href='{pay_url}'><b>НАЖМИТЕ ТУТ ДЛЯ ПЕРЕХОДА К ОПЛАТЕ</b></a>\n\n"
            f"<i>После подтверждения платежа банком, конфигурационная карточка доступа прилетит в этот чат автоматически!</i>"
        )
        return {
            "state": "payment_pending",
            "message": msg_text,
            "keyboard": "back"
        }
    else:
        logger.error(f"❌ [MANAGER] Агрегатор Platega отклонил генерацию инвойса для {attempt_id}")
        return {
            "state": "error",
            "message": "⚠️ <b>Провайдер платежей Platega временно недоступен.</b>\n\nПожалуйста, попробуйте повторить запрос через минуту.",
            "keyboard": "back"
        }



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


async def activate_free_subscription(db: AsyncSession, email: str, tariff_slug: str, tg_user_id: int = None) -> bool:
    """Активировать бесплатный тариф для пользователя по email или tg_user_id.
    Всегда создаёт новую подписку, даже если у пользователя уже был sub_free.
    """
    # 1. Найти пользователя по tg_user_id или email
    if tg_user_id:
        user_res = await db.execute(
            text("SELECT id, hiddify_uuid, email FROM users WHERE tg_user_id = :tg_id"),
            {"tg_id": tg_user_id}
        )
    else:
        user_res = await db.execute(
            text("SELECT id, hiddify_uuid, email FROM users WHERE email = :email"),
            {"email": email}
        )
    user_row = user_res.fetchone()

    if user_row:
        user_id, hiddify_uuid, db_email = user_row
        # если email в базе пустой, используем переданный (может быть tg_...)
        if not db_email:
            db_email = email
    else:
        hiddify_uuid = str(uuid_lib.uuid4())
        try:
            sql_user = """
                INSERT INTO users (email, hiddify_uuid, tg_user_id, created_at, updated_at)
                VALUES (:email, :uuid, :tg_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """
            res_user = await db.execute(text(sql_user), {
                "email": email,
                "uuid": hiddify_uuid,
                "tg_id": tg_user_id
            })
            user_id = res_user.scalar_one()
            await db.commit()
            db_email = email
        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            return False

    # 2. Проверить, есть ли уже активный sub_free (не блокирует создание нового)
    existing_sub = await db.execute(
        text("""
            SELECT id FROM subscriptions
            WHERE user_id = :uid AND tariff_slug = 'sub_free' AND status = 'active'
        """),
        {"uid": user_id}
    )
    if existing_sub.fetchone():
        logger.info(f"Пользователь {db_email} уже имеет активный sub_free, будет создан новый тестовый период")

    # 3. Создать подписку
    days = 3
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    sql_sub = """
        INSERT INTO subscriptions (user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at)
        VALUES (:user_id, :tariff, 'provisioning', 'main', CURRENT_TIMESTAMP, :expires, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
    """
    res_sub = await db.execute(text(sql_sub), {
        "user_id": user_id,
        "tariff": tariff_slug,
        "expires": expires_at
    })
    sub_id = res_sub.scalar_one()
    await db.commit()

    # 4. Провижн на HFM
    try:
        provisioner = HiddifyProvisioner()
        # Пробуем создать пользователя; если он уже есть, игнорируем ошибку 400
        success = False
        try:
            success = await provisioner.create_user(uuid=hiddify_uuid, name=db_email.split("@")[0][:30])
        except Exception as e:
            if "already exists" in str(e).lower() or "exists" in str(e).lower():
                # Пользователь уже существует – это нормально, считаем успехом
                success = True
            else:
                raise

        if success:
            await db.execute(
                text("UPDATE subscriptions SET status = 'active', activated_at = CURRENT_TIMESTAMP WHERE id = :sub_id"),
                {"sub_id": sub_id}
            )
            await db.commit()
            logger.info(f"✅ Бесплатный тариф активирован для {db_email}")

            # Отправка приветственного письма (только для реальных email)
            if db_email and "@" in db_email and not db_email.endswith("@ulysses.internal"):
                try:
                    from app.email_service import email_service as mail_svc
                    subject, html_body, text_body = mail_svc.get_welcome_email(db_email, hiddify_uuid)
                    await mail_svc.send_email(db_email, subject, html_body, text_body)
                    logger.info(f"📧 Письмо отправлено на {db_email}")
                except Exception as email_err:
                    logger.error(f"❌ Ошибка отправки письма для {db_email}: {email_err}")

            return True
        else:
            await db.execute(
                text("UPDATE subscriptions SET provisioning_error = 'HFM API error' WHERE id = :sub_id"),
                {"sub_id": sub_id}
            )
            await db.commit()
            logger.error(f"❌ HFM отклонил создание для {db_email}")
            return False
    except Exception as e:
        await db.execute(
            text("UPDATE subscriptions SET provisioning_error = :err WHERE id = :sub_id"),
            {"sub_id": sub_id, "err": str(e)[:200]}
        )
        await db.commit()
        logger.error(f"❌ Ошибка провижна для {db_email}: {e}")
        return False
