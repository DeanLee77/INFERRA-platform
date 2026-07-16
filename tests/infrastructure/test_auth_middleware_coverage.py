"""Focused fail-closed coverage for authentication middleware."""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.auth_middleware import (
    ApiKeyAuthMiddleware,
    _AuthFailure,
    _b64url_encode,
    _env_bool,
    _parse_scopes,
)


def _protected_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware)

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    @app.post("/mutating")
    async def mutating():
        return {"ok": True}

    return app


def _signed_jwt(header: dict, payload: dict, secret: str) -> str:
    header_segment = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"


def test_enabled_auth_without_any_secret_returns_service_unavailable() -> None:
    with patch(
        "src.infrastructure.auth_middleware.get_feature_flags",
        return_value=FeatureFlags(auth_enabled=True),
    ), patch.dict("os.environ", {}, clear=True):
        response = TestClient(_protected_app()).get("/protected")

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": "Authentication is enabled but no API key or JWT secret is configured",
    }


def test_csrf_allows_safe_methods_and_matching_double_submit_cookie() -> None:
    environment = {
        "INFERRA_API_KEY": "secret",
        "INFERRA_CSRF_PROTECTION": "true",
    }
    with patch(
        "src.infrastructure.auth_middleware.get_feature_flags",
        return_value=FeatureFlags(auth_enabled=True),
    ), patch.dict("os.environ", environment, clear=True):
        client = TestClient(_protected_app())
        safe = client.get("/protected", headers={"x-api-key": "secret"})
        client.cookies.set("inferra_csrf_token", "double-submit-token")
        cookie = client.post(
            "/mutating",
            headers={
                "x-api-key": "secret",
                "x-csrf-token": "double-submit-token",
            },
        )

    assert safe.status_code == 200
    assert cookie.status_code == 200


def test_jwt_validation_rejects_invalid_temporal_and_subject_claims() -> None:
    secret = "jwt-secret"
    now = int(time.time())

    with pytest.raises(_AuthFailure, match="Invalid JWT"):
        ApiKeyAuthMiddleware._verify_hs256_jwt("not-a-jwt", secret)
    with pytest.raises(_AuthFailure, match="Unsupported JWT algorithm"):
        ApiKeyAuthMiddleware._verify_hs256_jwt(
            _signed_jwt({"alg": "RS256"}, {"sub": "user"}, secret),
            secret,
        )
    with pytest.raises(_AuthFailure, match="JWT expired"):
        ApiKeyAuthMiddleware._verify_hs256_jwt(
            _signed_jwt({"alg": "HS256"}, {"sub": "user", "exp": now - 1}, secret),
            secret,
        )
    with pytest.raises(_AuthFailure, match="JWT is not active yet"):
        ApiKeyAuthMiddleware._verify_hs256_jwt(
            _signed_jwt({"alg": "HS256"}, {"sub": "user", "nbf": now + 60}, secret),
            secret,
        )
    with pytest.raises(_AuthFailure, match="JWT is missing subject"):
        ApiKeyAuthMiddleware._verify_hs256_jwt(
            _signed_jwt({"alg": "HS256"}, {"scope": "read"}, secret),
            secret,
        )


def test_scope_and_boolean_parsers_cover_iterable_scalar_and_invalid_values() -> None:
    assert _parse_scopes(["read", "rules:write"], default={"default"}) == {
        "read",
        "rules:write",
    }
    assert _parse_scopes(42, default={"default"}) == {"42"}

    with patch.dict("os.environ", {"INVALID_BOOL": "sometimes"}, clear=True):
        assert _env_bool("INVALID_BOOL", True) is True
