from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Payment Service", version="0.1.0")
app.include_router(router)

# TODO: on startup run background threads from app/workers/: outbox_relay (MySQL outbox -> Redis Streams)
#       and expiry_job (expire stale PENDING_OTP transactions, release reservations).


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service"}
