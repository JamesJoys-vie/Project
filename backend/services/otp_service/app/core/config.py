from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str
    otp_ttl_seconds: int = 300  # max 5 minutes per requirements


settings = Settings()
