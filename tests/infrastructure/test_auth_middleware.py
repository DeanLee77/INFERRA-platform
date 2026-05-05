from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.auth_middleware import ApiKeyAuthMiddleware, RateLimitMiddleware


def _app_with_auth():
    app = FastAPI()
    app.add_middleware(ApiKeyAuthMiddleware)

    @app.get("/protected")
    async def protected():
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
