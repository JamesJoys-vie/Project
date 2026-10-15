from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    reservation_ttl_seconds: int = 600


settings = Settings()
