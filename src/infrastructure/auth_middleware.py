import base64
import hashlib
import hmac
import json
import os
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.domain.state.feature_flags import get_feature_flags
from src.infrastructure.rate_limiter import RateLimitMiddleware
from src.infrastructure.secrets import read_secret


class ApiKeyAuthMiddleware:
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

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not get_feature_flags().auth_enabled or self._is_exempt(path):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        try:
            user_id = self._authenticate(request)
            self._validate_csrf(request)
        except _AuthConfigError as exc:
            response = JSONResponse(
                status_code=503,
                content={"success": False, "error": str(exc)},
            )
            await response(scope, receive, send)
            return
        except _AuthFailure as exc:
            response = JSONResponse(
                status_code=401,
                content={"success": False, "error": str(exc)},
            )
            await response(scope, receive, send)
            return
        except _CsrfFailure as exc:
            response = JSONResponse(
                status_code=403,
                content={"success": False, "error": str(exc)},
            )
            await response(scope, receive, send)
            return

        scope["inferra_user_id"] = user_id
        await self.app(scope, receive, send)

    def _is_exempt(self, path: str) -> bool:
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in self.EXEMPT_PREFIXES if prefix != "/") or path == "/"

    @staticmethod
    def _bearer_token(request: Request) -> str:
        value = request.headers.get("authorization", "")
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return ""

    def _authenticate(self, request: Request) -> str:
        configured_key = read_secret("INFERRA_API_KEY")
        jwt_secret = read_secret("INFERRA_JWT_SECRET")
        supplied_api_key = request.headers.get("x-api-key")
        bearer_token = self._bearer_token(request)

        if jwt_secret and bearer_token and bearer_token != configured_key:
            return self._verify_hs256_jwt(bearer_token, jwt_secret)

        supplied = supplied_api_key or bearer_token
        if not configured_key and not jwt_secret:
            raise _AuthConfigError("Authentication is enabled but no API key or JWT secret is configured")
        if configured_key and supplied == configured_key:
            return os.environ.get("INFERRA_API_KEY_OWNER_ID", "api-key")
        raise _AuthFailure("Invalid or missing API key/JWT")

    def _validate_csrf(self, request: Request) -> None:
        if os.environ.get("INFERRA_CSRF_PROTECTION", "false").lower() not in {"1", "true", "yes"}:
            return
        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        supplied = request.headers.get("x-csrf-token", "")
        configured = read_secret("INFERRA_CSRF_TOKEN", "") or ""
        if configured and hmac.compare_digest(supplied, configured):
            return
        cookie = request.cookies.get("inferra_csrf_token", "")
        if supplied and cookie and hmac.compare_digest(supplied, cookie):
            return
        raise _CsrfFailure("Missing or invalid CSRF token")

    @staticmethod
    def _verify_hs256_jwt(token: str, secret: str) -> str:
        try:
            header_segment, payload_segment, signature_segment = token.split(".")
            header = json.loads(_b64url_decode(header_segment))
            payload = json.loads(_b64url_decode(payload_segment))
        except Exception as exc:
            raise _AuthFailure("Invalid JWT") from exc

        if header.get("alg") != "HS256":
            raise _AuthFailure("Unsupported JWT algorithm")

        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected = _b64url_encode(hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature_segment):
            raise _AuthFailure("Invalid JWT signature")

        now = int(time.time())
        exp = payload.get("exp")
        if exp is not None and int(exp) < now:
            raise _AuthFailure("JWT expired")
        nbf = payload.get("nbf")
        if nbf is not None and int(nbf) > now:
            raise _AuthFailure("JWT is not active yet")

        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise _AuthFailure("JWT is missing subject")
        return str(user_id)


class _AuthConfigError(RuntimeError):
    pass


class _AuthFailure(RuntimeError):
    pass


class _CsrfFailure(RuntimeError):
    pass


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
