from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.rate_limiter import RateLimiter, RateLimitMiddleware, TokenBucket


def _limited_app(**middleware_kwargs):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, **middleware_kwargs)

    @app.get("/limited")
    async def limited():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


def test_token_bucket_consumes_capacity_and_refuses_when_empty():
    bucket = TokenBucket(rate=0.0, capacity=1)

    assert bucket.consume() is True
    assert bucket.consume() is False


def test_rate_limiter_reset_clears_bucket():
    limiter = RateLimiter(requests_per_minute=1, capacity=1)

    assert limiter.check("client-a") is True
    assert limiter.check("client-a") is False
    limiter.reset("client-a")
    assert limiter.check("client-a") is True


def test_rate_limit_middleware_isolates_api_keys():
    client = TestClient(_limited_app(limit_per_minute=1, capacity=1))

    assert client.get("/limited", headers={"x-api-key": "a"}).status_code == 200
    assert client.get("/limited", headers={"x-api-key": "a"}).status_code == 429
    assert client.get("/limited", headers={"x-api-key": "b"}).status_code == 200


def test_rate_limit_middleware_can_be_disabled():
    client = TestClient(_limited_app(limit_per_minute=0))

    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200


def test_rate_limit_middleware_exempts_health_routes():
    client = TestClient(_limited_app(limit_per_minute=1, capacity=1))

    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
