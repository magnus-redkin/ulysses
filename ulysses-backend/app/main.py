# ulysses-backend/app/main.py

import os
import psutil
from pathlib import Path
from dotenv import load_dotenv

import json
import uuid
import httpx
import aiosmtplib
import ssl
import email.utils as email_utils
import asyncio

# Настройка логирования
import logging
from logging.handlers import RotatingFileHandler

from app.monitoring import metrics
import platform

from datetime import datetime, timedelta
from fastapi import FastAPI, Header, Query, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy import func

from app.email_service import email_service
from app.database import get_db, AsyncSessionLocal
from app.models import PaymentAttempt, User, Subscription
from app.config import settings
from app.provisioning_service import ProvisioningManager
from app.system_info import collect_system_metrics
from app.bot_messages import get_message

from app.enot_service import get_invoice_info

from email.message import EmailMessage

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

app = FastAPI(title="Ulysses Lab VPN Billing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://138.124.114.5:5173",
        "http://ulysses.best",
        "https://ulysses.best",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Pydantic модели
# ============================================================

class InvoiceCreate(BaseModel):
    email: EmailStr
    tariff_slug: str


class WebhookPayload(BaseModel):
    order_id: uuid.UUID
    provider_tx_id: str
    status: str  # 'success' или 'failed'

class LinkTelegramRequest(BaseModel):
    uuid: str
    tg_user_id: int  # Это теперь может быть BIGINT
    tg_username: str | None = None

class TelegramLinkPayload(BaseModel):
    uuid: str
    tg_user_id: int
    tg_username: str | None = None

class BotInvoiceCreate(BaseModel):
    tg_user_id: int
    tg_username: str | None = None
    tariff_slug: str

BOT_LIB_PATH = Path(__file__).parent.parent.parent / "ulysses-bot" / "lib"

def _read_md(filename: str) -> str:
    try:
        with open(BOT_LIB_PATH / filename, "r", encoding="utf-8") as f:
            return f.read()[:4000]
    except:
        return "⚠️ Документ временно недоступен."

MD_TEXTS = {
    "service": _read_md("service.md"),
    "rules": _read_md("rules.md"),
    "support": _read_md("support.md"),
}



@app.post("/api/user/link-telegram")
async def link_telegram_account(
    payload: TelegramLinkPayload,
    db: AsyncSession = Depends(get_db)
):
    """
    Привязка Telegram аккаунта к пользователю на основе UUID его подписки.
    """
    # 1. Ищем пользователя по его бессмертному UUID в таблице USERS
    # Заодно берем ID его подписки (если она уже создалась через вебхук)
    sub_result = await db.execute(text("""
        SELECT u.id AS user_id, s.id AS sub_id, s.status
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE CAST(u.hiddify_uuid AS TEXT) = :uuid
        ORDER BY s.created_at DESC
        LIMIT 1
    """), {"uuid": str(payload.uuid).lower()})
    sub_row = sub_result.fetchone()

    if not sub_row:
        raise HTTPException(status_code=404, detail="User with this VPN token not found")

    user_id = sub_row[0]
    sub_id = sub_row[1]
    current_status = sub_row[2]

    # 2. ЗАЩИТА: Сбрасываем этот tg_user_id у других записей, если он был где-то занят
    await db.execute(text("""
        UPDATE users
        SET tg_user_id = NULL, tg_username = NULL
        WHERE tg_user_id = :tg_id AND id != :user_id
    """), {
        "tg_id": payload.tg_user_id,
        "user_id": user_id
    })

    # 3. Привязываем Telegram данные к нашему целевому пользователю
    await db.execute(text("""
        UPDATE users
        SET tg_user_id = :tg_id, tg_username = :tg_username
        WHERE id = :user_id
    """), {
        "tg_id": payload.tg_user_id,
        "tg_username": payload.tg_username,
        "user_id": user_id
    })

    # 4. Если подписка найдена и она в статусе provisioning, переводим в active
    if sub_id and current_status == "provisioning":
        await db.execute(text("""
            UPDATE subscriptions
            SET status = 'active'
            WHERE id = :sub_id
        """), {"sub_id": sub_id})

    await db.commit()
    logger.info(f"✅ Telegram ID {payload.tg_user_id} успешно привязан к user_id {user_id}")

    return {"status": "success", "message": "Telegram account linked successfully"}



# ============================================================
# Вспомогательные функции
# ============================================================

# ulysses-backend/app/main.py

async def send_welcome_email(to_email: str, hiddify_uuid: str) -> bool:
    """Отправка приветственного письма (использует EmailService)"""
    subject, html_body, text_body = email_service.get_welcome_email(to_email, hiddify_uuid)
    return await email_service.send_email(to_email, subject, html_body, text_body)


async def create_hiddify_vpn_user(user_uuid: str, email: str, tariff_slug: str) -> bool:
    """
    Создание пользователя в Hiddify
    (Оставлена для обратной совместимости)
    """
    from app.provisioning_service import HiddifyProvisioner
    provisioner = HiddifyProvisioner()
    success, _ = await provisioner.create_user(user_uuid, email, tariff_slug, max_retries=1)
    return success

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

                # Достаем tg_user_id этого пользователя из базы через subscription
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

                    # Ссылка для импорта в Hiddify App
                    sub_link = f"https://ulysses.best/{hiddify_uuid}/#Ulysses"

                    # Формируем текст сообщения в зависимости от того, продление это или новая покупка
                    if tariff_slug == "sub_free":
                        text_msg = (
                            f"🎁 *Тестовый период успешно активирован!*\n\n"
                            f"Ваш VPN-туннель готов к работе.\n"
                            f"⏳ Доступ активен до: *{expires_at}*\n\n"
                            f"🔗 Ссылка для подключения (нажмите для копирования):\n"
                            f"`{sub_link}`\n\n"
                            f"Инструкция: Скопируйте ссылку выше и вставьте её в приложение *Hiddify App*."
                        )
                    else:
                        text_msg = (
                            f"🎉 *Оплата успешно получена!*\n\n"
                            f"Ваша подписка обновлена.\n"
                            f"⏳ Новый срок действия: *{expires_at}*\n\n"
                            f"🔗 Ваша ссылка для подключения:\n"
                            f"`{sub_link}`\n\n"
                            f"_Если вы уже добавляли ключ в приложение, перенастраивать ничего не нужно — данные обновятся автоматически!_"
                        )

                    # Inline-клавиатура для сообщения в боте
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "📊 Проверить баланс", "callback_data": "check_balance"}],
                            [{"text": "✉️ Добавить Email для уведомлений", "callback_data": "prompt_add_email"}]
                        ]
                    }

                    # Прямой запрос к API Telegram
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
                # Обычный сценарий: отправка письма на email
                logger.info(f"📧 Пользователь с сайта. Отправляю письмо на {to_email}...")
                await send_welcome_email(to_email, hiddify_uuid)

        except Exception as e:
            logger.error(f"❌ Ошибка в provision_and_notify: {e}", exc_info=True)



