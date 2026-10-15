from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="User Service", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "user-service"}
