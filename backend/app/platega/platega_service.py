import json
import os
import asyncio
import uuid  # <-- ИСПРАВЛЕНО
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import Response, status
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.hiddify_client import HiddifyProvisioner
from app.platega.platega import Platega, PlategaCallback
from backend.app.services.activation_manager import get_tariffs

from pathlib import Path
# Вычисляем корень backend динамически
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
json_paths = [
    str(BACKEND_ROOT / "app" / "tariffs.json"),
    "app/tariffs.json"
]


class PlategaPaymentService:
    """Асинхронный провайдер для работы с SDK Platega.io."""
    def __init__(self):
        self.client = Platega(
            merchant_id=settings.PLATEGA_MERCHANT_ID,
            secret=settings.PLATEGA_API
        )

    async def create_invoice_link(
        self,
        amount: float,
        attempt_id: str,
        tariff_name: str,
        currency: Optional[str] = None,
        method: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Генерация платежной ссылки с гарантированным заполнением обязательных полей SDK."""
        base_domain = "ulysses.best"

        # ИСПРАВЛЕНО: Если параметры не переданы, подставляем базовый мульти-контур.
        # Метод 11 (CARD_ACQUIRING) или 10 обычно открывают стандартную форму,
        # где Platega сама выводит кнопки СБП/карт/других шлюзов на основе настроек вашего терминала.
        final_currency = str(currency).upper().strip() if currency else "RUB"
        final_method = int(method) if method else 11  # 11 = METHOD_CARD_ACQUIRING (универсальный эквайринг)

        def _sync_call():
            # Передаем параметры строго в соответствии с позиционными требованиями SDK
            return self.client.create_payment(
                amount=float(amount),
                currency=final_currency,
                payment_method=final_method,
                description=f"Оплата подписки Ulysses VPN: {tariff_name}",
                return_url=f"https://{base_domain}/payment/success",
                failed_url=f"https://{base_domain}/payment/fail",
                payload=str(attempt_id)
            )

        try:
            return await asyncio.to_thread(_sync_call)
        except Exception as e:
            print(f"❌ [PLATEGA SERVICE] Ошибка при генерации ссылки: {e}")
            return None



class PlategaWebhookProcessor:
    """
    🔒 ЧУВСТВИТЕЛЬНЫЙ ЯДЕРНЫЙ КОНТУР БИЛЛИНГА
    Выполняет валидацию, парсинг тарифов из JSON и начисление дней.
    """
    def __init__(self):
        # 🟢 ИСПРАВЛЕНО: Никакого хардкода путей и повторного чтения файлов!
        # Используем наш готовый централизованный кэширующий метод
        self.tariffs = get_tariffs()

    async def process_incoming_callback(self, headers: dict, body_str: str) -> Response:
        """Атомарная бизнес-логика обработки успешного платежа."""
        callback = PlategaCallback(
            merchant_id=settings.PLATEGA_MERCHANT_ID,
            secret=settings.PLATEGA_API
        )

        # 1. Валидация подписи через SDK
        if not callback.validate_raw(headers=headers, body=body_str):
            print(f"🚨 [WEBHOOK VALIDATION FAILED] {callback.get_validation_error()}")
            return Response(content="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

        raw_attempt_id = callback.get_order_id()
        platega_tx_id = callback.get_transaction_id()

        if not callback.is_success():
            return Response(content="OK", status_code=status.HTTP_200_OK)

        # ИСПРАВЛЕНО: Безопасное приведение строки заказа к UUID объекту для PostgreSQL
        try:
            attempt_uuid = uuid.UUID(str(raw_attempt_id).strip())
        except (ValueError, TypeError):
            print(f"❌ [WEBHOOK ERROR] Invalid UUID format: {raw_attempt_id}")
            return Response(content="Invalid UUID format", status_code=status.HTTP_400_BAD_REQUEST)

        # 2. Быстрая СУБД транзакция (Защита от состояния гонки и дедлоков)
        async with AsyncSessionLocal() as session:
            try:
                res_inv = await session.execute(
                    text("SELECT status, user_id, tariff_slug FROM payment_attempts WHERE id = :id FOR UPDATE"),
                    {"id": attempt_uuid}
                )
                invoice = res_inv.fetchone()

                if not invoice:
                    return Response(content="Invoice Not Found", status_code=status.HTTP_404_NOT_FOUND)

                inv_status, user_id, tariff_slug = invoice

                if inv_status == "success":
                    return Response(content="Already Processed", status_code=status.HTTP_200_OK)

                # Переводим в промежуточный статус и мгновенно коммитим, освобождая СУБД воркеры
                await session.execute(
                    text("UPDATE payment_attempts SET status = 'processing', updated_at = NOW() WHERE id = :id"),
                    {"id": attempt_uuid}
                )
                await session.commit()

            except Exception as err:
                await session.rollback()
                print(f"💥 [CRITICAL ERROR] Сбой первичной транзакции вебхука: {err}")
                return Response(content="Internal Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 3. Изолированная сетевая и финальная логика за пределами мертвой блокировки
        try:
            async with AsyncSessionLocal() as session:
                clean_tariff = tariff_slug.lower().strip()
                days_to_add = 30
                if clean_tariff in self.tariffs:
                    days_to_add = self.tariffs[clean_tariff]["days"]

                res_usr = await session.execute(
                    text("SELECT tg_user_id, hiddify_uuid FROM users WHERE id = :uid"), {"uid": user_id}
                )
                tg_id, hiddify_uuid = res_usr.fetchone()
                hiddify_uuid_str = str(hiddify_uuid)
                now = datetime.now(timezone.utc)

                res_sub = await session.execute(
                    text("SELECT expires_at FROM subscriptions WHERE user_id = :uid AND status = 'active' LIMIT 1"),
                    {"uid": user_id}
                )
                sub_row = res_sub.fetchone()

                if sub_row and sub_row[0] and sub_row[0] > now:
                    new_expires = sub_row[0] + timedelta(days=days_to_add)
                else:
                    new_expires = now + timedelta(days=days_to_add)

                total_remaining_days = (new_expires - now).days

                # Запрос к инфраструктуре Hiddify
                provisioner = HiddifyProvisioner()
                hiddify_success = await provisioner.create_user(
                    uuid=hiddify_uuid_str,
                    name=f"tg_{tg_id}" if tg_id else f"id_{user_id}",
                    package_days=total_remaining_days if total_remaining_days > 0 else days_to_add,
                    usage_limit_gb=500
                )
                # if hiddify_success:
                #     await provisioner.enable_user(hiddify_uuid_str)

                # Фиксация успехов в БД
                status_str = "active" if hiddify_success else "provisioning"

                await session.execute(
                    text("UPDATE payment_attempts SET status = 'success', provider_tx_id = :tx, updated_at = NOW() WHERE id = :id"),
                    {"tx": platega_tx_id, "id": attempt_uuid}
                )

                if sub_row:
                    await session.execute(
                        text("UPDATE subscriptions SET expires_at = :exp, status = :status, updated_at = NOW() WHERE user_id = :uid AND status = 'active'"),
                        {"exp": new_expires, "status": status_str, "uid": user_id}
                    )
                else:
                    # ИСПРАВЛЕНО: Добавлены все обязательные поля СУБД ограничений
                    await session.execute(
                        text("""
                            INSERT INTO subscriptions (user_id, tariff_slug, status, starts_at, expires_at, activated_at, node_id, created_at, updated_at)
                            VALUES (:uid, :tariff, :status, NOW(), :exp, NOW(), 'main', NOW(), NOW())
                        """),
                        {"uid": user_id, "tariff": tariff_slug, "status": status_str, "exp": new_expires}
                    )

                await session.commit()

                if tg_id:
                    try:
                        from app.services.telegram_bot import send_telegram_message
                        msg = f"💳 <b>Оплата получена!</b>\n\nПодписка продлена на <b>{days_to_add} дней</b>.\n📅 До: <code>{new_expires.strftime('%Y-%m-%d %H:%M')}</code> UTC. 🚀"
                        await send_telegram_message(tg_id=tg_id, text=msg)
                    except:
                        pass

                return Response(content="OK", status_code=status.HTTP_200_OK)

        except Exception as err:
            print(f"💥 [CRITICAL ERROR] Сбой процессинга активации: {err}")
            return Response(content="Activation Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