# ============================================================
# ЭНДПОИНТЫ
# ============================================================

@app.post("/api/billing/create-invoice")
async def create_invoice(payload: InvoiceCreate, db: AsyncSession = Depends(get_db)):
    """
    Обновленный эндпоинт создания счета.
    Поддерживает новые типы тарифов для бота и веб-страницы.
    """
    # Загружаем тарифы из tariffs.json
    import json
    tariffs_path = Path(__file__).parent / "tariffs.json"
    with open(tariffs_path, "r", encoding="utf-8") as f:
        tariffs = json.load(f)

    # Получаем цену из tariffs.json
    tariff_config = tariffs.get(payload.tariff_slug, {})
    amount = float(tariff_config.get("price", 490.00))

    logger.info(f"💰 Создание инвойса: тариф={payload.tariff_slug}, цена={amount}")

    new_attempt = PaymentAttempt(
        email=payload.email,
        tariff_slug=payload.tariff_slug,
        amount=amount,
        status="pending"
    )
    db.add(new_attempt)
    await db.commit()
    await db.refresh(new_attempt)

    # Для бесплатного тарифа можно вернуть специальный статус
    if amount == 0.00:
        return {
            "status": "free_tariff",
            "order_id": new_attempt.id,
            "amount": new_attempt.amount,
            "currency": new_attempt.currency,
            "message": "Бесплатный тариф. Оплата не требуется."
        }

    return {
        "status": "success",
        "order_id": new_attempt.id,
        "amount": new_attempt.amount,
        "currency": new_attempt.currency
    }


@app.post("/api/billing/webhook")
async def payment_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Обработка успешного вебхука от платежного агрегатора.
    Реализует концепцию продления дат (суммирование дней) и бессмертного UUID.
    """
    # 1. Находим инвойс в нашей базе
    try:
        invoice_id = uuid.UUID(payload.order_id) if isinstance(payload.order_id, str) else payload.order_id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    result = await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.id == invoice_id)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if attempt.status == "success":
        return {"status": "already_processed"}

    # 2. Если платеж отклонен агрегатором
    if payload.status != "success":
        attempt.status = "failed"
        await db.commit()
        return {"status": "failed_marked"}

    # 3. Фиксируем успешную оплату инвойса
    attempt.status = "success"
    attempt.provider_tx_id = payload.provider_tx_id
    attempt.updated_at = datetime.utcnow()

    # 4. Находим пользователя по email или создаем абсолютно нового
    # === [ИЗМЕНЕНИЕ] Шаг 4. Находим пользователя: приоритет по user_id, затем по email ===
    user = None
    if attempt.user_id:
        # Если инвойс создан из бота, user_id уже жестко привязан
        user_result = await db.execute(
            select(User).where(User.id == attempt.user_id)
        )
        user = user_result.scalar_one_or_none()
        logger.info(f"👤 [WEBHOOK] Юзер найден по привязанному user_id: {attempt.user_id}")

    if not user:
        # Старый сценарий (покупка с сайта): ищем по email или создаем абсолютно нового
        user_result = await db.execute(
            select(User).where(User.email == attempt.email)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            # Первое появление юзера с сайта: генерируем бессмертный UUID
            user = User(
                email=attempt.email,
                hiddify_uuid=uuid.uuid4()
            )
            db.add(user)
            await db.flush()  # Получаем user.id
            logger.info(f"👤 [WEBHOOK] Создан новый пользователь сайта {user.email} с ключом {user.hiddify_uuid}")
        else:
            if not user.hiddify_uuid:
                user.hiddify_uuid = uuid.uuid4()
                await db.flush()

        # Привязываем ID пользователя к оплаченному инвойсу с сайта
        attempt.user_id = user.id

        # 5. КЛЮЧЕВАЯ ЛОГИКА: Расчет дат подписки (Складывание/Продление)
    # Загружаем тарифы из tariffs.json
    import json
    tariffs_path = Path(__file__).parent / "tariffs.json"
    with open(tariffs_path, "r", encoding="utf-8") as f:
        tariffs = json.load(f)

    tariff_config = tariffs.get(attempt.tariff_slug, {})
    days_to_add = int(tariff_config.get("days", 30))

    logger.info(f"📅 Тариф {attempt.tariff_slug}: +{days_to_add} дней")

    # Ищем его самую свежую/последнюю подписку
    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    last_subscription = sub_result.scalar_one_or_none()

    now = datetime.utcnow()

    # Гарантируем дефолтное объявление переменных перед условиями
    starts_at = now
    expires_at = now + timedelta(days=days_to_add)

    # Корректируем даты, если есть активная подписка
    if last_subscription and last_subscription.expires_at:
        # Убираем таймзону, если она есть в базе, для корректного сравнения с datetime.utcnow()
        last_expires_naive = last_subscription.expires_at.replace(tzinfo=None) if last_subscription.expires_at.tzinfo else last_subscription.expires_at

        if last_expires_naive > now:
            # Подписка ЕЩЕ АКТИВНА: продлеваем её, отталкиваясь от даты её будущего окончания
            starts_at = last_expires_naive
            expires_at = starts_at + timedelta(days=days_to_add)
            logger.info(f"🔄 Продление активной подписки юзера {user.id}. Добавляем {days_to_add} дней к дате {starts_at}")
        else:
            logger.info(f"⏳ Старая подписка юзера {user.id} уже истекла. Активируем новую с текущего момента.")
    else:
        logger.info(f"⏳ Новая активация подписки для юзера {user.id} на {days_to_add} дней.")

    # Создаем новую запись подписки в истории со статусом "provisioning"
    subscription = Subscription(
        user_id=user.id,
        tariff_slug=attempt.tariff_slug,
        status="provisioning",
        starts_at=starts_at,
        expires_at=expires_at
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    logger.info(f"📝 Создана запись подписки {subscription.id} (До: {expires_at}) в статусе provisioning")

    # === [ИЗМЕНЕНИЕ] Шаг 6. Фоновый воркер активации ===
    # Вместо константного user.email передаем attempt.email (там может быть заглушка @ulysses.internal)
    background_tasks.add_task(
        provision_and_notify,
        subscription_id=subscription.id,
        to_email=attempt.email,
        hiddify_uuid=str(user.hiddify_uuid)
    )

    return {
        "status": "provisioning",
        "hiddify_uuid": str(user.hiddify_uuid),
        "message": "Оплата подтверждена. Срок подписки обновлен."
    }


@app.get("/api/billing/subscription/{hiddify_uuid}")
async def get_subscription_status(
    hiddify_uuid: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Получение статуса последней подписки по UUID пользователя.
    """
    # Преобразуем строку в валидный объект UUID для безопасного нативного сравнения в PG
    try:
        target_uuid = uuid.UUID(hiddify_uuid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Чистый поиск пользователя по его UUID без использования сырого CAST
    user_result = await db.execute(
        select(User).where(User.hiddify_uuid == target_uuid)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User with this VPN profile not found")

    # Берём его самую свежую подписку
    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    subscription = sub_result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription history is empty for this user")

    return subscription.to_dict()


@app.post("/api/billing/retry-provisioning/{subscription_id}")
async def retry_provisioning(
    subscription_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Ручной повтор provisioning (для администратора)"""
    manager = ProvisioningManager(db)
    success = await manager.provision_subscription(subscription_id)

    if success:
        return {"status": "activated", "subscription_id": subscription_id}
    else:
        return {
            "status": "failed",
            "subscription_id": subscription_id,
            "message": "Не удалось активировать. Проверьте логи бэкенда."
        }

@app.get("/api/admin/stats")
async def get_admin_stats(
    include_users: bool = False,  # <-- ДОБАВЛЯЕМ ФЛАГ
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для администратора: получение общей статистики системы.
    """
    # 1. Считаем общее количество пользователей
    total_users_result = await db.execute(select(func.count()).select_from(User))
    total_users = total_users_result.scalar_one()

    # 2. Считаем активные подписки
    active_subs_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status == 'active'
        )
    )
    active_subs = active_subs_result.scalar_one()

    # 3. Считаем подписки в обработке
    pending_subs_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status.in_(['pending_payment', 'provisioning'])
        )
    )
    pending_subs = pending_subs_result.scalar_one()

    response_data = {
        "total_users": total_users,
        "active_subscriptions": active_subs,
        "pending_subscriptions": pending_subs
    }

    # Если CLI запрашивает список пользователей
    if include_users:
        # Делаем выборку пользователей (адаптируйте имена полей, если они отличаются)
        users_result = await db.execute(select(User))
        users_rows = users_result.scalars().all()

        users_list = []
        for u in users_rows:
            users_list.append({
                "tg_user_id": getattr(u, "tg_user_id", None), # Строго имя из БД
                "email": getattr(u, "email", None),
                "status": getattr(u, "status", "active")  # Или любое другое поле статуса юзера
            })
        response_data["users"] = users_list

    return response_data

