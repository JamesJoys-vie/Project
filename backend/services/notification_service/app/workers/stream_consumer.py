"""Consumes `otp.requested` and `payment.completed` from Redis Streams (consumer group `notification`) and sends emails.
Handlers must be idempotent: a message can be delivered more than once (see shared/events.py)."""
import threading
from shared import events
from shared.redis_client import get_redis
from app.domain.mailer import send_email

GROUP = "notification"


def handle(event_type: str, payload: dict) -> None:
    """TODO: nicer templates; dedupe via `SET notif:sent:<transaction_id>:<event_type> 1 NX EX 86400` before sending."""
    if event_type == events.OTP_REQUESTED:
        send_email(payload["email"], "Your tuition payment OTP",
                   f"Hello {payload['full_name']},\nYour OTP is {payload['otp']}. "
                   f"It expires in {payload['expires_in'] // 60} minutes.")
    elif event_type == events.PAYMENT_COMPLETED:
        send_email(payload["email"], "Tuition payment successful",
                   f"Hello {payload['full_name']},\nPaid {payload['amount']} for student {payload['student_id']}. "
                   f"Transaction {payload['transaction_id']}.")


def start(redis_url: str, stop: threading.Event | None = None) -> threading.Thread:
    t = threading.Thread(target=events.consume, daemon=True, name="stream-consumer",
                         args=(get_redis(redis_url), GROUP, [events.OTP_REQUESTED, events.PAYMENT_COMPLETED], handle),
                         kwargs={"stop": stop})
    t.start()
    return t
