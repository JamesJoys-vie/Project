from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, Boolean, JSON, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from shared.db import new_id

# Transaction lifecycle
PENDING_OTP, PROCESSING, SUCCESS, FAILED, CANCELLED, EXPIRED = (
    "PENDING_OTP", "PROCESSING", "SUCCESS", "FAILED", "CANCELLED", "EXPIRED")


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_account_balance_nonneg"),)  # last line of defence vs overdraft
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)  # logical ref to user-service
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    payer_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    student_id: Mapped[str] = mapped_column(String(20), nullable=False)
    tuition_id: Mapped[str] = mapped_column(String(36), nullable=False)  # logical ref to tuition-service
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=PENDING_OTP)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False, unique=True)  # one debit per txn
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # DEBIT
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OutboxEvent(Base):
    """Transactional outbox: written in the same DB transaction as the payment, relayed to Redis Streams by app/workers/outbox_relay.py."""
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