@app.get("/api/admin/check")
async def check_system(
    query: str = Query(None, description="UUID, email, tg_id или username для детализации"),
    db: AsyncSession = Depends(get_db)
):
    """
    Проверка аномалий системы: расхождения с Hiddify, зависшие подписки, мусор.
    Если передан query — возвращает детализацию по конкретной сущности.
    """
    # Если запросили конкретную сущность — детализация
    if query:
        return await _check_entity(query, db)

    # Иначе — полная сводка
    # Считаем технический мусор (инвойсы старше 48 часов)
    dirty_invoices_result = await db.execute(text("""
        SELECT COUNT(*) FROM payment_attempts
        WHERE status = 'pending' AND created_at < NOW() - INTERVAL '48 hours'
    """))
    dirty_invoices = dirty_invoices_result.scalar_one()

    # Ищем подписки со статусом 'provisioning_failed'
    failed_provisioning_result = await db.execute(text("""
        SELECT u.email, u.tg_username, s.id, s.tariff_slug, s.provisioning_error
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.status = 'provisioning_failed'
    """))
    failed_subs = [
        {"email": r[0], "tg": r[1], "sub_id": r[2], "tariff": r[3], "error": r[4]}
        for r in failed_provisioning_result.fetchall()
    ]

    # Получаем расхождения статусов через общую функцию
    status_mismatches = await _get_status_mismatches(db)

    # Сканируем Hiddify на критические аномалии (орфаны)
    hiddify_anomalies = []

    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                hiddify_users = response.json()
                hiddify_map = {str(u.get("uuid", "")).lower(): u for u in hiddify_users}

                db_data_result = await db.execute(text("""
                    SELECT DISTINCT ON (u.id) u.hiddify_uuid, u.email, s.status, s.expires_at, u.id
                    FROM users u
                    LEFT JOIN subscriptions s ON s.user_id = u.id
                    ORDER BY u.id, s.expires_at DESC
                """))

                now = datetime.utcnow()

                for row in db_data_result.fetchall():
                    uuid_raw, email, db_status, expires_at, user_id = row
                    if not uuid_raw:
                        continue

                    uuid_str = str(uuid_raw).lower()
                    in_hiddify = uuid_str in hiddify_map

                    if not in_hiddify:
                        expires_naive = expires_at.replace(tzinfo=None) if expires_at and expires_at.tzinfo else expires_at
                        db_is_active = db_status == "active" and expires_naive and expires_naive > now

                        if db_is_active:
                            hiddify_anomalies.append({
                                "type": "missing_in_hiddify",
                                "uuid": uuid_str,
                                "email": email or f"User {user_id}",
                                "details": "Активен в биллинге, но отсутствует профиль в Hiddify"
                            })

                # Орфанные записи в Hiddify (нет в БД)
                db_uuids = {str(r[0]).lower() for r in await db.execute(select(User.hiddify_uuid)) if r[0]}
                for hu_uuid in hiddify_map:
                    if hu_uuid not in db_uuids:
                        hd_user = hiddify_map[hu_uuid]
                        hiddify_anomalies.append({
                            "type": "unknown_in_db",
                            "uuid": hu_uuid,
                            "email": hd_user.get("name", "Unknown"),
                            "details": "Создан в Hiddify, отсутствует в биллинге",
                            "hiddify_info": {
                                "usage_gb": hd_user.get("current_usage_GB", 0),
                                "limit_gb": hd_user.get("usage_limit_GB", 0),
                                "enabled": hd_user.get("enable", False)
                            }
                        })

    except Exception as e:
        logger.error(f"🔴 Ошибка сканирования Hiddify: {e}")

    return {
        "summary": {
            "dirty_invoices_count": dirty_invoices,
            "failed_provisioning_count": len(failed_subs),
            "hiddify_anomalies_count": len(hiddify_anomalies),
            "status_mismatches_count": len(status_mismatches)
        },
        "failed_subscriptions": failed_subs,
        "anomalies": hiddify_anomalies,
        "status_mismatches": status_mismatches
    }



