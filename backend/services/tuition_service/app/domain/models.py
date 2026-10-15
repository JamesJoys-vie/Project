from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from shared.db import new_id

UNPAID, RESERVED, PAID = "UNPAID", "RESERVED", "PAID"


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"
    student_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # MSSV
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Tuition(Base):
    """One liability per (student, term). Status moves UNPAID -> RESERVED -> PAID (or RESERVED -> UNPAID on release/expiry)."""
    __tablename__ = "tuitions"
    __table_args__ = (UniqueConstraint("student_id", "term", name="uq_tuition_student_term"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.student_id"), nullable=False)
    term: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=UNPAID)
    reserved_by_txn: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_by_txn: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # optimistic lock
