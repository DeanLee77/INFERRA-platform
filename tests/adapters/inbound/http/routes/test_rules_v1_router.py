from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.domain.models.rule import RuleEntity, RuleFileEntity
from src.main import app


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    from src.adapters.inbound.http.dependencies import get_db_session

    def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestRulesV1Router:
    @patch("src.services.rule_service.RuleService.list_rules")
    def test_list_rule_sets_uses_modern_field_names(self, mock_list, client):
        mock_list.return_value = [
            {
                "rule_id": 1,
                "name": "benefit_eligibility_v1",
                "category": "Benefits",
                "description": "Eligibility rules",
            }
        ]

        response = client.get("/api/v1/rules")

        assert response.status_code == 200
        assert response.json() == [
            {
                "rule_id": 1,
                "rule_name": "benefit_eligibility_v1",
                "category": "Benefits",
                "description": "Eligibility rules",
            }
        ]

    @patch("src.services.rule_service.RuleService.get_latest_rule_file")
    @patch("src.services.rule_service.RuleService.get_rule_by_name")
    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_create_rule_set_saves_and_returns_detail(
        self,
        mock_save,
        mock_get_rule,
        mock_get_file,
        client,
    ):
        mock_get_rule.return_value = RuleEntity(
            rule_id=7,
            name="benefit_eligibility_v1",
            category="Benefits",
            description="Eligibility rules",
        )
        mock_get_file.return_value = RuleFileEntity(
            file_id=11,
            rule_id=7,
            files=b"INPUT age AS NUMBER\nage > 18\n",
        )

        response = client.post(
            "/api/v1/rules",
            json={
                "rule_name": "benefit_eligibility_v1",
                "category": "Benefits",
                "description": "Eligibility rules",
                "rule_text": "INPUT age AS NUMBER\nage > 18\n",
                "waived_error_ids": ["TYPE_MISMATCH:age"],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["rule_name"] == "benefit_eligibility_v1"
        assert data["rule_text"] == "INPUT age AS NUMBER\nage > 18\n"
        assert data["latest_file_id"] == 11
        mock_save.assert_called_once_with(
            "benefit_eligibility_v1",
            "Benefits",
            "Eligibility rules",
            "INPUT age AS NUMBER\nage > 18\n",
            waived_error_ids=["TYPE_MISMATCH:age"],
        )

    @patch("src.services.rule_service.RuleService.get_latest_rule_file")
    @patch("src.services.rule_service.RuleService.get_rule_by_name")
    def test_get_rule_set_returns_latest_rule_text(self, mock_get_rule, mock_get_file, client):
        mock_get_rule.return_value = RuleEntity(
            rule_id=7,
            name="benefit_eligibility_v1",
            category="Benefits",
            description="Eligibility rules",
        )
        mock_get_file.return_value = RuleFileEntity(
            file_id=11,
            rule_id=7,
            files=b"INPUT age AS NUMBER\nage > 18\n",
        )

        response = client.get("/api/v1/rules/benefit_eligibility_v1")

        assert response.status_code == 200
        assert response.json() == {
            "rule_id": 7,
            "rule_name": "benefit_eligibility_v1",
            "category": "Benefits",
            "description": "Eligibility rules",
            "rule_text": "INPUT age AS NUMBER\nage > 18\n",
            "latest_file_id": 11,
        }

    @patch("src.services.rule_service.RuleService.get_latest_rule_file")
    @patch("src.services.rule_service.RuleService.create_rule_file")
    def test_create_rule_set_version_adds_new_file(
        self,
        mock_create_file,
        mock_get_file,
        client,
    ):
        mock_create_file.return_value = "INPUT age AS NUMBER\nage > 21\n"
        mock_get_file.return_value = RuleFileEntity(
            file_id=12,
            rule_id=7,
            files=b"INPUT age AS NUMBER\nage > 21\n",
        )

        response = client.post(
            "/api/v1/rules/benefit_eligibility_v1/versions",
            json={
                "rule_text": "INPUT age AS NUMBER\nage > 21\n",
                "waived_error_ids": ["TYPE_MISMATCH:age"],
            },
        )

        assert response.status_code == 201
        assert response.json() == {
            "rule_name": "benefit_eligibility_v1",
            "rule_text": "INPUT age AS NUMBER\nage > 21\n",
            "latest_file_id": 12,
        }
        mock_create_file.assert_called_once_with(
            "benefit_eligibility_v1",
            "INPUT age AS NUMBER\nage > 21\n",
            waived_error_ids=["TYPE_MISMATCH:age"],
        )

    @patch("src.services.rule_service.RuleService.get_target_node_names")
    def test_list_rule_set_targets(self, mock_targets, client):
        mock_targets.return_value = ["eligible for benefit"]

        response = client.get("/api/v1/rules/benefit_eligibility_v1/targets")

        assert response.status_code == 200
        assert response.json() == ["eligible for benefit"]

    def test_create_rule_set_requires_snake_case_contract(self, client):
        response = client.post(
            "/api/v1/rules",
            json={
                "ruleName": "legacy_style",
                "ruleText": "INPUT age AS NUMBER\nage > 18\n",
            },
        )

        assert response.status_code == 422

    def test_validation_endpoint_is_not_shadowed_by_rule_resource_routes(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_name": "benefit_eligibility_v1",
                "rule_text": "INPUT age AS NUMBER\nage > 18\n",
            },
        )

        assert response.status_code == 200
        assert "valid" in response.json()