async def _check_entity(query: str, db: AsyncSession) -> dict:
    """Детализация по конкретной сущности (UUID, email, tg_id, username, имя в Hiddify)"""
    # Для email и UUID — ищем как есть. Для username — убираем @
    clean_query = str(query).strip().lower()
    clean_query_no_at = clean_query.replace("@", "")

    # 1. Пробуем найти в БД
    result = await db.execute(text("""
        SELECT u.hiddify_uuid, u.email, u.tg_user_id, u.tg_username, u.id,
               s.status, s.expires_at, s.tariff_slug, s.id as sub_id
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE CAST(u.hiddify_uuid AS TEXT) = :q
           OR LOWER(u.email) = :q
           OR CAST(u.tg_user_id AS TEXT) = :q
           OR LOWER(u.tg_username) = :q_no_at
        ORDER BY s.expires_at DESC
        LIMIT 1
    """), {"q": clean_query, "q_no_at": clean_query_no_at})

    row = result.fetchone()

    # 2. Проверяем Hiddify
    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    hiddify_data = None

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                hiddify_users = response.json()
                # Ищем по query (uuid или имя)
                for u in hiddify_users:
                    if str(u.get("uuid", "")).lower() == clean_query or u.get("name", "").lower() == clean_query:
                        hiddify_data = {
                            "uuid": u.get("uuid"),
                            "name": u.get("name"),
                            "enabled": u.get("enable"),
                            "usage_gb": u.get("current_usage_GB", 0),
                            "limit_gb": u.get("usage_limit_GB", 0),
                            "days_left": u.get("remaining_days", 0)
                        }
                        break
                # Если не нашли по query, но нашли в БД — ищем в Hiddify по UUID из БД
                if not hiddify_data and row and row[0]:
                    db_uuid = str(row[0]).lower()
                    for u in hiddify_users:
                        if str(u.get("uuid", "")).lower() == db_uuid:
                            hiddify_data = {
                                "uuid": u.get("uuid"),
                                "name": u.get("name"),
                                "enabled": u.get("enable"),
                                "usage_gb": u.get("current_usage_GB", 0),
                                "limit_gb": u.get("usage_limit_GB", 0),
                                "days_left": u.get("remaining_days", 0)
                            }
                            break
    except Exception as e:
        logger.error(f"Ошибка запроса Hiddify: {e}")

    # 3. Если нашли в Hiddify, но не нашли в БД — ищем в БД по UUID из Hiddify
    if not row and hiddify_data:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, u.tg_user_id, u.tg_username, u.id,
                   s.status, s.expires_at, s.tariff_slug, s.id as sub_id
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE CAST(u.hiddify_uuid AS TEXT) = :q
            ORDER BY s.expires_at DESC
            LIMIT 1
        """), {"q": hiddify_data["uuid"].lower()})
        row = result.fetchone()

    if not row and not hiddify_data:
        raise HTTPException(status_code=404, detail="Сущность не найдена ни в биллинге, ни в Hiddify")

    return {
        "found_in_db": row is not None,
        "found_in_hiddify": hiddify_data is not None,
        "account": {
            "id": row[4] if row else None,
            "email": row[1] if row else ("Бот (без почты)" if row and row[2] and not row[1] else "—"),
            "tg_user_id": row[2] if row else None,
            "tg_username": row[3] if row else None,
            "hiddify_uuid": str(row[0]) if row else None
        } if row else None,
        "subscription": {
            "id": row[8] if row else None,
            "status": row[5] if row else None,
            "expires_at": row[6].isoformat() if row and row[6] else None,
            "tariff_slug": row[7] if row else None
        } if row else None,
        "hiddify_profile": hiddify_data,
        "anomaly": _classify_anomaly(row, hiddify_data)
    }

def _classify_anomaly(db_row, hiddify_data) -> str | None:
    """Определяет тип аномалии"""
    if db_row and not hiddify_data:
        return "missing_in_hiddify"
    elif not db_row and hiddify_data:
        return "unknown_in_db"
    elif db_row and hiddify_data:
        db_status = db_row[5]
        hd_enabled = hiddify_data.get("enabled", False)
        if db_status == "active" and not hd_enabled:
            return "should_be_enabled"
        elif db_status != "active" and hd_enabled:
            return "should_be_disabled"
    return None



async def _get_status_mismatches(db: AsyncSession) -> list:
    """Внутренняя функция: получить расхождения статусов с Hiddify"""
    status_mismatches = []

    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)
            if response.status_code == 200:
                hiddify_users = response.json()
                hiddify_map = {str(u.get("uuid", "")).lower(): u for u in hiddify_users}

                db_data_result = await db.execute(text("""
                    SELECT DISTINCT ON (u.id) u.hiddify_uuid, u.email, s.status, s.expires_at
                    FROM users u
                    LEFT JOIN subscriptions s ON s.user_id = u.id
                    ORDER BY u.id, s.expires_at DESC
                """))

                now = datetime.utcnow()

                for row in db_data_result.fetchall():
                    uuid_raw, email, db_status, expires_at = row
                    if not uuid_raw:
                        continue

                    uuid_str = str(uuid_raw).lower()
                    if uuid_str not in hiddify_map:
                        continue

                    hd_user = hiddify_map[uuid_str]
                    hd_enabled = hd_user.get("enable", False)

                    expires_naive = expires_at.replace(tzinfo=None) if expires_at and expires_at.tzinfo else expires_at
                    db_is_active = db_status == "active" and expires_naive and expires_naive > now

                    if db_is_active and not hd_enabled:
                        status_mismatches.append({
                            "uuid": uuid_str, "email": email or "—",
                            "issue": "Должен быть включен, но выключен в Hiddify", "action": "enable"
                        })
                    elif not db_is_active and hd_enabled:
                        status_mismatches.append({
                            "uuid": uuid_str, "email": email or "—",
                            "issue": "Должен быть выключен (истек), но активен в Hiddify", "action": "disable"
                        })

    except Exception as e:
        logger.error(f"Ошибка в _get_status_mismatches: {e}")

    return status_mismatches

@app.post("/api/admin/fix/sync")
async def fix_sync_hiddify(db: AsyncSession = Depends(get_db)):
    """
    Синхронизация статусов с Hiddify: исправление расхождений тумблеров.
    """
    from app.provisioning_service import HiddifyProvisioner
    provisioner = HiddifyProvisioner()

    mismatches = await _get_status_mismatches(db)

    fixed = 0
    for m in mismatches:
        if m["action"] == "enable":
            success = await provisioner.enable_user(m["uuid"])
        else:
            success = await provisioner.disable_user(m["uuid"])
        if success:
            fixed += 1

    return {
        "status": "success",
        "fixed_hiddify_statuses": fixed
    }



@app.post("/api/user/unlink-telegram")
async def unlink_telegram_account(
    payload: LinkTelegramRequest, # Используем уже готовую модель, где есть tg_user_id
    db: AsyncSession = Depends(get_db)
):
    """
    Удаление привязки Telegram-аккаунта (разлогин из бота).
    """
    logger.info(f"🚪 [LOGOUT] Запрос на отвязку Telegram ID: {payload.tg_user_id}")

    result = await db.execute(text("""
        UPDATE users
        SET tg_user_id = NULL, tg_username = NULL
        WHERE tg_user_id = :tg_id
    """), {"tg_id": payload.tg_user_id})

    await db.commit()
    logger.info(f"✅ Telegram ID {payload.tg_user_id} успешно отвязан от всех профилей.")
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/billing/tariffs")
async def get_tariffs_endpoint():
    """
    Открытый эндпоинт для получения актуальной тарифной сетки.
    Используется ботом и фронтендом сайта.
    """
    try:
        tariffs_path = Path(__file__).parent / "tariffs.json"
        with open(tariffs_path, "r", encoding="utf-8") as f:
            tariffs = json.load(f)
        return tariffs
    except Exception as e:
        logger.error(f"❌ Ошибка при чтении тарифов для API: {e}")
        raise HTTPException(status_code=500, detail="Unable to load tariffs")

@app.get("/api/billing/invoice-status/{order_id}")
async def get_invoice_status(
    order_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Проверка статуса инвойса для бота.
    """
    try:
        invoice_id = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    result = await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.id == invoice_id)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Получаем информацию о подписке, если есть
    subscription_info = None
    if attempt.user_id:
        sub_result = await db.execute(text("""
            SELECT id, status, expires_at, tariff_slug
            FROM subscriptions
            WHERE user_id = :user_id
            ORDER BY expires_at DESC
            LIMIT 1
        """), {"user_id": attempt.user_id})
        sub_row = sub_result.fetchone()
        if sub_row:
            subscription_info = {
                "subscription_id": sub_row[0],
                "status": sub_row[1],
                "expires_at": sub_row[2].isoformat() if sub_row[2] else None,
                "tariff_slug": sub_row[3]
            }

    return {
        "status": attempt.status,  # pending, success, failed
        "order_id": str(attempt.id),
        "amount": float(attempt.amount),
        "tariff_slug": attempt.tariff_slug,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        "subscription": subscription_info
    }


