from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.schemas.payment import (AccountOut, InitiateTransactionRequest, TransactionOut,
                                 VerifyOtpRequest, TransactionResult)

router = APIRouter()


@router.get("/accounts/me", response_model=AccountOut)
def my_account(x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """TODO: balance of the authenticated user's account."""
    raise HTTPException(501, "Not implemented")


@router.get("/transactions", response_model=list[TransactionOut])
def history(x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """TODO: transaction history of the authenticated user (newest first)."""
    raise HTTPException(501, "Not implemented")


@router.post("/transactions", response_model=TransactionOut, status_code=201,
             responses={400: {"description": "Bad input"}, 409: {"description": "Tuition already paid/reserved"},
                        422: {"description": "Insufficient balance"}})
def initiate(body: InitiateTransactionRequest, x_user_id: str = Header(...),
             idempotency_key: str = Header(..., alias="Idempotency-Key"), db: Session = Depends(get_db)):
    """SAGA step 1. TODO:
    1) if idempotency_key exists -> return the original transaction (no side effects);
    2) fetch tuition (tuition-service), require UNPAID and balance >= amount;
    3) reserve tuition (atomic conditional UPDATE in tuition-service) -> 409 if lost the race;
    4) insert Transaction(PENDING_OTP); request OTP from otp-service (otp-service emits `otp.requested` on Redis Streams -> notification-service emails the payer)."""
    raise HTTPException(501, "Not implemented")


@router.post("/transactions/{transaction_id}/verify-otp", response_model=TransactionResult,
             responses={400: {"description": "Invalid/expired OTP"}, 409: {"description": "Conflict"}, 410: {"description": "Transaction expired"}})
def verify_otp(transaction_id: str, body: VerifyOtpRequest, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """SAGA step 2. TODO: verify OTP (single-use) then in ONE DB transaction:
    SELECT ... FOR UPDATE account -> re-check balance -> debit -> insert LedgerEntry -> mark SUCCESS -> insert OutboxEvent;
    call tuition-service commit; on any failure compensate (release reservation, mark FAILED)."""
    raise HTTPException(501, "Not implemented")


@router.post("/transactions/{transaction_id}/resend-otp", status_code=200, responses={429: {"description": "Too many requests"}})
def resend_otp(transaction_id: str, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """TODO: issue a new OTP (invalidates the previous one for this transaction), rate limited."""
    raise HTTPException(501, "Not implemented")


@router.post("/transactions/{transaction_id}/cancel", status_code=200)
def cancel(transaction_id: str, x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """TODO: cancel a PENDING_OTP transaction and release the tuition reservation."""
    raise HTTPException(501, "Not implemented")
