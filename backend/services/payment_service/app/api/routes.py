"""HTTP layer of payment-service. The saga logic lives in app/domain/saga.py."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.domain import saga
from app.domain.models import Account, Transaction
from app.schemas.payment import (AccountOut, InitiateTransactionRequest, TransactionOut,
                                 VerifyOtpRequest, TransactionResult, ResendOtpResult)

router = APIRouter()
HISTORY_LIMIT = 100


def _out(t: Transaction) -> TransactionOut:
    return TransactionOut(id=t.id, student_id=t.student_id, amount=t.amount, status=t.status,
                          failure_reason=t.failure_reason, created_at=t.created_at, completed_at=t.completed_at,
                          otp_expires_in=saga.otp_expires_in(t))


@router.get("/accounts/me", response_model=AccountOut, responses={404: {"description": "No account"}})
def my_account(x_user_id: str = Header(...), db: Session = Depends(get_db)):
    balance = db.scalar(select(Account.balance).where(Account.user_id == x_user_id))
    if balance is None:
        raise HTTPException(404, "No payment account for this user")
    return AccountOut(balance=balance)


@router.get("/transactions", response_model=list[TransactionOut])
def history(x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """Transaction history of the authenticated user (newest first)."""
    rows = db.scalars(select(Transaction).where(Transaction.payer_user_id == x_user_id)
                      .order_by(Transaction.created_at.desc(), Transaction.id).limit(HISTORY_LIMIT)).all()
    return [_out(t) for t in rows]


@router.post("/transactions", response_model=TransactionOut, status_code=201,
             responses={400: {"description": "Bad input"}, 404: {"description": "Student/tuition not found"},
                        409: {"description": "Tuition already paid/reserved"},
                        422: {"description": "Insufficient balance"}, 502: {"description": "Dependency down"}})
def initiate(body: InitiateTransactionRequest, x_user_id: str = Header(...),
             idempotency_key: str = Header(..., alias="Idempotency-Key"), db: Session = Depends(get_db)):
    """SAGA step 1: reserve the tuition, create a PENDING_OTP transaction, email an OTP.
    Re-sending the same Idempotency-Key returns the original transaction without side effects."""
    return _out(saga.initiate(db, x_user_id, idempotency_key, body.student_id))


@router.post("/transactions/{transaction_id}/verify-otp", response_model=TransactionResult,
             responses={400: {"description": "Invalid/expired OTP"}, 404: {"description": "Not found"},
                        409: {"description": "Conflict"}, 410: {"description": "Transaction expired"}})
def verify_otp(transaction_id: str, body: VerifyOtpRequest, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """SAGA step 2: verify OTP, debit, mark the tuition paid. Business outcomes come back as 200 with the
    transaction status: SUCCESS, FAILED (e.g. insufficient balance, see failure_reason) or PROCESSING (finishing)."""
    t = saga.verify(db, x_user_id, transaction_id, body.otp)
    return TransactionResult(transaction=_out(t), balance_after=saga.balance_after(db, t))


@router.get("/transactions/{transaction_id}", response_model=TransactionOut, responses={404: {"description": "Not found"}})
def get_transaction(transaction_id: str, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """Poll a single transaction (e.g. while it is PROCESSING, or to resume a PENDING_OTP one)."""
    return _out(saga.get_owned(db, transaction_id, x_user_id))


@router.post("/transactions/{transaction_id}/resend-otp", response_model=ResendOtpResult,
             responses={404: {"description": "Not found"}, 409: {"description": "Not waiting for OTP"},
                        410: {"description": "Transaction expired"}, 429: {"description": "Too many requests"}})
def resend_otp(transaction_id: str, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """New OTP (the previous one stops working); the transaction's OTP window restarts."""
    return ResendOtpResult(otp_expires_in=saga.resend_otp(db, x_user_id, transaction_id))


@router.post("/transactions/{transaction_id}/cancel", response_model=TransactionOut,
             responses={404: {"description": "Not found"}, 409: {"description": "Not cancellable"}})
def cancel(transaction_id: str, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """Cancel a PENDING_OTP transaction and release the tuition reservation."""
    return _out(saga.cancel(db, x_user_id, transaction_id))
