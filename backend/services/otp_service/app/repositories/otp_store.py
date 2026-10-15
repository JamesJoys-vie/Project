"""Redis key layout for OTPs (all keys expire on their own -> TTL requirement is enforced by Redis).

  otp:txn:<transaction_id>  -> HASH {code_hash, attempts}      EX = OTP_TTL_SECONDS (300)
        one active OTP per transaction; issuing again overwrites (resend invalidates the old code)
  otp:code:<code>           -> <transaction_id>                SET NX EX 300
        guarantees a code is not shared by two ACTIVE OTPs of different transactions (retry generation on NX failure)

Verify = atomic Lua script: compare hash, on match DEL both keys (single-use); on mismatch HINCRBY attempts and
DEL after N failed attempts.
"""
from redis import Redis


class OtpStore:
    def __init__(self, r: Redis, ttl_seconds: int = 300, max_attempts: int = 5):
        self.r, self.ttl, self.max_attempts = r, ttl_seconds, max_attempts

    def save(self, transaction_id: str, code: str) -> bool:
        """TODO: reserve otp:code:<code> with NX; store otp:txn:<id> hash; return False on code collision."""
        raise NotImplementedError

    def verify_and_consume(self, transaction_id: str, code: str) -> bool:
        """TODO: Lua compare-and-delete (single-use)."""
        raise NotImplementedError
