"""API gateway: single public entry point. Verifies the JWT, injects X-User-Id, forwards to the owning service.
Only /api/<prefix>/... routes below are exposed; /internal/* endpoints of services are unreachable from outside."""
import httpx
import jwt
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from app.config import settings
from shared.security import decode_token

ROUTES = {
    "auth": settings.user_service_url,
    "users": settings.user_service_url,
    "tuitions": settings.tuition_service_url,
    "accounts": settings.payment_service_url,
    "transactions": settings.payment_service_url,
}
SKIP_REQ_HEADERS = {"host", "content-length", "connection", "x-user-id", "transfer-encoding"}

app = FastAPI(title="API Gateway", version="0.1.0")
client = httpx.AsyncClient(timeout=20)


@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    base = ROUTES.get(path.split("/", 1)[0])
    if base is None:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    headers = {k: v for k, v in request.headers.items() if k.lower() not in SKIP_REQ_HEADERS}
    if not (request.method == "POST" and path == "auth/login"):
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"detail": "Missing bearer token"}, status_code=401)
        try:
            claims = decode_token(auth[7:], settings.jwt_secret)
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
        headers["x-user-id"] = claims["sub"]  # downstream services trust this header (internal network only)

    # TODO: rate limiting for /api/auth/login and OTP endpoints (e.g. Redis counter)
    try:
        r = await client.request(request.method, f"{base}/{path}", params=request.query_params,
                                 headers=headers, content=await request.body())
    except httpx.RequestError:
        return JSONResponse({"detail": "Upstream service unavailable"}, status_code=502)
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))
