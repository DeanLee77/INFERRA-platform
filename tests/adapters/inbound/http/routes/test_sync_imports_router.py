"""
Tests for the Sync & Import API Router.

Covers:
- GET /api/v1/sync/status — Celery task status lookup
- GET /api/v1/rules/{rule_name}/imports — Import tree with pagination
- GET /api/v1/rules/{rule_name}/validate — Import-aware rule validation
- Error responses (404, 422)
- Feature flag gating (async_sync_enabled, modular_imports)
"""

import hashlib
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.domain.imports.import_resolver import CircularImportError, ImportDepthExceededError


@pytest.fixture(autouse=True)
def _setup_client():
    from src.main import app
    from src.adapters.inbound.http.dependencies import get_db_session

    app.dependency_overrides[get_db_session] = lambda: None
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestSyncStatus:
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_disabled(self, mock_flags_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.async_sync_enabled = False
        mock_flags_cls.return_value = mock_flags
        response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"
        assert data["rule_name"] == "test_rule"

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_unknown_when_no_tasks(self, mock_flags_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.async_sync_enabled = True
        mock_flags.modular_imports = False
        mock_flags_cls.return_value = mock_flags
        response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unknown"

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_missing_rule_name(self, mock_flags_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.async_sync_enabled = True
        mock_flags.modular_imports = False
        mock_flags_cls.return_value = mock_flags
        response = _setup_client.get("/api/v1/sync/status")
        assert response.status_code == 422

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {"hash1": "task-1"})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_pending_from_inflight_task(self, mock_flags_cls, _setup_client):
        mock_flags = MagicMock(async_sync_enabled=True)
        mock_flags_cls.return_value = mock_flags
        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult.return_value = MagicMock(status="STARTED")

        with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
            response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {"hash1": "task-1"})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_completed_includes_hash(self, mock_flags_cls, _setup_client):
        rule_text = "text"
        source_hash = hashlib.sha256(rule_text.encode()).hexdigest()
        mock_flags = MagicMock(async_sync_enabled=True)
        mock_flags_cls.return_value = mock_flags
        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult.side_effect = [
            MagicMock(status="SUCCESS"),
            MagicMock(status="SUCCESS", result={"hash": source_hash}),
        ]

        with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
            with patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {source_hash: "task-1"}):
                with patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text", return_value=rule_text):
                    response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["source_hash"] == source_hash

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {"hash1": "task-1"})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_failed_includes_error(self, mock_flags_cls, _setup_client):
        rule_text = "text"
        source_hash = hashlib.sha256(rule_text.encode()).hexdigest()
        mock_flags = MagicMock(async_sync_enabled=True)
        mock_flags_cls.return_value = mock_flags
        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult.side_effect = [
            MagicMock(status="SUCCESS"),
            MagicMock(status="FAILURE", result=RuntimeError("boom")),
        ]

        with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
            with patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {source_hash: "task-1"}):
                with patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text", return_value=rule_text):
                    response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "boom" in data["error"]

    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_matches_by_rule_text_hash(self, mock_flags_cls, _setup_client):
        rule_text = "INPUT x AS BOOLEAN"
        source_hash = hashlib.sha256(rule_text.encode()).hexdigest()
        mock_flags = MagicMock(async_sync_enabled=True)
        mock_flags_cls.return_value = mock_flags
        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult.return_value = MagicMock(status="SUCCESS", result={"hash": source_hash})

        with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
            with patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {source_hash: "task-1"}):
                with patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text", return_value=rule_text):
                    response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {"hash1": "task-1"})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_unknown_when_async_result_import_unavailable(self, mock_flags_cls, _setup_client):
        mock_flags = MagicMock(async_sync_enabled=True)
        mock_flags_cls.return_value = mock_flags

        with patch.dict(sys.modules, {"celery.result": None}):
            response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})

        assert response.status_code == 200
        assert response.json()["status"] == "unknown"

    @patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {"hash1": "task-1"})
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_sync_status_unknown_when_final_status_check_fails(self, mock_flags_cls, _setup_client):
        rule_text = "text"
        source_hash = hashlib.sha256(rule_text.encode()).hexdigest()
        mock_flags = MagicMock(async_sync_enabled=True)
        mock_flags_cls.return_value = mock_flags
        mock_celery_result = MagicMock()
        mock_celery_result.AsyncResult.side_effect = [MagicMock(status="SUCCESS"), Exception("backend down")]

        with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
            with patch("src.adapters.inbound.http.routes.sync_imports._inflight_tasks", {source_hash: "task-1"}):
                with patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text", return_value=rule_text):
                    response = _setup_client.get("/api/v1/sync/status", params={"rule_name": "test_rule"})

        assert response.status_code == 200
        assert response.json()["status"] == "unknown"