# Healthcheck
# app/main.py - обновить healthcheck

@app.get("/health")
async def health_check():
    """Healthcheck для мониторинга"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Проверка БД
    try:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = "error"
        logger.error(f"Healthcheck DB error: {e}")

    # Быстрая проверка Hiddify
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
            r = await client.head(
                settings.HIDDIFY_API_URL,
                headers={"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
            )
            if r.status_code in [200, 401, 403]:
                health_status["checks"]["hiddify_api"] = "ok"
            else:
                health_status["checks"]["hiddify_api"] = f"status_{r.status_code}"
    except Exception as e:
        health_status["checks"]["hiddify_api"] = "error"
        logger.error(f"Healthcheck Hiddify error: {e}")

    # Проверка памяти
    import psutil
    import os
    mem = psutil.Process(os.getpid()).memory_info()
    if mem.rss > 500 * 1024 * 1024:
        health_status["checks"]["memory"] = "warning"
    else:
        health_status["checks"]["memory"] = "ok"

    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status

# Метрики
@app.get("/metrics")
async def get_metrics():
    """
    Простые метрики в JSON.
    Можно подключить к Grafana через JSON API plugin.
    """
    return metrics.get_all_metrics()

# Быстрый healthcheck для балансировщика (легкий, без проверок)
@app.get("/ping")
async def ping():
    """Легкий пинг для load balancer"""
    return {"status": "pong", "time": datetime.utcnow().isoformat()}

# Создаем директорию для логов
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

# Форматтер
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Файловый handler с ротацией (10MB, 5 файлов)
file_handler = RotatingFileHandler(
    log_dir / "ulysses.log",
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

# Консольный handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.WARNING)  # В консоль только WARNING и выше

# Настраиваем корневой logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Отключаем лишние логи
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('aiosmtplib').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info("🚀 Ulysses VPN Billing API starting...")

@app.get("/api/admin/system")
async def get_backend_system_status():
    """
    Эндпоинт системного мониторинга: возвращает JSON из утилитарного модуля.
    """
    metrics = await collect_system_metrics()
    return metrics

@app.post("/api/admin/fix/process-pending")
async def fix_process_pending(db: AsyncSession = Depends(get_db)):
    """Обработка pending подписок (для cron)"""
    manager = ProvisioningManager(db)
    processed = await manager.process_pending_provisioning(limit=20)
    return {"status": "ok", "processed": processed}

@app.post("/api/admin/fix/cleanup-invoices")
async def fix_cleanup_invoices(db: AsyncSession = Depends(get_db)):
    """Очистка старых инвойсов (для cron)"""
    result = await db.execute(text("""
        DELETE FROM payment_attempts
        WHERE status = 'pending' AND created_at < NOW() - INTERVAL '48 hours'
    """))
    await db.commit()
    return {"status": "ok", "deleted": result.rowcount}


@app.get("/api/bot/state")
async def get_bot_state(
    tg_user_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Возвращает состояние бота и приветственное сообщение."""

    # Ищем пользователя
    result = await db.execute(text("""
        SELECT s.status, s.expires_at
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        WHERE u.tg_user_id = :tg_id
        ORDER BY s.expires_at DESC
        LIMIT 1
    """), {"tg_id": tg_user_id})
    row = result.fetchone()

    # Новый пользователь
    if not row:
        return {
            "state": "new",
            "message": get_message("welcome_new"),
            "keyboard": "tariffs"
        }

    db_status, db_expires_at = row

    # Считаем дни
    now = datetime.utcnow()
    days_left = 0
    if db_expires_at:
        expires_naive = db_expires_at.replace(tzinfo=None) if db_expires_at.tzinfo else db_expires_at
        days_left = max(0, (expires_naive - now).days)

    is_active = db_status in ["active", "provisioning"] and days_left > 0

    # Активна
    if is_active and days_left > 5:
        return {
            "state": "active",
            "message": get_message("welcome_active"),
            "keyboard": "active"
        }

    # Истекает сегодня
    if is_active and days_left == 0:
        return {
            "state": "expiring_today",
            "message": get_message("welcome_expiring_today"),
            "keyboard": "renew"
        }

    # Истекает
    if is_active and days_left <= 5:
        return {
            "state": "expiring",
            "message": get_message("welcome_expiring", days=days_left),
            "keyboard": "renew"
        }

    # Истекла
    return {
        "state": "expired",
        "message": get_message("welcome_expired"),
        "keyboard": "renew"
    }

