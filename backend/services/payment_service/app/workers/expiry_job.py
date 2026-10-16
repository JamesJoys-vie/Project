"""Expiry + reconcile job (runs every `expiry_interval_seconds`).

1) PENDING_OTP past `expires_at` -> EXPIRED (conditional update) and release the tuition hold.
   (tuition-service also treats holds past `reserved_until` as free, so this is cleanup, not the only safeguard.)
2) PROCESSING (money debited, tuition commit not confirmed, e.g. tuition-service was down) -> retry the commit,
   then SUCCESS or refund. Safe even while the original request is still in flight: commit is idempotent and the
   final status change is conditional on PROCESSING under a row lock.
"""
import logging
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domain import saga
from app.domain.models import PENDING_OTP, PROCESSING, Transaction
from app.repositories import clients
from app.repositories.clients import UpstreamError

log = logging.getLogger("payment.expiry")
BATCH = 100


def run_once(db: Session) -> tuple[int, int]:
    overdue = db.scalars(select(Transaction).where(Transaction.status == PENDING_OTP,
                                                   Transaction.expires_at <= saga.utcnow()).limit(BATCH)).all()
    saga.end_read(db)
    expired = sum(saga.expire(db, t) for t in overdue)

    stuck = db.scalars(select(Transaction).where(Transaction.status == PROCESSING).limit(BATCH)).all()
    saga.end_read(db)  # no connection held during the user / tuition calls below
    for t in stuck:
        try:
            payer = clients.get_user(t.payer_user_id)
        except UpstreamError as e:
            log.warning("cannot reconcile txn %s yet: %s", t.id, e)
            continue
        saga.complete(db, t, payer)
    return expired, len(stuck)


def run_forever(session_factory, interval_s: float = 15.0, stop=None) -> None:
    while not (stop and stop.is_set()):
        try:
            with session_factory() as db:
                expired, reconciled = run_once(db)
            if expired or reconciled:
                log.info("expired %d pending transaction(s), reconciled %d processing", expired, reconciled)
        except Exception:
            log.exception("expiry job failed; retrying")
        time.sleep(interval_s)