class TestGetRuleTextHelper:
    def test_get_rule_text_returns_503_without_database(self):
        from fastapi import HTTPException
        from src.adapters.inbound.http.routes import sync_imports

        with patch("src.adapters.inbound.http.dependencies.get_db_session", return_value=iter([None])):
            with pytest.raises(HTTPException) as exc:
                sync_imports._get_rule_text("rule")

        assert exc.value.status_code == 503

    def test_get_rule_text_translates_lookup_error_to_404(self):
        from fastapi import HTTPException
        from src.adapters.inbound.http.routes import sync_imports

        db = MagicMock()
        with patch("src.adapters.inbound.http.dependencies.get_db_session", return_value=iter([db])):
            with patch("src.services.rule_service.RuleService.get_rule_text", side_effect=LookupError):
                with pytest.raises(HTTPException) as exc:
                    sync_imports._get_rule_text("missing")

        assert exc.value.status_code == 404
        db.close.assert_called_once()


class TestRuleImports:
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_imports_modular_disabled(self, mock_flags_cls, mock_get_text, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = False
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: other_rule\nINPUT x AS NUMBER'
        response = _setup_client.get("/api/v1/rules/test_rule/imports")
        assert response.status_code == 200
        data = response.json()
        assert data["imports"] == []
        assert data["has_cycles"] is False
        assert data["total_count"] == 0

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_imports_with_resolved(self, mock_flags_cls, mock_get_text, mock_resolver_cls, _setup_client):
        from src.domain.imports.node_origin import NodeOrigin

        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: sub_rule\nINPUT x AS NUMBER'

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = {
            "test_rule": NodeOrigin(module="test_rule", imported=False, depth=0),
            "sub_rule": NodeOrigin(module="sub_rule", imported=True, depth=1),
        }
        mock_resolver_cls.return_value = mock_resolver

        response = _setup_client.get("/api/v1/rules/test_rule/imports")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["imports"][0]["name"] == "sub_rule"
        assert data["imports"][0]["depth"] == 1
        assert data["has_cycles"] is False

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_imports_circular_detected(self, mock_flags_cls, mock_get_text, mock_resolver_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: sub_rule\nINPUT x AS NUMBER'

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = CircularImportError(["A", "B", "C", "A"])
        mock_resolver_cls.return_value = mock_resolver

        response = _setup_client.get("/api/v1/rules/test_rule/imports")
        assert response.status_code == 200
        data = response.json()
        assert data["has_cycles"] is True

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_imports_depth_exceeded_returns_422(self, mock_flags_cls, mock_get_text, mock_resolver_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: sub_rule\nINPUT x AS NUMBER'

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = ImportDepthExceededError(101, "deep_rule")
        mock_resolver_cls.return_value = mock_resolver

        response = _setup_client.get("/api/v1/rules/test_rule/imports")
        assert response.status_code == 422

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_imports_pagination(self, mock_flags_cls, mock_get_text, mock_resolver_cls, _setup_client):
        from src.domain.imports.node_origin import NodeOrigin

        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: sub_rule\nINPUT x AS NUMBER'

        resolved = {
            "test_rule": NodeOrigin(module="test_rule", imported=False, depth=0),
        }
        for i in range(5):
            resolved[f"sub_{i}"] = NodeOrigin(module=f"sub_{i}", imported=True, depth=1)

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = resolved
        mock_resolver_cls.return_value = mock_resolver

        response = _setup_client.get("/api/v1/rules/test_rule/imports", params={"offset": 1, "limit": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 1
        assert data["limit"] == 2
        assert len(data["imports"]) == 2
        assert data["total_count"] == 5

    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    def test_imports_rule_not_found(self, mock_get_text, _setup_client):
        mock_get_text.side_effect = Exception("not found")
        with patch(
            "src.adapters.inbound.http.routes.sync_imports._get_rule_text",
            side_effect=__import__("fastapi").HTTPException(status_code=404, detail="Rule not found"),
        ):
            response = _setup_client.get("/api/v1/rules/nonexistent/imports")
            assert response.status_code == 404

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_imports_depth_filter(self, mock_flags_cls, mock_get_text, mock_resolver_cls, _setup_client):
        from src.domain.imports.node_origin import NodeOrigin

        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: sub_rule\nINPUT x AS NUMBER'

        resolved = {
            "test_rule": NodeOrigin(module="test_rule", imported=False, depth=0),
            "sub_a": NodeOrigin(module="sub_a", imported=True, depth=1),
            "sub_b": NodeOrigin(module="sub_b", imported=True, depth=2),
        }
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = resolved
        mock_resolver_cls.return_value = mock_resolver

        response = _setup_client.get("/api/v1/rules/test_rule/imports", params={"depth": 1})
        assert response.status_code == 200
        data = response.json()
        assert all(imp["depth"] <= 1 for imp in data["imports"])


class TestRuleValidateWithImports:
    @patch("src.adapters.inbound.http.routes.sync_imports.RuleValidationService")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_validate_valid_rule(self, mock_flags_cls, mock_get_text, mock_svc_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = False
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'INPUT x AS NUMBER\nx > 0\n'

        mock_result = MagicMock()
        mock_result.valid = True
        mock_result.errors = []
        mock_result.warnings = []
        mock_svc = MagicMock()
        mock_svc.validate.return_value = mock_result
        mock_svc_cls.return_value = mock_svc

        response = _setup_client.get("/api/v1/rules/test_rule/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleValidationService")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_validate_with_circular_import(self, mock_flags_cls, mock_get_text, mock_svc_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: sub_rule\nINPUT x AS NUMBER'

        mock_result = MagicMock()
        mock_result.valid = True
        mock_result.errors = []
        mock_result.warnings = []
        mock_svc = MagicMock()
        mock_svc.validate.return_value = mock_result
        mock_svc_cls.return_value = mock_svc

        with patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver") as mock_res_cls:
            mock_resolver = MagicMock()
            mock_resolver.resolve.side_effect = CircularImportError(["A", "B", "A"])
            mock_res_cls.return_value = mock_resolver

            response = _setup_client.get("/api/v1/rules/test_rule/validate")
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert any(e["code"] == "CIRCULAR_IMPORT" for e in data["errors"])

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleValidationService")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_validate_with_depth_exceeded(self, mock_flags_cls, mock_get_text, mock_svc_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = True
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'IMPORT: deep_rule\nINPUT x AS NUMBER'

        mock_result = MagicMock()
        mock_result.valid = True
        mock_result.errors = []
        mock_result.warnings = []
        mock_svc = MagicMock()
        mock_svc.validate.return_value = mock_result
        mock_svc_cls.return_value = mock_svc

        with patch("src.adapters.inbound.http.routes.sync_imports.RuleSetImportResolver") as mock_res_cls:
            mock_resolver = MagicMock()
            mock_resolver.resolve.side_effect = ImportDepthExceededError(101, "deep_rule")
            mock_res_cls.return_value = mock_resolver

            response = _setup_client.get("/api/v1/rules/test_rule/validate")
            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert any(e["code"] == "IMPORT_DEPTH_EXCEEDED" for e in data["errors"])

    @patch("src.adapters.inbound.http.routes.sync_imports.RuleValidationService")
    @patch("src.adapters.inbound.http.routes.sync_imports._get_rule_text")
    @patch("src.adapters.inbound.http.routes.sync_imports.FeatureFlags")
    def test_validate_syntax_errors_reported(self, mock_flags_cls, mock_get_text, mock_svc_cls, _setup_client):
        mock_flags = MagicMock()
        mock_flags.modular_imports = False
        mock_flags_cls.return_value = mock_flags
        mock_get_text.return_value = 'BAD SYNTAX'

        mock_err = MagicMock()
        mock_err.code = "SYNTAX_ERROR"
        mock_err.message = "Unexpected token"
        mock_err.line = 1
        mock_err.node_name = None

        mock_result = MagicMock()
        mock_result.valid = False
        mock_result.errors = [mock_err]
        mock_result.warnings = []
        mock_svc = MagicMock()
        mock_svc.validate.return_value = mock_result
        mock_svc_cls.return_value = mock_svc

        response = _setup_client.get("/api/v1/rules/test_rule/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) == 1
        assert data["errors"][0]["code"] == "SYNTAX_ERROR"