@app.get("/api/user/balance")
async def get_user_balance(
    tg_user_id: int = Query(None, description="Telegram user ID"),
    hiddify_uuid: str = Query(None, description="Hiddify UUID"),
    email: str = Query(None, description="User email"),
    username: str = Query(None, description="Telegram username"), # Добавили поле
    db: AsyncSession = Depends(get_db)
):
    uuid = None
    email_db = None
    db_expires_at = None
    db_status = None

    # Новые поля для админской панели
    user_id = None
    tg_id_db = None
    tg_username_db = None

    # 1. Поиск по Telegram Username
    if username:
        # Убираем символ @, если админ ввел его по привычке
        clean_username = str(username).lower().replace("@", "").strip()
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE LOWER(u.tg_username) = :username
            ORDER BY s.expires_at DESC
            LIMIT 1
        """), {"username": clean_username})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]), row[1], row[2], row[3], row[4], row[5], row[6]

    # 2. Поиск по email
    elif email:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE LOWER(u.email) = :email
            ORDER BY s.expires_at DESC
            LIMIT 1
        """), {"email": str(email).lower().strip()})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]), row[1], row[2], row[3], row[4], row[5], row[6]

    # 3. Поиск по hiddify_uuid
    elif hiddify_uuid:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE CAST(u.hiddify_uuid AS TEXT) = :uuid
            ORDER BY s.expires_at DESC
            LIMIT 1
        """), {"uuid": str(hiddify_uuid).lower().strip()})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]), row[1], row[2], row[3], row[4], row[5], row[6]

    # 4. Поиск по tg_user_id
    elif tg_user_id:
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id
            ORDER BY s.expires_at DESC
            LIMIT 1
        """), {"tg_id": tg_user_id})
        row = result.fetchone()
        if row:
            uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]), row[1], row[2], row[3], row[4], row[5], row[6]

    # Сценарий 1: Пользователь вообще не зарегистрирован в системе
    if not uuid:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Высчитываем оставшиеся дни по нашей локальной базе данных
    now = datetime.utcnow()
    days_left = 0
    if db_expires_at:
        expires_naive = db_expires_at.replace(tzinfo=None) if db_expires_at.tzinfo else db_expires_at
        days_left = max(0, (expires_naive - now).days)

    # Дефолтная структура трафика на случай сбоя API панели Hiddify
    traffic_data = {
        "used_gb": 0.0,
        "total_gb": 0.0,
        "remaining_gb": 0.0,
        "percent": 0.0
    }

    # Подписка считается активной, если в БД статус active/provisioning и дни не истекли
    is_active = (db_status in ["active", "provisioning"]) and days_left > 0

    # Запрашиваем живые данные по потреблению трафика из Hiddify
    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(settings.HIDDIFY_API_URL, headers=headers)

            if response.status_code == 200:
                users_list = response.json()
                target = None

                for u in users_list:
                    if str(u.get("uuid", "")).lower() == uuid.lower():
                        target = u
                        break

                if target:
                    usage = float(target.get("current_usage_GB", 0))
                    total = float(target.get("usage_limit_GB", 0))

                    # Синхронизируем статус активности с панелью Hiddify
                    is_active = bool(target.get("enable", True)) and days_left > 0

                    remaining = max(0.0, total - usage)
                    pct = (usage / total * 100) if total > 0 else 0

                    traffic_data = {
                        "used_gb": round(usage, 2),
                        "total_gb": round(total, 2),
                        "remaining_gb": round(remaining, 2),
                        "percent": round(pct, 1)
                    }
                else:
                    logger.warning(f"⚠️ Ключ {uuid} активен в БД, но удален или отсутствует в самой панели Hiddify")
            else:
                logger.error(f"❌ Hiddify API вернул статус-код ошибки: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Ошибка связи с Hiddify API panel: {e}")
        # Защита: не падаем по 500/502, отдаем кэш БД, чтобы бот продолжал отвечать пользователю!

    return {
        "status": "active" if is_active else "disabled",
        "email": email_db if email_db else "Бот (Без почты)",
        "uuid": uuid,
        "traffic": traffic_data,
        "days_left": days_left,
        "is_active": is_active,
        # Передаем скрытые поля для админ-панели и CLI
        "admin_info": {
            "id": user_id,
            "tg_user_id": tg_id_db,
            "tg_username": tg_username_db
        }
    }

# Добавить в app/main.py
# В app/main.py

