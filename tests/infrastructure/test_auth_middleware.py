from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.auth_middleware import ApiKeyAuthMiddleware, RateLimitMiddleware


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


def test_auth_middleware_rejects_bad_jwt_signature():
    token = _jwt({"sub": "user-123", "exp": int(time.time()) + 60}, "other-secret")

    with patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with patch.dict("os.environ", {"INFERRA_JWT_SECRET": "jwt-secret"}, clear=True):
            response = TestClient(_app_with_auth()).get("/whoami", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401


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
