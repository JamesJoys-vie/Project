from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    tuition_service_url: str
    otp_service_url: str
    redis_url: str  # event bus (Redis Streams)


settings = Settings()
