from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(title="Notification Service", version="0.1.0")


@app.on_event("startup")
def start_consumer():
    # TODO: enable once otp/payment services publish events.
    # from app.workers.stream_consumer import start
    # start(settings.redis_url)
    pass


@app.get("/health")
def health():
    return {"status": "ok", "service": "notification-service"}
