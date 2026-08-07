import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tg_user_id = Column(BigInteger, nullable=True, index=True)
    tg_username = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hiddify_uuid = Column(UUID(as_uuid=True), unique=True, nullable=True, default=uuid.uuid4)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payment_attempts = relationship("PaymentAttempt", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tariff_slug = Column(String(50), nullable=False)
    status = Column(String(50), default="pending_payment", index=True)

    starts_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    provisioning_attempts = Column(Integer, default=0)
    last_provisioning_at = Column(DateTime(timezone=True), nullable=True)
    provisioning_error = Column(Text, nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)

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

    tariff_slug = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")

    status = Column(String(50), default="pending", index=True)
    provider_tx_id = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="payment_attempts")
