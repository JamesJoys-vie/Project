from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str
    otp_ttl_seconds: int = 300  # max 5 minutes per requirements
    otp_max_attempts: int = 5  # wrong codes before the OTP is burned
    otp_max_issues: int = 4  # per transaction: initial OTP + 3 resends
    otp_resend_cooldown_seconds: int = 30


settings = Settings()
