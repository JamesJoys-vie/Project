from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jwt_secret: str
    user_service_url: str
    tuition_service_url: str
    payment_service_url: str


settings = Settings()
