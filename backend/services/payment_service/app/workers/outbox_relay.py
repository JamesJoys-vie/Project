"""Outbox relay: MySQL `outbox_events` -> Redis Streams.

Why an outbox: the debit, the ledger entry and the `payment.completed` event row are committed in ONE MySQL
transaction, so an event can never be lost or emitted for a payment that rolled back.
Delivery is at-least-once (a crash between XADD and the `published=1` commit re-sends), so consumers are idempotent.
"""
import time
from sqlalchemy.orm import Session


def relay_once(db: Session, r, batch: int = 50) -> int:
    """TODO:
    rows = SELECT * FROM outbox_events WHERE published = 0 ORDER BY created_at LIMIT :batch FOR UPDATE SKIP LOCKED
    for row in rows: shared.events.publish(r, row.type, row.payload); row.published = True
    db.commit(); return len(rows)"""
    raise NotImplementedError


def run_forever(session_factory, r, interval_s: float = 1.0, stop=None) -> None:
    while not (stop and stop.is_set()):
        with session_factory() as db:
            n = relay_once(db, r)
        if n == 0:
            time.sleep(interval_s)
