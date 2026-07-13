"""
Tests for the Validation API Router.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.domain.models.rule import RuleFileEntity
from src.main import app


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    """Create a test client for the FastAPI app."""
    from src.adapters.inbound.http.dependencies import get_db_session

    def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
        assert data["errors"][0]["waiver_id"] == "EMPTY_RULE"

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
        assert any(
            e["code"] == "DUPLICATE_DECLARATION"
            and e["waiver_id"] == "DUPLICATE_DECLARATION:rate"
            for e in data["errors"]
        )

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

    @patch("src.adapters.inbound.http.routes.validation.RuleRepositoryImpl")
    def test_validate_draft_resolves_stored_import(self, mock_repository_cls, client):
        repository = mock_repository_cls.return_value
        repository.find_rule_text_by_rule_name.return_value = RuleFileEntity(
            file_id=2,
            rule_id=2,
            files=(
                "INPUT imported age AS NUMBER\n"
                "FIXED minimum imported age IS 18\n"
            ).encode("utf-8"),
        )

        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_name": "root_rule",
                "rule_text": (
                    "IMPORT: common_rule\n"
                    "eligible for imported benefit\n"
                    "    AND imported age >= minimum imported age\n"
                ),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []
        repository.find_rule_text_by_rule_name.assert_any_call("common_rule")

    @patch("src.adapters.inbound.http.routes.validation.RuleRepositoryImpl")
    def test_validate_draft_reports_missing_import(self, mock_repository_cls, client):
        repository = mock_repository_cls.return_value
        repository.find_rule_text_by_rule_name.return_value = None

        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_name": "root_rule",
                "rule_text": (
                    "IMPORT: missing_rule\n"
                    "eligible for imported benefit\n"
                    "    AND imported age >= minimum imported age\n"
                ),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any(
            error["code"] == "UNRESOLVED_IMPORT"
            and error["node_name"] == "missing_rule"
            and "missing_rule" in error["message"]
            for error in data["errors"]
        )
        assert "Traceback" not in response.text

    @patch("src.adapters.inbound.http.routes.validation.RuleRepositoryImpl")
    def test_validate_response_exposes_ontology_review_queue(self, mock_repository_cls, client):
        repository = mock_repository_cls.return_value
        repository.find_rule_text_by_rule_name.return_value = None

        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_name": "benefit_rule",
                "rule_text": (
                    "INPUT benefit age AS FOOBAR\n"
                    "benefit eligibility\n"
                    "    AND benefit age > 18\n"
                ),
            },
        )

        assert response.status_code == 200
        data = response.json()
        ontology_warning = next(
            warning
            for warning in data["warnings"]
            if warning["code"] == "ONTOLOGY_DECLARATION_TYPE_UNMAPPED"
        )
        assert ontology_warning["severity"] == "high-risk"
        assert ontology_warning["source"] == "ontology"
        assert ontology_warning["review_required"] is True
        assert data["review_queue"]
        assert data["review_queue"][0]["approval_state"] == "candidate"
        assert data["review_queue"][0]["requires_rule_approval"] is True
        assert data["review_queue"][0]["mutates_assets"] is False
