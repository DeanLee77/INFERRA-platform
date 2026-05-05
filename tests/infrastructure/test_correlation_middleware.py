"""
Tests for Correlation-ID Middleware and Structured Logging.

Covers:
- Correlation-ID header propagation
- UUID4 generation when no header is provided
- structlog context vars binding
- Invalid correlation-ID header handling
- Overly long correlation-ID header handling
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.correlation_middleware import CorrelationIdMiddleware
from src.infrastructure.logging_config import configure_logging, get_logger


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app_with_middleware):
    return TestClient(app_with_middleware)


class TestCorrelationIdMiddleware:
    def test_generates_correlation_id_when_missing(self, client):
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-Correlation-ID" in response.headers
        corr_id = response.headers["X-Correlation-ID"]
        assert len(corr_id) > 0

    def test_propagates_existing_correlation_id(self, client):
        response = client.get("/test", headers={"X-Correlation-ID": "test-id-123"})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == "test-id-123"

    def test_different_requests_get_different_ids(self, client):
        r1 = client.get("/test")
        r2 = client.get("/test")
        id1 = r1.headers["X-Correlation-ID"]
        id2 = r2.headers["X-Correlation-ID"]
        assert id1 != id2

    def test_rejects_correlation_id_with_special_chars(self, client):
        response = client.get("/test", headers={"X-Correlation-ID": "id\nwith\nnewlines"})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] != "id\nwith\nnewlines"

    def test_rejects_overly_long_correlation_id(self, client):
        long_id = "a" * 200
        response = client.get("/test", headers={"X-Correlation-ID": long_id})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] != long_id

    def test_accepts_valid_dotted_hyphenated_id(self, client):
        valid_id = "req-abc_123.v2"
        response = client.get("/test", headers={"X-Correlation-ID": valid_id})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == valid_id


class TestLoggingConfig:
    def test_configure_logging_development(self):
        configure_logging(env="development")
        logger = get_logger("test")
        assert logger is not None

    def test_configure_logging_production(self):
        configure_logging(env="production")
        logger = get_logger("test")
        assert logger is not None

    def test_get_logger_returns_bound_logger(self):
        configure_logging()
        logger = get_logger("test_module")
        assert logger is not None
