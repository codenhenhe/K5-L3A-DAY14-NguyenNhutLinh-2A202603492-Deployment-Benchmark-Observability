"""Redis-backed sliding window per API key."""

from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException

from .config import settings
from .redis_client import r

# One Redis operation makes the count and insertion atomic across workers.
_SLIDING_WINDOW = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local clock = redis.call("TIME")
local now_ms = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local window_ms = 60000

redis.call("ZREMRANGEBYSCORE", key, "-inf", now_ms - window_ms)
if redis.call("ZCARD", key) >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")[2]
    return math.max(1, math.ceil((oldest + window_ms - now_ms) / 1000))
end
redis.call("ZADD", key, now_ms, ARGV[2])
redis.call("PEXPIRE", key, window_ms)
return 0
"""


def check_rate_limit(api_key: str) -> None:
    key_digest = sha256(api_key.encode("utf-8")).hexdigest()
    retry_after = r.eval(
        _SLIDING_WINDOW,
        1,
        f"agent:rate-limit:{key_digest}",
        settings.rate_limit_per_minute,
        uuid4().hex,
    )
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
