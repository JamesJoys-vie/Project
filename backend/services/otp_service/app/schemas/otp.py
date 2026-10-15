from pydantic import BaseModel


class IssueOtpRequest(BaseModel):
    transaction_id: str
    email: str
    full_name: str


class IssueOtpResponse(BaseModel):
    expires_in: int


class VerifyOtpRequest(BaseModel):
    transaction_id: str
    otp: str


class VerifyOtpResponse(BaseModel):
    valid: bool
