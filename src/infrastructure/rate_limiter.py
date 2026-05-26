import hashlib
import os
import threading
import time
from typing import Dict, Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


log = structlog.get_logger("inferra.rate_limiter")


EXEMPT_PREFIXES = (
    "/",
    "/live",
    "/api/v1/live",
    "/health",
    "/api/v1/health",
    "/metrics",
    "/api/v1/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class TokenBucket:
    """Thread-safe token bucket for in-process rate limiting."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = max(rate, 0.0)
        self._capacity = max(capacity, 0)
        self._tokens = float(self._capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def last_refill(self) -> float:
        return self._last_refill

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now


class RateLimiter:
    """In-process token-bucket limiter keyed by API key hash or client host."""

    def __init__(self, requests_per_minute: int = 10000, capacity: Optional[int] = None) -> None:
        self._requests_per_minute = max(int(requests_per_minute), 0)
        self._rate = self._requests_per_minute / 60.0
        self._capacity = max(int(capacity or self._requests_per_minute), 0)
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    @property
    def requests_per_minute(self) -> int:
        return self._requests_per_minute

    def check(self, key: str) -> bool:
        if self._requests_per_minute <= 0:
            return True
        return self._get_bucket(key).consume()

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._buckets.pop(key, None)
                return
            self._buckets.clear()

    def _get_bucket(self, key: str) -> TokenBucket:
        with self._lock:
            now = time.monotonic()
            if now - self._last_cleanup > 300:
                self._cleanup_unlocked(now)
                self._last_cleanup = now
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(rate=self._rate, capacity=self._capacity)
                self._buckets[key] = bucket
            return bucket

    def _cleanup_unlocked(self, now: float) -> None:
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if now - bucket.last_refill > 3600 and bucket.available_tokens >= bucket.capacity
        ]
        for key in stale_keys:
            del self._buckets[key]


rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that applies a token-bucket request limit."""

    def __init__(
        self,
        app,
        limiter: Optional[RateLimiter] = None,
        limit_per_minute: Optional[int] = None,
        capacity: Optional[int] = None,
    ) -> None:
        super().__init__(app)
        if limiter is not None:
            self._limiter = limiter
        elif limit_per_minute is not None:
            self._limiter = RateLimiter(limit_per_minute, capacity=capacity)
        else:
            configured_limit = int(os.environ.get("INFERRA_RATE_LIMIT_PER_MINUTE", "10000"))
            self._limiter = RateLimiter(configured_limit, capacity=capacity)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if self._is_exempt(path):
            return await call_next(request)

        key = self._identity_key(request)
        if not self._limiter.check(key):
            log.warning("rate_limit_exceeded", client=key, path=path)
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Rate limit exceeded"},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self._limiter.requests_per_minute),
                },
            )
        return await call_next(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        return any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in EXEMPT_PREFIXES
            if prefix != "/"
        ) or path == "/"

    @staticmethod
    def _identity_key(request: Request) -> str:
        api_key = request.headers.get("x-api-key", "")
        if not api_key:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                api_key = auth_header[7:].strip()
        if api_key:
            digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            return f"api_key:{digest}"
        return f"client:{request.client.host if request.client else 'unknown'}"
