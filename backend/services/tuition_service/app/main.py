from fastapi import FastAPI
from shared.db import add_busy_handler
from app.api.routes import router

app = FastAPI(title="Tuition Service", version="0.1.0")
app.include_router(router)
add_busy_handler(app)


@app.get("/health")
async def health():  # async: answered by the event loop even when the threadpool is saturated
    return {"status": "ok", "service": "tuition-service"}
