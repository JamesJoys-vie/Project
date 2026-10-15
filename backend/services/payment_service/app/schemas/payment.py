from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class AccountOut(BaseModel):
    balance: Decimal


class InitiateTransactionRequest(BaseModel):
    student_id: str = Field(..., description="MSSV to pay for")
    term: str | None = None


class TransactionOut(BaseModel):
    id: str
    student_id: str
    amount: Decimal
    status: str
    failure_reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    otp_expires_in: int | None = None


class VerifyOtpRequest(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6)


class TransactionResult(BaseModel):
    transaction: TransactionOut
    balance_after: Decimal | None = None
