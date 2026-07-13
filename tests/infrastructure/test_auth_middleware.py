import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from src.adapters.inbound.http.dependencies import require_scope
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.auth_middleware import ApiKeyAuthMiddleware, RateLimitMiddleware
from src.main import create_app


def _app_with_auth():
    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware)

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    @app.get("/whoami")
    async def whoami(request: Request):
        return {"user_id": request.scope.get("inferra_user_id")}

    @app.post("/mutating")
    async def mutating():
        return {"ok": True}

    @app.post("/rule-write", dependencies=[Depends(require_scope("rules:write"))])
    async def rule_write():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/live")
    async def live():
        return {"ok": True}

    return app


def test_auth_middleware_skips_when_disabled():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=False)):
        response = TestClient(_app_with_auth()).get("/protected")

    assert response.status_code == 200


def test_auth_middleware_rejects_missing_key_when_enabled():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict("os.environ", {"INFERRA_API_KEY": "secret"}):
            response = TestClient(_app_with_auth()).get("/protected")

    assert response.status_code == 401


def test_auth_middleware_accepts_api_key():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict("os.environ", {"INFERRA_API_KEY": "secret"}):
            response = TestClient(_app_with_auth()).get("/protected", headers={"x-api-key": "secret"})

    assert response.status_code == 200


def test_scope_dependency_rejects_authenticated_api_key_without_write_scope():
    flags = FeatureFlags(auth_enabled=True)
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags), patch(
        "src.adapters.inbound.http.dependencies.get_feature_flags", return_value=flags
    ):
        with patch.dict("os.environ", {"INFERRA_API_KEY": "secret"}, clear=True):
            response = TestClient(_app_with_auth()).post("/rule-write", headers={"x-api-key": "secret"})

    assert response.status_code == 403


def test_scope_dependency_accepts_api_key_with_write_scope():
    flags = FeatureFlags(auth_enabled=True)
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags), patch(
        "src.adapters.inbound.http.dependencies.get_feature_flags", return_value=flags
    ):
        with patch.dict(
            "os.environ",
            {"INFERRA_API_KEY": "secret", "INFERRA_API_KEY_SCOPES": "read,rules:write"},
            clear=True,
        ):
            response = TestClient(_app_with_auth()).post("/rule-write", headers={"x-api-key": "secret"})

    assert response.status_code == 200


