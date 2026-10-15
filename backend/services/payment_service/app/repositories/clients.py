"""Synchronous HTTP clients for the services payment-service orchestrates (internal network only)."""
from functools import lru_cache
import httpx
from app.core.config import settings


class UpstreamError(Exception):
    """Non-2xx answer (status = upstream status) or no answer at all (status = None)."""

    def __init__(self, service: str, status: int | None, detail: str = "", headers: dict | None = None):
        super().__init__(f"{service}: {status} {detail}")
        self.service, self.status, self.detail, self.headers = service, status, detail, headers or {}


@lru_cache
def _client() -> httpx.Client:
    return httpx.Client(timeout=settings.http_timeout_seconds)


def _call(service: str, method: str, url: str, json: dict | None = None) -> dict:
    try:
        r = _client().request(method, url, json=json)
    except httpx.HTTPError as e:
        raise UpstreamError(service, None, str(e)) from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise UpstreamError(service, r.status_code, str(detail), dict(r.headers))
    return r.json()


# ---- user-service ----
def get_user(user_id: str) -> dict:
    return _call("user-service", "GET", f"{settings.user_service_url}/internal/users/{user_id}")


# ---- tuition-service ----
def get_tuition(student_id: str) -> dict:
    return _call("tuition-service", "GET", f"{settings.tuition_service_url}/tuitions/{student_id}")


def reserve_tuition(tuition_id: str, txn_id: str) -> dict:
    return _call("tuition-service", "POST", f"{settings.tuition_service_url}/internal/tuitions/{tuition_id}/reserve",
                 {"transaction_id": txn_id})


def commit_tuition(tuition_id: str, txn_id: str) -> dict:
    return _call("tuition-service", "POST", f"{settings.tuition_service_url}/internal/tuitions/{tuition_id}/commit",
                 {"transaction_id": txn_id})


def release_tuition(tuition_id: str, txn_id: str) -> dict:
    return _call("tuition-service", "POST", f"{settings.tuition_service_url}/internal/tuitions/{tuition_id}/release",
                 {"transaction_id": txn_id})


# ---- otp-service ----
def issue_otp(txn_id: str, email: str, full_name: str) -> dict:
    return _call("otp-service", "POST", f"{settings.otp_service_url}/internal/otp",
                 {"transaction_id": txn_id, "email": email, "full_name": full_name})


def verify_otp(txn_id: str, otp: str) -> dict:
    return _call("otp-service", "POST", f"{settings.otp_service_url}/internal/otp/verify",
                 {"transaction_id": txn_id, "otp": otp})
