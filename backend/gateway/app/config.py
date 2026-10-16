from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jwt_secret: str
    user_service_url: str
    tuition_service_url: str
    payment_service_url: str
    redis_url: str  # rate-limit counters
    rate_limit_multiplier: float = 1.0  # scales every limit below; load tests raise it (one client IP, many users)


settings = Settings()
