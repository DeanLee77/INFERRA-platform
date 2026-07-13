import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Iterable

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
            user_id, scopes = self._authenticate(request)
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
        scope["inferra_auth_scopes"] = tuple(scopes)
        await self.app(scope, receive, send)

    def _is_exempt(self, path: str) -> bool:
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in self.EXEMPT_PREFIXES if prefix != "/") or path == "/"

    @staticmethod
    def _bearer_token(request: Request) -> str:
        value = request.headers.get("authorization", "")
        if value.lower().startswith("bearer "):
            return value[7:].strip()
        return ""

    def _authenticate(self, request: Request) -> tuple[str, set[str]]:
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
            return os.environ.get("INFERRA_API_KEY_OWNER_ID", "api-key"), _api_key_scopes()
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
    def _verify_hs256_jwt(token: str, secret: str) -> tuple[str, set[str]]:
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
        return str(user_id), _jwt_scopes(payload)


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


def assert_production_auth_config() -> None:
    """Fail closed before serving a production app with ineffective auth."""
    if os.environ.get("INFERRA_ENV", "").strip().lower() not in {"prod", "production"}:
        return
    if not _env_bool("INFERRA_AUTH_ENABLED", False):
        raise RuntimeError("INFERRA_ENV=production requires INFERRA_AUTH_ENABLED=true")
    if not (_configured_secret("INFERRA_API_KEY") or _configured_secret("INFERRA_JWT_SECRET")):
        raise RuntimeError("Production auth requires INFERRA_API_KEY or INFERRA_JWT_SECRET")


def has_scope(scopes: Iterable[str], required_scope: str) -> bool:
    normalized = {scope.strip() for scope in scopes if scope and scope.strip()}
    if "*" in normalized or required_scope in normalized:
        return True
    namespace = required_scope.split(":", 1)[0]
    return f"{namespace}:*" in normalized


def _api_key_scopes() -> set[str]:
    return _parse_scopes(os.environ.get("INFERRA_API_KEY_SCOPES"), default={"read", "llm:read"})


def _jwt_scopes(payload: dict) -> set[str]:
    claim = payload.get("scope") or payload.get("scp") or payload.get("scopes")
    return _parse_scopes(claim, default={"read"})


def _parse_scopes(value, default: set[str]) -> set[str]:
    if value is None:
        return set(default)
    if isinstance(value, str):
        raw_scopes = value.replace(",", " ").split()
    elif isinstance(value, Iterable):
        raw_scopes = [str(item) for item in value]
    else:
        raw_scopes = [str(value)]
    scopes = {scope.strip() for scope in raw_scopes if scope and scope.strip()}
    return scopes or set(default)


def _configured_secret(name: str) -> bool:
    value = read_secret(name)
    return bool(value and value.strip())


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default
