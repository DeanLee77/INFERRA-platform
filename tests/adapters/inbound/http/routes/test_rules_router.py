"""
Integration tests for the rules router.

Covers CRUD operations on rules via the /service/rule endpoints
using FastAPI TestClient with database dependency overrides.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.main import app
from src.domain.exceptions import RuleValidationError
from src.domain.models.rule import RuleEntity
from src.services.rule_validation_service import RuleValidationService


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def client(mock_db):
    """Create a test client with DB dependency overridden."""
    from src.adapters.inbound.http.dependencies import get_db_session

    def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# =============================================================================
# GET /service/rule/searchRuleByName
# =============================================================================

class TestSearchRuleByName:
    """Tests for GET /service/rule/searchRuleByName."""

    @patch("src.services.rule_service.RuleService.get_rule_by_name")
    def test_search_rule_found(self, mock_get, client, mock_db):
        """Test 200 when rule is found."""
        rule = RuleEntity(rule_id=1, name="Test Rule", category="Cat", description="Desc")
        mock_get.return_value = rule

        response = client.get("/service/rule/searchRuleByName?ruleName=Test+Rule")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Rule"

    @patch("src.services.rule_service.RuleService.get_rule_by_name")
    def test_search_rule_not_found(self, mock_get, client, mock_db):
        """Test 404 when rule does not exist."""
        mock_get.side_effect = LookupError("Rule 'NonExistent' was not found")

        response = client.get("/service/rule/searchRuleByName?ruleName=NonExistent")

        assert response.status_code == 404

    def test_search_rule_missing_param(self, client, mock_db):
        """Test 422 when ruleName query parameter is missing."""
        response = client.get("/service/rule/searchRuleByName")
        assert response.status_code == 422


# =============================================================================
# GET /service/rule/findRuleTreeDataByName
# =============================================================================

class TestFindRuleTreeData:
    """Tests for GET /service/rule/findRuleTreeDataByName."""

    @patch("src.services.rule_service.RuleService.get_rule_tree_data")
    @patch("src.services.rule_service.RuleService.get_rule_text")
    def test_find_rule_tree_data(self, mock_text, mock_tree, client, mock_db):
        """Test 200 when rule tree data is found."""
        mock_text.return_value = "INPUT x AS NUMBER\nx > 10"
        mock_tree.return_value = "INPUT x AS NUMBER\nx > 10"

        response = client.get("/service/rule/findRuleTreeDataByName?ruleName=Test+Rule")

        assert response.status_code == 200
        data = response.json()
        assert "ruleTreeData" in data


# =============================================================================
# GET /service/rule/findRuleTextByName
# =============================================================================

class TestFindRuleText:
    """Tests for GET /service/rule/findRuleTextByName."""

    @patch("src.services.rule_service.RuleService.get_rule_text")
    def test_find_rule_text(self, mock_text, client, mock_db):
        """Test 200 when rule text is found."""
        mock_text.return_value = "INPUT x AS NUMBER\nx > 10"

        response = client.get("/service/rule/findRuleTextByName?ruleName=Test+Rule")

        assert response.status_code == 200
        data = response.json()
        assert "ruleText" in data
        assert data["ruleText"] == "INPUT x AS NUMBER\nx > 10"

    @patch("src.services.rule_service.RuleService.get_rule_text")
    def test_find_rule_text_not_found(self, mock_text, client, mock_db):
        """Test 404 when rule text is not found."""
        mock_text.side_effect = LookupError("Rule 'missing' was not found")

        response = client.get("/service/rule/findRuleTextByName?ruleName=missing")

        assert response.status_code == 404


# =============================================================================
# GET /service/rule/findAllRules
# =============================================================================

class TestFindAllRules:
    """Tests for GET /service/rule/findAllRules."""

    @patch("src.services.rule_service.RuleService.list_rules")
    def test_find_all_rules(self, mock_list, client, mock_db):
        """Test 200 returning list of rules."""
        mock_list.return_value = [
            {"rule_id": 1, "name": "Rule 1", "category": "Cat 1", "description": "Desc 1"},
            {"rule_id": 2, "name": "Rule 2", "category": "Cat 2", "description": "Desc 2"},
        ]

        response = client.get("/service/rule/findAllRules")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Rule 1"

    @patch("src.services.rule_service.RuleService.list_rules")
    def test_find_all_rules_empty(self, mock_list, client, mock_db):
        """Test 200 returning empty list."""
        mock_list.return_value = []

        response = client.get("/service/rule/findAllRules")

        assert response.status_code == 200
        assert response.json() == []


# =============================================================================
# POST /service/rule/updateRule
# =============================================================================

class TestUpdateRule:
    """Tests for POST /service/rule/updateRule."""

    @patch("src.services.rule_service.RuleService.update_rule")
    def test_update_rule_success(self, mock_update, client, mock_db):
        """Test 200 when rule is updated."""
        rule = RuleEntity(rule_id=1, name="Updated Rule", category="Updated Category", description="Desc")
        mock_update.return_value = rule

        response = client.post(
            "/service/rule/updateRule",
            json={"oldRuleName": "Old Rule", "newRuleName": "Updated Rule", "newRuleCategory": "Updated Category"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["newRuleName"] == "Updated Rule"
        assert data["newCategory"] == "Updated Category"

    @patch("src.services.rule_service.RuleService.update_rule")
    def test_update_rule_not_found(self, mock_update, client, mock_db):
        """Test 404 when rule to update is not found."""
        mock_update.side_effect = LookupError("Rule 'Old' was not found")

        response = client.post(
            "/service/rule/updateRule",
            json={"oldRuleName": "Old", "newRuleName": "New", "newRuleCategory": "Cat"},
        )

        assert response.status_code == 404


# =============================================================================
# POST /service/rule/createNewRule
# =============================================================================

class TestCreateNewRule:
    """Tests for POST /service/rule/createNewRule."""

    @patch("src.services.rule_service.RuleService.create_rule")
    def test_create_new_rule(self, mock_create, client, mock_db):
        """Test 200 when a new rule is created."""
        rule = RuleEntity(rule_id=1, name="New Rule", category="Test", description="Test description")
        mock_create.return_value = rule

        response = client.post(
            "/service/rule/createNewRule",
            json={"name": "New Rule", "category": "Test", "description": "Test description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ruleName"] == "New Rule"
        assert data["category"] == "Test"
        assert data["description"] == "Test description"


# =============================================================================
# POST /service/rule/saveConvertedRule
# =============================================================================

class TestSaveConvertedRule:
    """Tests for POST /service/rule/saveConvertedRule."""

    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_save_converted_rule(self, mock_save, client, mock_db):
        """Test 200 when a converted rule is saved."""
        rule = RuleEntity(rule_id=1, name="Converted Rule", category="Converted", description="Desc")
        mock_save.return_value = rule

        response = client.post(
            "/service/rule/saveConvertedRule",
            json={
                "name": "Converted Rule",
                "category": "Converted",
                "description": "Desc",
                "ruleText": "INPUT x AS NUMBER\nx > 10",
                "waived_error_ids": ["TYPE_MISMATCH:x"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ruleName"] == "Converted Rule"
        mock_save.assert_called_once_with(
            "Converted Rule",
            "Converted",
            "Desc",
            "INPUT x AS NUMBER\nx > 10",
            waived_error_ids=["TYPE_MISMATCH:x"],
        )


# =============================================================================
# POST /service/rule/createFile
# =============================================================================

class TestCreateFile:
    """Tests for POST /service/rule/createFile."""

    @patch("src.services.rule_service.RuleService.create_rule_file")
    def test_create_file(self, mock_create_file, client, mock_db):
        """Test 200 when a rule file is created."""
        mock_create_file.return_value = "INPUT x AS NUMBER\nx > 10"

        response = client.post(
            "/service/rule/createFile",
            json={
                "ruleName": "Test Rule",
                "ruleText": "INPUT x AS NUMBER\nx > 10",
                "waived_error_ids": ["TYPE_MISMATCH:x"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "ruleText" in data
        mock_create_file.assert_called_once_with(
            "Test Rule",
            "INPUT x AS NUMBER\nx > 10",
            waived_error_ids=["TYPE_MISMATCH:x"],
        )


# =============================================================================
# GET /service/rule/targetNodeNameList
# =============================================================================

class TestTargetNodeNameList:
    """Tests for GET /service/rule/targetNodeNameList."""

    @patch("src.services.rule_service.RuleService.get_target_node_names")
    def test_target_node_name_list(self, mock_targets, client, mock_db):
        """Test 200 returning list of target node names."""
        mock_targets.return_value = ["node1", "node2", "node3"]

        response = client.get("/service/rule/targetNodeNameList?ruleName=Test+Rule")

        assert response.status_code == 200
        assert response.json() == ["node1", "node2", "node3"]

    @patch("src.services.rule_service.RuleService.get_target_node_names")
    def test_target_node_name_list_not_found(self, mock_targets, client, mock_db):
        """Test 404 when rule does not exist."""
        mock_targets.side_effect = LookupError("Rule 'missing' was not found")

        response = client.get("/service/rule/targetNodeNameList?ruleName=missing")

        assert response.status_code == 404


# =============================================================================
# POST /service/rule/saveConvertedRule — Validation Gate
# =============================================================================

class TestSaveConvertedRuleValidationGate:
    """Integration tests: validation gate returns 422 for invalid rules."""

    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_valid_rule_saves_normally(self, mock_save, client, mock_db):
        """Valid rule text returns 200."""
        rule = RuleEntity(rule_id=1, name="ok_rule", category="cat", description="desc")
        mock_save.return_value = rule

        response = client.post(
            "/service/rule/saveConvertedRule",
            json={
                "name": "ok_rule",
                "category": "cat",
                "description": "desc",
                "ruleText": "INPUT age AS NUMBER\nage > 18\n",
            },
        )

        assert response.status_code == 200

    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_duplicate_declaration_returns_422(self, mock_save, client, mock_db):
        """Duplicate INPUT declarations return 422 with structured errors."""
        mock_save.side_effect = RuleValidationError(
            errors=list(RuleValidationService().validate(
                "INPUT x AS NUMBER\nINPUT x AS NUMBER\n", "bad_rule",
            ).errors),
            rule_name="bad_rule",
        )

        response = client.post(
            "/service/rule/saveConvertedRule",
            json={
                "name": "bad_rule",
                "category": "cat",
                "description": "desc",
                "ruleText": "INPUT x AS NUMBER\nINPUT x AS NUMBER\n",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False
        assert data["detail"]["rule_name"] == "bad_rule"
        assert any(
            e["code"] == "DUPLICATE_DECLARATION"
            for e in data["detail"]["errors"]
        )

    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_cyclic_dependency_returns_422(self, mock_save, client, mock_db):
        """Cyclic dependency returns 422 with structured errors."""
        mock_save.side_effect = RuleValidationError(
            errors=list(RuleValidationService().validate(
                "INPUT a AS NUMBER\nINPUT b AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n",
                "cyclic_rule",
            ).errors),
            rule_name="cyclic_rule",
        )

        response = client.post(
            "/service/rule/saveConvertedRule",
            json={
                "name": "cyclic_rule",
                "category": "cat",
                "description": "desc",
                "ruleText": "INPUT a AS NUMBER\nINPUT b AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert any(
            e["code"] == "CYCLIC_DEPENDENCY"
            for e in data["detail"]["errors"]
        )

    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_empty_rule_returns_422(self, mock_save, client, mock_db):
        """Empty rule text returns 422."""
        mock_save.side_effect = RuleValidationError(
            errors=list(RuleValidationService().validate("", "empty_rule").errors),
            rule_name="empty_rule",
        )

        response = client.post(
            "/service/rule/saveConvertedRule",
            json={
                "name": "empty_rule",
                "category": "cat",
                "description": "desc",
                "ruleText": "",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert any(
            e["code"] == "EMPTY_RULE"
            for e in data["detail"]["errors"]
        )


# =============================================================================
# POST /service/rule/createFile — Validation Gate
# =============================================================================

class TestCreateFileValidationGate:
    """Integration tests: validation gate returns 422 for invalid rule files."""

    @patch("src.services.rule_service.RuleService.create_rule_file")
    def test_valid_file_saves_normally(self, mock_create_file, client, mock_db):
        """Valid rule file returns 200."""
        mock_create_file.return_value = "INPUT age AS NUMBER\nage > 18\n"

        response = client.post(
            "/service/rule/createFile",
            json={
                "ruleName": "Test Rule",
                "ruleText": "INPUT age AS NUMBER\nage > 18\n",
            },
        )

        assert response.status_code == 200

    @patch("src.services.rule_service.RuleService.create_rule_file")
    def test_invalid_file_returns_422(self, mock_create_file, client, mock_db):
        """Invalid rule text returns 422 with structured errors."""
        mock_create_file.side_effect = RuleValidationError(
            errors=list(RuleValidationService().validate(
                "INPUT x AS NUMBER\nINPUT x AS NUMBER\n", "bad_file",
            ).errors),
            rule_name="bad_file",
        )

        response = client.post(
            "/service/rule/createFile",
            json={
                "ruleName": "bad_file",
                "ruleText": "INPUT x AS NUMBER\nINPUT x AS NUMBER\n",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False
        assert data["detail"]["rule_name"] == "bad_file"
        assert any(
            e["code"] == "DUPLICATE_DECLARATION"
            for e in data["detail"]["errors"]
        )

    @patch("src.services.rule_service.RuleService.create_rule_file")
    def test_cyclic_file_returns_422(self, mock_create_file, client, mock_db):
        """Cyclic rule file returns 422 with structured errors."""
        mock_create_file.side_effect = RuleValidationError(
            errors=list(RuleValidationService().validate(
                "INPUT a AS NUMBER\nINPUT b AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n",
                "cyclic_file",
            ).errors),
            rule_name="cyclic_file",
        )

        response = client.post(
            "/service/rule/createFile",
            json={
                "ruleName": "cyclic_file",
                "ruleText": "INPUT a AS NUMBER\nINPUT b AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert any(
            e["code"] == "CYCLIC_DEPENDENCY"
            for e in data["detail"]["errors"]
        )


# =============================================================================
# POST /service/rule/createNewRule — No Validation Gate
# =============================================================================

class TestCreateNewRuleNoValidationGate:
    """Integration tests: createNewRule is NOT gated (no rule text)."""

    @patch("src.services.rule_service.RuleService.create_rule")
    def test_create_rule_no_validation(self, mock_create, client, mock_db):
        """createNewRule creates metadata-only rule without validation."""
        rule = RuleEntity(rule_id=1, name="New Rule", category="cat", description="desc")
        mock_create.return_value = rule

        response = client.post(
            "/service/rule/createNewRule",
            json={"name": "New Rule", "category": "cat", "description": "desc"},
        )

        assert response.status_code == 200
        assert response.json()["ruleName"] == "New Rule"
