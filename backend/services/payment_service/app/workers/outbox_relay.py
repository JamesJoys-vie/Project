"""Outbox relay: MySQL `outbox_events` -> Redis Streams.

Why an outbox: the SUCCESS status and the `payment.completed` event row are committed in ONE MySQL
transaction, so an event can never be lost or emitted for a payment that rolled back.
Delivery is at-least-once (a crash between XADD and the `published=1` commit re-sends), so consumers are idempotent.
"""
import logging
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from shared import events
from app.domain.models import OutboxEvent

log = logging.getLogger("payment.outbox")


def relay_once(db: Session, r, batch: int = 50) -> int:
    """SKIP LOCKED lets several payment-service replicas relay in parallel without sending a row twice."""
    rows = db.scalars(select(OutboxEvent).where(OutboxEvent.published.is_(False))
                      .order_by(OutboxEvent.created_at).limit(batch).with_for_update(skip_locked=True)).all()
    for row in rows:
        events.publish(r, row.type, row.payload)
        row.published = True
    db.commit()
    return len(rows)


def run_forever(session_factory, r, interval_s: float = 1.0, stop=None) -> None:
    while not (stop and stop.is_set()):
        try:
            with session_factory() as db:
                n = relay_once(db, r)
        except Exception:
            log.exception("outbox relay failed; retrying")
            n = 0
        if n == 0:
            time.sleep(interval_s)
