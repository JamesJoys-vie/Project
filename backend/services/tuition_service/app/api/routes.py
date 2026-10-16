"""Tuition lookup + the reservation state machine used by the payment saga.

UNPAID --reserve--> RESERVED --commit--> PAID
                       |
                       +--release / reserved_until passed--> UNPAID

Every transition is ONE conditional UPDATE (compare-and-set on status/owner), so two concurrent payments for
the same student cannot both win: InnoDB row locking serialises the UPDATEs and the loser sees rowcount == 0.
All times are naive UTC (`utcnow()`), never MySQL NOW(), so there is one clock for reserved_until.
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.domain.models import PAID, RESERVED, UNPAID, Student, Tuition
from app.schemas.tuition import CommitRequest, ReserveRequest, TuitionInfo

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _info(t: Tuition, student: Student, now: datetime) -> TuitionInfo:
    status = t.status
    if status == RESERVED and t.reserved_until and t.reserved_until < now:
        status = UNPAID  # stale hold: free again (reserve() accepts it)
    return TuitionInfo(tuition_id=t.id, student_id=t.student_id, student_name=student.full_name,
                       term=t.term, amount=t.amount, status=status)


@router.get("/tuitions/{student_id}", response_model=TuitionInfo, responses={404: {"description": "Student/tuition not found"}})
def get_tuition(student_id: str, db: Session = Depends(get_db, scope="function")):
    """Public (via gateway, authenticated). The student's outstanding tuition (oldest unpaid term first);
    if everything is paid, the latest PAID one so the UI can say "already paid"."""
    student = db.get(Student, student_id.strip())
    if student is None:
        raise HTTPException(404, "Student not found")
    paid_last = case((Tuition.status == PAID, 1), else_=0)
    t = db.scalars(select(Tuition).where(Tuition.student_id == student.student_id)
                   .order_by(paid_last, Tuition.term)).first()
    if t is None:
        raise HTTPException(404, "No tuition for this student")
    if t.status == PAID:  # all paid -> show the most recent term
        t = db.scalars(select(Tuition).where(Tuition.student_id == student.student_id)
                       .order_by(Tuition.term.desc())).first()
    return _info(t, student, utcnow())


# ---- internal endpoints (called by payment-service only; NOT routed by the gateway) ----
def _get_or_404(db: Session, tuition_id: str) -> Tuition:
    t = db.get(Tuition, tuition_id, populate_existing=True)
    if t is None:
        raise HTTPException(404, "Tuition not found")
    return t


@router.post("/internal/tuitions/{tuition_id}/reserve", response_model=TuitionInfo,
             responses={404: {"description": "Not found"}, 409: {"description": "Already reserved/paid"}})
def reserve(tuition_id: str, body: ReserveRequest, db: Session = Depends(get_db, scope="function")):
    """Hold the tuition for one transaction until reserved_until. Idempotent for the same transaction."""
    now = utcnow()
    res = db.execute(
        update(Tuition)
        .where(Tuition.id == tuition_id,
               or_(Tuition.status == UNPAID,
                   and_(Tuition.status == RESERVED,
                        or_(Tuition.reserved_until < now, Tuition.reserved_by_txn == body.transaction_id))))
        .values(status=RESERVED, reserved_by_txn=body.transaction_id,
                reserved_until=now + timedelta(seconds=settings.reservation_ttl_seconds),
                version=Tuition.version + 1)
        .execution_options(synchronize_session=False))
    db.commit()
    t = _get_or_404(db, tuition_id)
    if res.rowcount != 1:
        raise HTTPException(409, "Tuition already paid" if t.status == PAID else "Tuition is being paid by another transaction")
    return _info(t, db.get(Student, t.student_id), now)


@router.post("/internal/tuitions/{tuition_id}/commit", status_code=200,
             responses={404: {"description": "Not found"}, 409: {"description": "Not reserved by this transaction"}})
def commit(tuition_id: str, body: CommitRequest, db: Session = Depends(get_db, scope="function")):
    """RESERVED(by this txn) -> PAID. Idempotent if already PAID by the same txn.
    Deliberately ignores reserved_until: once the payer's money moved, an in-flight commit must not lose to the clock.
    (Another txn can only take the hold after expiry; payment-service rejects OTPs long before that.)"""
    res = db.execute(
        update(Tuition)
        .where(Tuition.id == tuition_id, Tuition.status == RESERVED, Tuition.reserved_by_txn == body.transaction_id)
        .values(status=PAID, paid_by_txn=body.transaction_id, reserved_until=None, version=Tuition.version + 1)
        .execution_options(synchronize_session=False))
    db.commit()
    if res.rowcount == 1:
        return {"status": PAID}
    t = _get_or_404(db, tuition_id)
    if t.status == PAID and t.paid_by_txn == body.transaction_id:
        return {"status": PAID}
    raise HTTPException(409, "Tuition is not reserved by this transaction")


@router.post("/internal/tuitions/{tuition_id}/release", status_code=200, responses={404: {"description": "Not found"}})
def release(tuition_id: str, body: ReserveRequest, db: Session = Depends(get_db, scope="function")):
    """RESERVED(by this txn) -> UNPAID (saga compensation). Idempotent: no-op if the hold is gone or belongs to someone else."""
    res = db.execute(
        update(Tuition)
        .where(Tuition.id == tuition_id, Tuition.status == RESERVED, Tuition.reserved_by_txn == body.transaction_id)
        .values(status=UNPAID, reserved_by_txn=None, reserved_until=None, version=Tuition.version + 1)
        .execution_options(synchronize_session=False))
    db.commit()
    if res.rowcount == 1:
        return {"released": True}
    _get_or_404(db, tuition_id)
    return {"released": False}
