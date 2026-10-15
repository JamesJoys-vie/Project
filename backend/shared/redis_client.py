"""One cached Redis client per URL (thread-safe connection pool inside redis-py)."""
from functools import lru_cache
import redis


@lru_cache
def get_redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)