@app.post("/api/bot/action")
async def bot_action(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Единый эндпоинт для всех действий бота.
    """
    tg_user_id = payload.get("tg_user_id")
    action = payload.get("action")
    data = payload.get("payload", {})

    if not tg_user_id or not action:
        raise HTTPException(status_code=400, detail="tg_user_id and action required")

    actions = {
        "buy_tariff": _action_buy_tariff,
        "check_balance": _action_check_balance,
        "show_about": _action_show_about,
        "show_rules": _action_show_rules,
        "show_support": _action_show_support,
    }

    handler = actions.get(action)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    return await handler(tg_user_id, data, db, background_tasks)


async def _action_buy_tariff(
    tg_user_id: int,
    data: dict,
    db: AsyncSession,
    background_tasks: BackgroundTasks
) -> dict:
    """Покупка тарифа — полная логика."""
    import json
    from pathlib import Path
    import uuid as uuid_lib

    tariff_slug = data.get("tariff_slug")
    tg_username = data.get("tg_username", "unknown")

    if not tariff_slug:
        raise HTTPException(status_code=400, detail="tariff_slug required")

    # 1. Загружаем тарифную сетку
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

    # 2. Ищем или создаём пользователя
    result = await db.execute(text("""
        SELECT id, hiddify_uuid, email FROM users WHERE tg_user_id = :tg_id LIMIT 1
    """), {"tg_id": tg_user_id})
    user_row = result.fetchone()

    if user_row:
        user_id, hiddify_uuid, email_db = user_row
        if not hiddify_uuid:
            hiddify_uuid = uuid_lib.uuid4()
            await db.execute(text("UPDATE users SET hiddify_uuid = :uuid WHERE id = :id"),
                             {"uuid": hiddify_uuid, "id": user_id})
        logger.info(f"👤 Существующий пользователь ID={user_id}")
    else:
        hiddify_uuid = uuid_lib.uuid4()
        insert_result = await db.execute(text("""
            INSERT INTO users (tg_user_id, tg_username, email, hiddify_uuid, created_at, updated_at)
            VALUES (:tg_id, :tg_username, NULL, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            "tg_id": tg_user_id,
            "tg_username": tg_username,
            "uuid": hiddify_uuid
        })
        user_id = insert_result.fetchone()[0]
        logger.info(f"✨ Новый пользователь ID={user_id}, UUID={hiddify_uuid}")

    bot_email_alias = f"tg_bot_{tg_user_id}@ulysses.internal"

    # 3. Создаём инвойс
    initial_status = "success" if amount == 0.00 else "pending"
    provider_tx = "tx_free_auto" if amount == 0.00 else None

    order_id = uuid_lib.uuid4()
    await db.execute(text("""
        INSERT INTO payment_attempts (id, email, user_id, tariff_slug, amount, currency, status, provider_tx_id, created_at, updated_at)
        VALUES (:id, :email, :user_id, :tariff_slug, :amount, 'RUB', :status, :tx_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """), {
        "id": order_id,
        "email": bot_email_alias,
        "user_id": user_id,
        "tariff_slug": tariff_slug,
        "amount": amount,
        "status": initial_status,
        "tx_id": provider_tx
    })
    logger.info(f"📝 Инвойс {order_id}, статус: {initial_status}")


    # 4. Бесплатный тариф — проверка на повтор + автоактивация
    if amount == 0.00:
        # Проверка: бесплатный тариф — только один раз
        free_check = await db.execute(text("""
            SELECT COUNT(*) FROM subscriptions
            WHERE user_id = :user_id AND tariff_slug = :slug
        """), {"user_id": user_id, "slug": tariff_slug})

        if free_check.scalar_one() > 0:
            return {
                "state": "error",
                "message": (
                    "⚠️ *Бесплатный период уже использован!*\n\n"
                    "Вы уже активировали тестовый доступ ранее.\n"
                    "Выберите платный тариф для продолжения."
                ),
                "keyboard": "tariffs"
            }

        # Автоактивация (существующая логика)
        sub_check = await db.execute(text("""
            SELECT expires_at FROM subscriptions WHERE user_id = :user_id ORDER BY expires_at DESC LIMIT 1
        """), {"user_id": user_id})
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
            VALUES (:user_id, :tariff_slug, 'provisioning', 'main', :starts_at, :expires_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            "user_id": user_id,
            "tariff_slug": tariff_slug,
            "starts_at": starts_at,
            "expires_at": expires_at
        })
        subscription_id = sub_result.fetchone()[0]

        await db.commit()

        background_tasks.add_task(
            provision_and_notify,
            subscription_id=subscription_id,
            to_email=bot_email_alias,
            hiddify_uuid=str(hiddify_uuid)
        )

        return {
            "state": "payment_free",
            "message": get_message("payment_free_activated"),
            "keyboard": "back"
        }

    # 5. Платный тариф — ожидание оплаты
    await db.commit()

    return {
        "state": "payment_pending",
        "message": get_message("payment_pending", order_id=str(order_id), amount=amount),
        "keyboard": "back",
        "order_id": str(order_id)
    }


