from decimal import Decimal
from pydantic import BaseModel


class TuitionInfo(BaseModel):
    tuition_id: str
    student_id: str
    student_name: str
    term: str
    amount: Decimal
    status: str  # UNPAID | RESERVED | PAID


class ReserveRequest(BaseModel):
    transaction_id: str


class CommitRequest(BaseModel):
    transaction_id: str
