from fastapi import APIRouter, HTTPException
from app.schemas.otp import IssueOtpRequest, IssueOtpResponse, VerifyOtpRequest, VerifyOtpResponse

router = APIRouter()


@router.post("/internal/otp", response_model=IssueOtpResponse, status_code=201)
def issue(body: IssueOtpRequest):
    """TODO: generate 6-digit code (secrets.randbelow); ensure it is unique among ACTIVE OTPs
    (Redis `SET otp:code:<code> <txn> NX EX 300`, retry on collision); store hash under `otp:txn:<txn_id>` with EX 300
    (overwriting any previous OTP for the same txn); publish `otp.requested` with shared.events.publish (Redis Stream `events:otp.requested`)."""
    raise HTTPException(501, "Not implemented")


@router.post("/internal/otp/verify", response_model=VerifyOtpResponse)
def verify(body: VerifyOtpRequest):
    """TODO: atomic compare-and-delete (Lua script or GETDEL) so the OTP is single-use; count failed attempts."""
    raise HTTPException(501, "Not implemented")
