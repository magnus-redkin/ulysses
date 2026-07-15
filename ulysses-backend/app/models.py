import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tg_user_id = Column(BigInteger, nullable=True, index=True) # Источник истины (без уникальности БД)
    tg_username = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True) # Сделали NULLABLE

    # Бессмертный UUID для Hiddify переехал сюда (генерируется один раз для пользователя)
    hiddify_uuid = Column(UUID(as_uuid=True), unique=True, nullable=True, default=uuid.uuid4)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payment_attempts = relationship("PaymentAttempt", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Тариф
    tariff_slug = Column(String(50), nullable=False)

    # Статусы: pending_payment, provisioning, active, provisioning_failed, expired, cancelled
    status = Column(String(50), default="pending_payment", index=True)

    # Даты
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Provisioning поля
    provisioning_attempts = Column(Integer, default=0)
    last_provisioning_at = Column(DateTime, nullable=True)
    provisioning_error = Column(Text, nullable=True)
    activated_at = Column(DateTime, nullable=True)

    # Связи
    user = relationship("User", back_populates="subscriptions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tariff_slug": self.tariff_slug,
            "status": self.status,
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "provisioning_attempts": self.provisioning_attempts,
            "provisioning_error": self.provisioning_error,
        }


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Платеж
    tariff_slug = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")

    # Статус платежа
    status = Column(String(50), default="pending", index=True)
    provider_tx_id = Column(String(255), nullable=True)

    # Даты
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="payment_attempts")
