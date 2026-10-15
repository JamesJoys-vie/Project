from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.schemas.tuition import TuitionInfo, ReserveRequest, CommitRequest

router = APIRouter()


@router.get("/tuitions/{student_id}", response_model=TuitionInfo, responses={404: {"description": "Student/tuition not found"}})
def get_tuition(student_id: str, db: Session = Depends(get_db)):
    """Public (via gateway, authenticated). TODO: return student + outstanding tuition."""
    raise HTTPException(501, "Not implemented")


# ---- internal endpoints (called by payment-service only; NOT routed by the gateway) ----
@router.post("/internal/tuitions/{tuition_id}/reserve", status_code=200, responses={409: {"description": "Already reserved/paid"}})
def reserve(tuition_id: str, body: ReserveRequest, db: Session = Depends(get_db)):
    """TODO: atomic `UPDATE tuitions SET status='RESERVED', reserved_by_txn=?, reserved_until=?, version=version+1
    WHERE id=? AND (status='UNPAID' OR (status='RESERVED' AND reserved_until < NOW()))` ; rowcount==1 -> success else 409."""
    raise HTTPException(501, "Not implemented")


@router.post("/internal/tuitions/{tuition_id}/commit", status_code=200)
def commit(tuition_id: str, body: CommitRequest, db: Session = Depends(get_db)):
    """TODO: RESERVED(by this txn) -> PAID, set paid_by_txn. Idempotent if already PAID by the same txn."""
    raise HTTPException(501, "Not implemented")


@router.post("/internal/tuitions/{tuition_id}/release", status_code=200)
def release(tuition_id: str, body: ReserveRequest, db: Session = Depends(get_db)):
    """TODO: RESERVED(by this txn) -> UNPAID (saga compensation). Idempotent."""
    raise HTTPException(501, "Not implemented")
