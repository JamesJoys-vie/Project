import logging
import threading
from fastapi import FastAPI
from shared.redis_client import get_redis
from app.api.routes import router
from app.core.config import settings
from app.core.db import SessionLocal
from app.workers import expiry_job, outbox_relay

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

app = FastAPI(title="Payment Service", version="0.1.0")
app.include_router(router)
_stop = threading.Event()


@app.on_event("startup")
def start_workers():
    """Background threads: outbox relay (MySQL outbox -> Redis Streams) and expiry/reconcile job."""
    threading.Thread(target=outbox_relay.run_forever, name="outbox-relay", daemon=True,
                     args=(SessionLocal, get_redis(settings.redis_url)), kwargs={"stop": _stop}).start()
    threading.Thread(target=expiry_job.run_forever, name="expiry-job", daemon=True,
                     args=(SessionLocal, settings.expiry_interval_seconds), kwargs={"stop": _stop}).start()


@app.on_event("shutdown")
def stop_workers():
    _stop.set()


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service"}