def test_auth_middleware_sets_api_key_owner_scope():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict("os.environ", {"INFERRA_API_KEY": "secret", "INFERRA_API_KEY_OWNER_ID": "svc-1"}):
            response = TestClient(_app_with_auth()).get("/whoami", headers={"x-api-key": "secret"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "svc-1"


def _jwt(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}

    def enc(value: dict | bytes) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8") if isinstance(value, dict) else value
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    header_segment = enc(header)
    payload_segment = enc(payload)
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{enc(signature)}"


def test_auth_middleware_accepts_hs256_jwt_and_sets_subject_scope():
    token = _jwt({"sub": "user-123", "exp": int(time.time()) + 60}, "jwt-secret")

    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict("os.environ", {"INFERRA_JWT_SECRET": "jwt-secret"}, clear=True):
            response = TestClient(_app_with_auth()).get("/whoami", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "user-123"


def test_scope_dependency_accepts_jwt_scope_claim():
    token = _jwt(
        {"sub": "user-123", "scope": "read rules:write", "exp": int(time.time()) + 60},
        "jwt-secret",
    )
    flags = FeatureFlags(auth_enabled=True)

    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags), patch(
        "src.adapters.inbound.http.dependencies.get_feature_flags", return_value=flags
    ):
        with patch.dict("os.environ", {"INFERRA_JWT_SECRET": "jwt-secret"}, clear=True):
            response = TestClient(_app_with_auth()).post(
                "/rule-write",
                headers={"authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200


def test_auth_middleware_rejects_bad_jwt_signature():
    token = _jwt({"sub": "user-123", "exp": int(time.time()) + 60}, "other-secret")

    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict("os.environ", {"INFERRA_JWT_SECRET": "jwt-secret"}, clear=True):
            response = TestClient(_app_with_auth()).get("/whoami", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_create_app_rejects_production_auth_disabled():
    with patch.dict("os.environ", {"INFERRA_ENV": "production", "INFERRA_AUTH_ENABLED": "false"}, clear=True):
        with pytest.raises(RuntimeError, match="INFERRA_AUTH_ENABLED=true"):
            create_app()


def test_create_app_rejects_production_auth_without_secret():
    with patch.dict("os.environ", {"INFERRA_ENV": "production", "INFERRA_AUTH_ENABLED": "true"}, clear=True):
        with pytest.raises(RuntimeError, match="requires INFERRA_API_KEY or INFERRA_JWT_SECRET"):
            create_app()


def test_production_rules_endpoint_rejects_unauthenticated_request():
    flags = FeatureFlags(auth_enabled=True)
    with patch.dict(
        "os.environ",
        {"INFERRA_ENV": "production", "INFERRA_AUTH_ENABLED": "true", "INFERRA_API_KEY": "secret"},
        clear=True,
    ), patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags):
        response = TestClient(create_app()).get("/api/v1/rules")

    assert response.status_code == 401


def test_production_rule_write_requires_explicit_scope():
    flags = FeatureFlags(auth_enabled=True)
    with patch.dict(
        "os.environ",
        {
            "INFERRA_ENV": "production",
            "INFERRA_AUTH_ENABLED": "true",
            "INFERRA_API_KEY": "secret",
            "INFERRA_API_KEY_SCOPES": "read,llm:read",
        },
        clear=True,
    ), patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags), patch(
        "src.adapters.inbound.http.dependencies.get_feature_flags", return_value=flags
    ):
        response = TestClient(create_app()).post(
            "/service/rule/createNewRule",
            headers={"x-api-key": "secret"},
            json={},
        )

    assert response.status_code == 403


def test_production_llm_endpoint_requires_llm_scope():
    flags = FeatureFlags(auth_enabled=True)
    with patch.dict(
        "os.environ",
        {
            "INFERRA_ENV": "production",
            "INFERRA_AUTH_ENABLED": "true",
            "INFERRA_API_KEY": "secret",
            "INFERRA_API_KEY_SCOPES": "read",
        },
        clear=True,
    ), patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags), patch(
        "src.adapters.inbound.http.dependencies.get_feature_flags", return_value=flags
    ):
        response = TestClient(create_app()).get(
            "/api/v1/llm/providers",
            headers={"x-api-key": "secret"},
        )

    assert response.status_code == 403


def test_cors_rejects_wildcard_credentials():
    with patch.dict(
        "os.environ",
        {
            "INFERRA_CORS_ALLOWED_ORIGINS": "*",
            "INFERRA_CORS_ALLOW_CREDENTIALS": "true",
        },
        clear=True,
    ):
        client = TestClient(create_app())
        response = client.options(
            "/api/v1/rules",
            headers={
                "Origin": "https://example.invalid",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in response.headers


def test_cors_allows_only_explicit_configured_origin():
    with patch.dict(
        "os.environ",
        {"INFERRA_CORS_ALLOWED_ORIGINS": "https://app.example.com"},
        clear=True,
    ):
        client = TestClient(create_app())
        allowed = client.options(
            "/api/v1/rules",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        blocked = client.options(
            "/api/v1/rules",
            headers={
                "Origin": "https://other.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert "access-control-allow-origin" not in blocked.headers


def test_auth_middleware_enforces_csrf_when_enabled():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict(
            "os.environ",
            {
                "INFERRA_API_KEY": "secret",
                "INFERRA_CSRF_PROTECTION": "true",
                "INFERRA_CSRF_TOKEN": "csrf-1",
            },
            clear=True,
        ):
            client = TestClient(_app_with_auth())
            assert client.post("/mutating", headers={"x-api-key": "secret"}).status_code == 403
            ok = client.post(
                "/mutating",
                headers={"x-api-key": "secret", "x-csrf-token": "csrf-1"},
            )

    assert ok.status_code == 200


def test_auth_middleware_exempts_health():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        response = TestClient(_app_with_auth()).get("/health")

    assert response.status_code == 200


def test_auth_middleware_exempts_liveness():
    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        response = TestClient(_app_with_auth()).get("/live")

    assert response.status_code == 200


def test_rate_limit_middleware_returns_429_after_limit():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=1)

    @app.get("/limited")
    async def limited():
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 429


def test_rate_limit_middleware_exempts_health():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=1)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/live")
    async def live():
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200


def test_rate_limit_middleware_exempts_liveness():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=1)

    @app.get("/live")
    async def live():
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/live").status_code == 200
    assert client.get("/live").status_code == 200
