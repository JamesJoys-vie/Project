from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    user_service_url: str
    tuition_service_url: str
    otp_service_url: str
    redis_url: str  # event bus (Redis Streams)
    otp_ttl_seconds: int = 300  # a PENDING_OTP transaction lives as long as its newest OTP
    http_timeout_seconds: float = 5.0
    expiry_interval_seconds: float = 15.0  # how often the expiry / reconcile job runs
    processing_retry_after_seconds: int = 15  # PROCESSING older than this -> reconciler retries the tuition commit


settings = Settings()
