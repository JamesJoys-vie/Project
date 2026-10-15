"""Tuition payment saga, orchestrated by payment-service.

  initiate:  idempotency check -> tuition lookup + balance pre-check -> insert PENDING_OTP
             -> reserve tuition (tuition-service)            [compensation: mark FAILED]
             -> issue OTP (otp-service -> email via Streams) [compensation: release tuition, mark FAILED]
  verify:    OTP check (single-use) -> ONE MySQL txn: lock txn row, lock account row, re-check balance, debit,
             DEBIT ledger entry, status PROCESSING
             -> commit tuition (tuition-service)
                  ok        -> ONE MySQL txn: status SUCCESS + outbox `payment.completed`
                  409       -> ONE MySQL txn: refund (CREDIT ledger entry), status FAILED
                  no answer -> stays PROCESSING; workers/expiry_job.py retries (commit is idempotent)

Concurrency rules:
  * Every status change is conditional on the expected current status (row lock or `UPDATE ... WHERE status=`),
    so cancel / expiry / a second verify can never both win.
  * Lock order is always transaction row -> account row (fewer deadlocks); deadlocks and lock-wait timeouts
    that still happen are retried (`run_in_tx`).
  * Overdraft is impossible: the balance check and the debit happen under the account row lock
    (SELECT ... FOR UPDATE), and the CHECK (balance >= 0) constraint is the last line of defence.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from shared import events
from app.core.config import settings
from app.domain.models import (CANCELLED, CREDIT, DEBIT, EXPIRED, FAILED, PENDING_OTP, PROCESSING, SUCCESS,
                               Account, LedgerEntry, OutboxEvent, Transaction)
from app.repositories import clients
from app.repositories.clients import UpstreamError

log = logging.getLogger("payment.saga")
RETRYABLE_MYSQL_ERRORS = {1213, 1205}  # deadlock found / lock wait timeout exceeded
TX_ATTEMPTS = 3


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_in_tx(db: Session, fn, attempts: int = TX_ATTEMPTS):
    """Run fn(db) as one DB transaction and commit. Deadlock / lock timeout -> roll back and run fn again."""
    for attempt in range(1, attempts + 1):
        try:
            result = fn(db)
            db.commit()
            return result
        except OperationalError as e:
            db.rollback()
            code = e.orig.args[0] if e.orig is not None and e.orig.args else None
            if code not in RETRYABLE_MYSQL_ERRORS or attempt == attempts:
                raise
            log.warning("MySQL error %s, retrying transaction (%d/%d)", code, attempt, attempts)
            time.sleep(0.05 * 2 ** attempt)
        except Exception:
            db.rollback()
            raise


def _locked_txn(db: Session, txn_id: str) -> Transaction:
    return db.scalar(select(Transaction).where(Transaction.id == txn_id)
                     .with_for_update().execution_options(populate_existing=True))


def _locked_account(db: Session, account_id: str) -> Account:
    return db.scalar(select(Account).where(Account.id == account_id)
                     .with_for_update().execution_options(populate_existing=True))


def _transition(db: Session, txn_id: str, frm: str, to: str, reason: str | None = None) -> bool:
    """Compare-and-set the status; False if the transaction was no longer in `frm`."""
    def step(db):
        return db.execute(update(Transaction).where(Transaction.id == txn_id, Transaction.status == frm)
                          .values(status=to, failure_reason=reason, completed_at=utcnow())
                          .execution_options(synchronize_session=False)).rowcount == 1
    changed = run_in_tx(db, step)
    db.expire_all()
    return changed


def _release(t: Transaction) -> None:
    """Best effort: a hold that is not released expires on its own (tuition `reserved_until`)."""
    try:
        clients.release_tuition(t.tuition_id, t.id)
    except UpstreamError as e:
        log.warning("release of tuition %s for txn %s failed: %s", t.tuition_id, t.id, e)


def _payer(user_id: str) -> dict:
    try:
        return clients.get_user(user_id)
    except UpstreamError:
        raise HTTPException(502, "User service unavailable, try again")


def _is_overdue(t: Transaction) -> bool:
    return t.status == PENDING_OTP and t.expires_at is not None and t.expires_at <= utcnow()


def expire(db: Session, t: Transaction) -> bool:
    if _transition(db, t.id, PENDING_OTP, EXPIRED, "OTP was not confirmed in time"):
        _release(t)
        return True
    return False


def otp_expires_in(t: Transaction) -> int | None:
    if t.status != PENDING_OTP or t.expires_at is None:
        return None
    return max(int((t.expires_at - utcnow()).total_seconds()), 0)


def get_owned(db: Session, txn_id: str, user_id: str) -> Transaction:
    t = db.get(Transaction, txn_id, populate_existing=True)
    if t is None or t.payer_user_id != user_id:  # do not reveal other users' transactions
        raise HTTPException(404, "Transaction not found")
    return t


def balance_after(db: Session, t: Transaction) -> Decimal | None:
    if t.status in (PROCESSING, SUCCESS):
        entry = db.scalar(select(LedgerEntry).where(LedgerEntry.transaction_id == t.id, LedgerEntry.type == DEBIT))
        if entry is not None:
            return entry.balance_after
    return db.scalar(select(Account.balance).where(Account.id == t.account_id))


# --------------------------------------------------------------------------- step 1: initiate
def _replay(t: Transaction, user_id: str) -> Transaction:
    if t.payer_user_id != user_id:
        raise HTTPException(409, "Idempotency-Key was already used for another request")
    return t


def initiate(db: Session, user_id: str, idempotency_key: str, student_id: str) -> Transaction:
    idempotency_key, student_id = idempotency_key.strip(), student_id.strip()
    if not 8 <= len(idempotency_key) <= 64:
        raise HTTPException(400, "Idempotency-Key header must be 8-64 characters (use a UUID)")
    if not student_id:
        raise HTTPException(400, "student_id is required")

    existing = db.scalar(select(Transaction).where(Transaction.idempotency_key == idempotency_key))
    if existing is not None:
        return _replay(existing, user_id)  # retry of a request we already handled: no new side effects

    account = db.scalar(select(Account).where(Account.user_id == user_id))
    if account is None:
        raise HTTPException(404, "No payment account for this user")
    try:
        tuition = clients.get_tuition(student_id)
    except UpstreamError as e:
        if e.status == 404:
            raise HTTPException(404, e.detail)
        raise HTTPException(502, "Tuition service unavailable, try again")
    if tuition["status"] == "PAID":
        raise HTTPException(409, "Tuition for this student is already paid")
    if tuition["status"] == "RESERVED":
        raise HTTPException(409, "Tuition for this student is being paid in another transaction")
    amount = Decimal(str(tuition["amount"]))
    if account.balance < amount:  # early, unlocked check for a friendly error; re-checked under lock in verify
        raise HTTPException(422, "Insufficient balance")
    payer = _payer(user_id)

    t = Transaction(account_id=account.id, payer_user_id=user_id, student_id=tuition["student_id"],
                    tuition_id=tuition["tuition_id"], amount=amount, status=PENDING_OTP,
                    idempotency_key=idempotency_key,
                    expires_at=utcnow() + timedelta(seconds=settings.otp_ttl_seconds))
    db.add(t)
    try:
        db.commit()
    except IntegrityError:  # the same Idempotency-Key raced us -> answer with the winner
        db.rollback()
        return _replay(db.scalar(select(Transaction).where(Transaction.idempotency_key == idempotency_key)), user_id)
    db.refresh(t)  # load server-side defaults (created_at)

    try:
        clients.reserve_tuition(t.tuition_id, t.id)
    except UpstreamError as e:
        lost_race = e.status == 409
        _transition(db, t.id, PENDING_OTP, FAILED,
                    "Tuition is already paid or being paid" if lost_race else "Tuition service unavailable")
        if lost_race:
            raise HTTPException(409, "Tuition for this student is being paid in another transaction")
        raise HTTPException(502, "Tuition service unavailable, try again")

    try:
        clients.issue_otp(t.id, payer["email"], payer["full_name"])
    except UpstreamError:
        _transition(db, t.id, PENDING_OTP, FAILED, "Could not send OTP")
        _release(t)
        raise HTTPException(502, "Could not send the OTP, try again")
    return t


# --------------------------------------------------------------------------- step 2: verify + debit
_OTP_ERRORS = {
    "expired": "OTP expired or already used. Request a new one.",
    "locked": "Too many wrong attempts. Request a new OTP.",
}


def verify(db: Session, user_id: str, txn_id: str, otp: str) -> Transaction:
    t = get_owned(db, txn_id, user_id)
    if t.status in (PROCESSING, SUCCESS):
        return t  # double submit: report the outcome again
    if _is_overdue(t):
        expire(db, t)
        raise HTTPException(410, "Transaction expired")
    if t.status == EXPIRED:
        raise HTTPException(410, "Transaction expired")
    if t.status != PENDING_OTP:
        raise HTTPException(409, f"Transaction is {t.status}")

    payer = _payer(user_id)  # before the OTP is consumed, so an outage here does not burn the code
    try:
        v = clients.verify_otp(t.id, otp)
    except UpstreamError:
        raise HTTPException(502, "OTP service unavailable, try again")
    if not v["valid"]:
        raise HTTPException(400, _OTP_ERRORS.get(v.get("reason"), f"Wrong OTP. {v.get('attempts_left', 0)} attempt(s) left."))

    def debit(db):
        t = _locked_txn(db, txn_id)
        if t.status != PENDING_OTP:  # cancelled / expired between our check and the lock
            return t
        account = _locked_account(db, t.account_id)
        if account.balance < t.amount:  # e.g. another payment from this account was confirmed first
            t.status, t.failure_reason, t.completed_at = FAILED, "Insufficient balance", utcnow()
            return t
        account.balance -= t.amount
        account.version += 1
        db.add(LedgerEntry(account_id=account.id, transaction_id=t.id, type=DEBIT, amount=t.amount,
                           balance_after=account.balance))
        t.status = PROCESSING
        return t

    t = run_in_tx(db, debit)
    if t.status == PROCESSING:
        return complete(db, t, payer)
    if t.status == FAILED:
        _release(t)
        return t
    if t.status == EXPIRED:
        raise HTTPException(410, "Transaction expired")
    raise HTTPException(409, f"Transaction is {t.status}")


def complete(db: Session, t: Transaction, payer: dict) -> Transaction:
    """PROCESSING -> commit tuition -> SUCCESS (or refund). Safe to call repeatedly / concurrently."""
    try:
        clients.commit_tuition(t.tuition_id, t.id)
    except UpstreamError as e:
        if e.status == 409:  # our hold is gone (should not happen within the TTLs) -> give the money back
            return refund(db, t.id, "Tuition could not be marked as paid; amount refunded")
        log.warning("tuition commit for txn %s failed (%s); left PROCESSING for the reconciler", t.id, e)
        return t

    txn_id = t.id

    def finalize(db):
        t = _locked_txn(db, txn_id)
        if t.status != PROCESSING:
            return t
        entry = db.scalar(select(LedgerEntry).where(LedgerEntry.transaction_id == t.id, LedgerEntry.type == DEBIT))
        t.status, t.completed_at = SUCCESS, utcnow()
        db.add(OutboxEvent(type=events.PAYMENT_COMPLETED, payload={
            "email": payer["email"], "full_name": payer["full_name"], "transaction_id": t.id,
            "student_id": t.student_id, "amount": str(t.amount), "balance_after": str(entry.balance_after)}))
        return t

    return run_in_tx(db, finalize)


def refund(db: Session, txn_id: str, reason: str) -> Transaction:
    def step(db):
        t = _locked_txn(db, txn_id)
        if t.status != PROCESSING:
            return t
        account = _locked_account(db, t.account_id)
        account.balance += t.amount
        account.version += 1
        db.add(LedgerEntry(account_id=account.id, transaction_id=t.id, type=CREDIT, amount=t.amount,
                           balance_after=account.balance))
        t.status, t.failure_reason, t.completed_at = FAILED, reason, utcnow()
        return t
    return run_in_tx(db, step)


# --------------------------------------------------------------------------- resend / cancel
def resend_otp(db: Session, user_id: str, txn_id: str) -> int:
    t = get_owned(db, txn_id, user_id)
    if _is_overdue(t):
        expire(db, t)
        raise HTTPException(410, "Transaction expired")
    if t.status != PENDING_OTP:
        raise HTTPException(409, f"Transaction is {t.status}")
    payer = _payer(user_id)
    try:
        clients.reserve_tuition(t.tuition_id, t.id)  # same txn -> idempotent; pushes reserved_until forward
    except UpstreamError as e:
        if e.status == 409:  # hold was lost (expired and taken) -> this payment cannot continue
            _transition(db, t.id, PENDING_OTP, FAILED, "Tuition reservation was lost")
            raise HTTPException(409, "Tuition for this student is being paid in another transaction")
        raise HTTPException(502, "Tuition service unavailable, try again")
    try:
        issued = clients.issue_otp(t.id, payer["email"], payer["full_name"])
    except UpstreamError as e:
        if e.status == 429:
            raise HTTPException(429, e.detail, headers={"Retry-After": e.headers.get("retry-after", "30")})
        raise HTTPException(502, "Could not send the OTP, try again")

    def extend(db):
        return db.execute(update(Transaction).where(Transaction.id == t.id, Transaction.status == PENDING_OTP)
                          .values(expires_at=utcnow() + timedelta(seconds=issued["expires_in"]))
                          .execution_options(synchronize_session=False)).rowcount
    if not run_in_tx(db, extend):
        raise HTTPException(409, "Transaction is no longer waiting for an OTP")
    return issued["expires_in"]


def cancel(db: Session, user_id: str, txn_id: str) -> Transaction:
    t = get_owned(db, txn_id, user_id)
    if t.status == CANCELLED:
        return t  # idempotent
    if t.status != PENDING_OTP or not _transition(db, t.id, PENDING_OTP, CANCELLED, "Cancelled by user"):
        raise HTTPException(409, f"Transaction is {db.get(Transaction, txn_id, populate_existing=True).status}")
    _release(t)
    return db.get(Transaction, txn_id, populate_existing=True)
