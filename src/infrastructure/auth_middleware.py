import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.domain.state.feature_flags import get_feature_flags


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Optional API-key authentication for non-health endpoints."""

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

    async def dispatch(self, request: Request, call_next) -> Response:
        if not get_feature_flags().auth_enabled or self._is_exempt(request.url.path):
            return await call_next(request)

        configured_key = os.environ.get("INFERRA_API_KEY")
        if not configured_key:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Authentication is enabled but no API key is configured"},
            )

        supplied = request.headers.get("x-api-key") or self._bearer_token(request)
        if supplied != configured_key:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid or missing API key"},
            )
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in self.EXEMPT_PREFIXES if prefix != "/") or path == "/"

    @staticmethod
    def _bearer_token(request: Request) -> str:
        value = request.headers.get("authorization", "")
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return ""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small in-process rate limiter for workstation and single-worker deployments."""

    EXEMPT_PREFIXES = ApiKeyAuthMiddleware.EXEMPT_PREFIXES

    def __init__(self, app, limit_per_minute: int | None = None) -> None:
        super().__init__(app)
        self.limit_per_minute = int(
            limit_per_minute
            if limit_per_minute is not None
            else os.environ.get("INFERRA_RATE_LIMIT_PER_MINUTE", "10000")
        )
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        if self.limit_per_minute <= 0 or self._is_exempt(request.url.path):
            return await call_next(request)
        now = time.time()
        key = request.client.host if request.client else "unknown"
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Rate limit exceeded"},
            )
        hits.append(now)
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        return any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in self.EXEMPT_PREFIXES
            if prefix != "/"
        ) or path == "/"
