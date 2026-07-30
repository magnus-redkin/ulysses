# ulysses-backend/app/services/billing_gateways.py

# АРХИТЕКТУРА И ИНТЕРФЕЙС ПЛАТЕЖНЫХ ШЛЮЗОВ ULYSSES VPN
# Описывает базовый абстрактный класс BaseBillingGateway, изолирующий бизнес-логику
# от внешних API. Содержит Mock-реализацию для отладки прохождения транзакций в тестах
# и подготавливает структуру для интеграции боевого агрегатора Platega.

import logging
import hashlib
from abc import ABC, abstractmethod
from app.config import settings

logger = logging.getLogger(__name__)

class BaseBillingGateway(ABC):
    """
    Абстрактный интерфейс платежного шлюза.
    Каждый подключаемый агрегатор (Enot, Platega, Crypto) обязан реализовывать эти методы.
    """
    @abstractmethod
    async def create_invoice(self, order_id: str, amount: float, email: str, tariff_slug: str) -> str:
        """
        Генерирует счет в платежной системе.
        Возвращает полную готовую URL-ссылку на форму оплаты для клиента.
        """
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: dict, received_signature: str) -> bool:
        """
        Проверяет подлинность входящего вебхука на основе секретного ключа (Secret Key).
        Возвращает True, если подписи совпали, защищая кассу от подделок оплат.
        """
        pass


class MockBillingGateway(BaseBillingGateway):
    """
    Тестовый симуляционный шлюз.
    Используется в интеграционных тестах для мгновенной генерации фейковых ссылок оплаты.
    """
    async def create_invoice(self, order_id: str, amount: float, email: str, tariff_slug: str) -> str:
        logger.info(f"🧪 [MOCK GATEWAY] Генерация тестового инвойса #{order_id} на сумму {amount} руб.")
        # Возвращает симуляционную ссылку, которая ведет на локальный эндпоинт-заглушку
        return f"http://127.0.0{order_id}&amount={amount}"

    def verify_webhook_signature(self, payload: dict, received_signature: str) -> bool:
        logger.info("🧪 [MOCK GATEWAY] Верификация подписи тестового вебхука...")
        # В тестовом окружении мы можем использовать упрощенную сверку или сверять по статическому токену
        expected_signature = hashlib.md5(f"{payload.get('order_id')}:mock_secret".encode()).hexdigest()
        return expected_signature == received_signature
