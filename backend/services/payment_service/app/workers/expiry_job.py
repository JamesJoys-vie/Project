"""Expiry job: cancels PENDING_OTP transactions whose OTP window passed and releases their tuition reservation.

TODO: every ~30s: SELECT id, tuition_id FROM transactions WHERE status='PENDING_OTP' AND created_at < NOW() - INTERVAL :ttl SECOND
      -> mark EXPIRED (conditional UPDATE ... WHERE status='PENDING_OTP') -> POST tuition-service /internal/tuitions/{id}/release.
(tuition-service also treats reservations past `reserved_until` as free, so this is cleanup, not the only safeguard.)
"""


def run_forever(session_factory, interval_s: float = 30.0, stop=None) -> None:
    raise NotImplementedError
