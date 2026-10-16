"""API gateway: single public entry point. Verifies the JWT, injects X-User-Id, forwards to the owning service.
Only /api/<prefix>/... routes below are exposed; /internal/* endpoints of services are unreachable from outside."""
import logging
import re
import httpx
import jwt
import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from app.config import settings
from shared.security import decode_token

log = logging.getLogger("gateway")

ROUTES = {
    "auth": settings.user_service_url,
    "users": settings.user_service_url,
    "tuitions": settings.tuition_service_url,
    "accounts": settings.payment_service_url,
    "transactions": settings.payment_service_url,
}
SKIP_REQ_HEADERS = {"host", "content-length", "connection", "x-user-id", "transfer-encoding"}

# Fixed-window rate limits on the abuse-prone endpoints: (method, path regex, key, max requests, window seconds).
# key "ip" = client address (nginx sets X-Forwarded-For), "user" = verified user id from the JWT.
RATE_LIMITS = [
    ("POST", re.compile(r"auth/login"), "ip", 10, 60),
    ("POST", re.compile(r"transactions"), "user", 20, 60),  # idempotent client retries count too
    ("POST", re.compile(r"transactions/[^/]+/verify-otp"), "user", 10, 60),
    ("POST", re.compile(r"transactions/[^/]+/resend-otp"), "user", 5, 60),
]

app = FastAPI(title="API Gateway", version="0.1.0")
client = httpx.AsyncClient(timeout=20)
rdb = aioredis.from_url(settings.redis_url, decode_responses=True)


async def rate_limited(request: Request, path: str, user_id: str | None) -> int:
    """0 if allowed, else seconds until the window resets. Fails open if Redis is unavailable."""
    for i, (method, pattern, key_kind, limit, window) in enumerate(RATE_LIMITS):
        if request.method != method or not pattern.fullmatch(path):
            continue
        who = user_id if key_kind == "user" else (request.headers.get("x-forwarded-for") or request.client.host)
        key = f"rl:{i}:{who}"
        try:
            async with rdb.pipeline(transaction=True) as p:
                count, _ = await p.incr(key).expire(key, window, nx=True).execute()
            if count > limit * settings.rate_limit_multiplier:
                return max(await rdb.ttl(key), 1)
        except Exception:
            log.exception("rate limiter unavailable; allowing request")
        return 0
    return 0


@app.get("/health")
async def health():  # async: answered by the event loop even when the threadpool is saturated
    return {"status": "ok", "service": "gateway"}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    base = ROUTES.get(path.split("/", 1)[0])
    if base is None:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    headers = {k: v for k, v in request.headers.items() if k.lower() not in SKIP_REQ_HEADERS}
    user_id = None
    if not (request.method == "POST" and path == "auth/login"):
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"detail": "Missing bearer token"}, status_code=401)
        try:
            claims = decode_token(auth[7:], settings.jwt_secret)
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
        user_id = headers["x-user-id"] = claims["sub"]  # downstream services trust this header (internal network only)

    if wait := await rate_limited(request, path, user_id):
        return JSONResponse({"detail": "Too many requests, slow down"}, status_code=429,
                            headers={"Retry-After": str(wait)})
    try:
        r = await client.request(request.method, f"{base}/{path}", params=request.query_params,
                                 headers=headers, content=await request.body())
    except httpx.RequestError:
        return JSONResponse({"detail": "Upstream service unavailable"}, status_code=502)
    passthrough = {k: r.headers[k] for k in ("retry-after",) if k in r.headers}
    return Response(content=r.content, status_code=r.status_code, headers=passthrough,
                    media_type=r.headers.get("content-type", "application/json"))