async def _action_check_balance(
    tg_user_id: int,
    data: dict,
    db: AsyncSession,
    background_tasks: BackgroundTasks
) -> dict:
    """Проверка баланса."""
    try:
        # Вызываем напрямую с db, без HTTPException
        result = await db.execute(text("""
            SELECT u.hiddify_uuid, u.email, s.expires_at, s.status, u.id, u.tg_user_id, u.tg_username
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id = :tg_id
            ORDER BY s.expires_at DESC
            LIMIT 1
        """), {"tg_id": tg_user_id})
        row = result.fetchone()

        if not row:
            return {
                "state": "error",
                "message": get_message("error_unknown"),
                "keyboard": "back"
            }

        uuid, email_db, db_expires_at, db_status, user_id, tg_id_db, tg_username_db = str(row[0]) if row[0] else None, row[1], row[2], row[3], row[4], row[5], row[6]

        now = datetime.utcnow()
        days_left = 0
        if db_expires_at:
            expires_naive = db_expires_at.replace(tzinfo=None) if db_expires_at.tzinfo else db_expires_at
            days_left = max(0, (expires_naive - now).days)

        is_active = (db_status in ["active", "provisioning"]) and days_left > 0

        traffic_data = {"used_gb": 0.0, "total_gb": 0.0, "remaining_gb": 0.0, "percent": 0.0}

        # Запрос к Hiddify
        if uuid:
            try:
                async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                    response = await client.get(settings.HIDDIFY_API_URL, headers={"Hiddify-API-Key": settings.HIDDIFY_API_KEY})
                    if response.status_code == 200:
                        for u in response.json():
                            if str(u.get("uuid", "")).lower() == uuid.lower():
                                usage = float(u.get("current_usage_GB", 0))
                                total = float(u.get("usage_limit_GB", 0))
                                remaining = max(0.0, total - usage)
                                pct = (usage / total * 100) if total > 0 else 0
                                traffic_data = {
                                    "used_gb": round(usage, 2),
                                    "total_gb": round(total, 2),
                                    "remaining_gb": round(remaining, 2),
                                    "percent": round(pct, 1)
                                }
                                is_active = bool(u.get("enable", True)) and days_left > 0
                                break
            except Exception as e:
                logger.error(f"❌ Ошибка Hiddify в bot/action: {e}")

        return {
            "state": "balance",
            "message": "balance_data",
            "keyboard": "back",
            "balance": {
                "status": "active" if is_active else "disabled",
                "email": email_db if email_db else "Бот (Без почты)",
                "uuid": uuid,
                "traffic": traffic_data,
                "days_left": days_left,
                "is_active": is_active
            }
        }

    except Exception as e:
        logger.error(f"❌ check_balance error: {e}")
        return {
            "state": "error",
            "message": get_message("error_unknown"),
            "keyboard": "back"
        }


async def _action_show_about(tg_user_id, data, db, background_tasks) -> dict:
    return {"state": "info", "message": MD_TEXTS["service"], "keyboard": "back"}

async def _action_show_rules(tg_user_id, data, db, background_tasks) -> dict:
    return {"state": "info", "message": MD_TEXTS["rules"], "keyboard": "back"}

async def _action_show_support(tg_user_id, data, db, background_tasks) -> dict:
    return {"state": "info", "message": MD_TEXTS["support"], "keyboard": "back"}

@app.post("/api/admin/notify-expiring")
async def notify_expiring_subscriptions(db: AsyncSession = Depends(get_db)):
    """
    Отправляет уведомления пользователям с истекающей подпиской (1-3 дня).
    Вызывается раз в день через cron.
    """
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    # Ищем активные подписки с истечением через 1, 2, 3 дня
    for days in [1, 2, 3]:
        target_date = datetime.utcnow() + timedelta(days=days)
        result = await db.execute(text("""
            SELECT u.tg_user_id, u.tg_username, s.expires_at, s.tariff_slug
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.tg_user_id IS NOT NULL
              AND s.status = 'active'
              AND DATE(s.expires_at) = DATE(:target_date)
        """), {"target_date": target_date})

        for row in result.fetchall():
            tg_id, username, expires_at, tariff = row
            expires_str = expires_at.strftime("%d.%m.%Y") if expires_at else "N/A"

            msg_text = None
            if days == 1:
                msg_text = f"🔴 *Подписка истекает завтра!*\n\n📅 Дата: {expires_str}\n⚠️ Продлите доступ, чтобы не потерять соединение."
            elif days == 2:
                msg_text = f"🟡 *Подписка истекает через 2 дня*\n\n📅 Дата: {expires_str}\n🔔 Рекомендуем продлить доступ."
            else:
                msg_text = f"🟢 *Подписка истекает через 3 дня*\n\n📅 Дата: {expires_str}\n💡 Ещё есть время продлить."

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                        "chat_id": tg_id,
                        "text": msg_text,
                        "parse_mode": "Markdown"
                    })
                logger.info(f"✅ Уведомление отправлено tg_id={tg_id} (истекает через {days} дн.)")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки tg_id={tg_id}: {e}")

    return {"status": "ok", "message": "Expiring notifications sent"}

@app.delete("/api/admin/account")
async def delete_account(
    tg_user_id: int = Query(None),
    email: str = Query(None),
    uuid: str = Query(None),
    target: str = Query("all"),
    db: AsyncSession = Depends(get_db)
):
    # 1. Найти UUID
    hiddify_uuid = uuid
    user_id = None

    if not uuid:
        if tg_user_id:
            result = await db.execute(text("SELECT id, hiddify_uuid FROM users WHERE tg_user_id = :id"), {"id": tg_user_id})
        elif email:
            result = await db.execute(text("SELECT id, hiddify_uuid FROM users WHERE email = :e"), {"e": email})
        else:
            raise HTTPException(status_code=400, detail="tg_user_id, email or uuid required")

        row = result.fetchone()
        if row:
            user_id, hiddify_uuid = row[0], str(row[1]) if row[1] else None

    deleted_db = False
    deleted_hf = False

    # 2. Сначала удалить из Hiddify (по uuid)
    if target in ("all", "hiddify") and hiddify_uuid:
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                resp = await client.post(
                    settings.HIDDIFY_API_URL,
                    headers={
                        "Hiddify-API-Key": settings.HIDDIFY_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json={"action": "delete", "uuid": hiddify_uuid}
                )
                deleted_hf = resp.status_code == 200
        except Exception as e:
            logger.error(f"Ошибка удаления из Hiddify: {e}")

    # 3. Потом удалить из БД
    if target in ("all", "db") and user_id:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await db.commit()
        deleted_db = True
    elif target in ("all", "db") and tg_user_id:
        result = await db.execute(text("DELETE FROM users WHERE tg_user_id = :id RETURNING id"), {"id": tg_user_id})
        deleted_db = result.rowcount > 0
        await db.commit()

    return {
        "status": "deleted",
        "user_id": user_id,
        "deleted_db": deleted_db,
        "deleted_hiddify": deleted_hf
    }

@app.get("/api/admin/pay/info/{order_id}")
async def admin_pay_info(order_id: str, db: AsyncSession = Depends(get_db)):
    """Получить статус инвойса у платёжного шлюза"""
    # Проверяем, есть ли такой платёж в БД
    result = await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.id == order_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Инвойс не найден")

    # Запрашиваем статус у Enot
    invoice_info = await get_invoice_info(str(payment.id))

    # Добавляем локальные данные
    invoice_info["local_status"] = payment.status
    invoice_info["local_amount"] = payment.amount
    invoice_info["email"] = payment.email
    invoice_info["tariff_slug"] = payment.tariff_slug

    return invoice_info
