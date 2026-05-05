"""
Tests for the Validation API Router.
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestValidationRouter:
    """Tests for POST /api/v1/rules/validate."""

    def test_validate_valid_rule(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_text": "INPUT age AS NUMBER\nage > 18\n",
                "rule_name": "test_rule",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert "errors" in data
        assert "warnings" in data

    def test_validate_empty_rule(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={"rule_text": "", "rule_name": "empty_rule"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "EMPTY_RULE"

    def test_validate_invalid_rule_with_duplicate(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_text": "FIXED rate IS 10\nFIXED rate IS 20\n",
                "rule_name": "dup_rule",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any(e["code"] == "DUPLICATE_DECLARATION" for e in data["errors"])

    def test_validate_rule_with_type_mismatch(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_text": "INPUT flag AS BOOLEAN\nflag > 5\n",
                "rule_name": "mismatch_rule",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any(e["code"] == "TYPE_MISMATCH" for e in data["errors"])

    def test_validate_rule_without_name(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={"rule_text": "INPUT age AS NUMBER\n"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data

    def test_validate_returns_warnings_for_unused(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_text": "INPUT age AS NUMBER\nINPUT name AS STRING\nage > 18\n",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert any(w["code"] == "UNUSED_DECLARATION" for w in data["warnings"])

    def test_validate_cyclic_rule(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_text": "INPUT base AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any(e["code"] == "CYCLIC_DEPENDENCY" for e in data["errors"])
