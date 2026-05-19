"""
Tests for the System API Router — extended /health endpoint.

Covers:
- Celery availability check
- Fuseki availability check
- Redis availability check
- SemanticCache stats collection
- Overall status logic (ok / degraded / unhealthy)
- Component-level status values
- Helper functions in isolation
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.inbound.http.routes.system import (
    _check_celery,
    _check_fuseki,
    _check_redis,
    _check_z3_solver,
    _get_active_session_count,
    _get_induction_worker_status,
    _get_semantic_cache_stats,
)


class TestCheckRedis:
    def test_redis_ok(self):
        mock_redis = MagicMock()
        mock_instance = MagicMock()
        mock_redis.Redis.from_url.return_value = mock_instance
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict(sys.modules, {"redis": mock_redis}):
                assert _check_redis() == "ok"
                mock_redis.Redis.from_url.assert_called_once_with("redis://localhost:6379/0")
                mock_instance.ping.assert_called_once()

    def test_redis_uses_configured_url(self):
        mock_redis = MagicMock()
        mock_instance = MagicMock()
        mock_redis.Redis.from_url.return_value = mock_instance
        with patch.dict("os.environ", {"REDIS_URL": "redis://redis:6379/0"}, clear=True):
            with patch.dict(sys.modules, {"redis": mock_redis}):
                assert _check_redis() == "ok"
                mock_redis.Redis.from_url.assert_called_once_with("redis://redis:6379/0")
                mock_instance.ping.assert_called_once()

    def test_redis_import_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict(sys.modules, {"redis": None}):
                assert _check_redis() == "unavailable"

    def test_redis_connection_error(self):
        mock_redis = MagicMock()
        mock_instance = MagicMock()
        mock_instance.ping.side_effect = Exception("Connection refused")
        mock_redis.Redis.from_url.return_value = mock_instance
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict(sys.modules, {"redis": mock_redis}):
                assert _check_redis() == "unavailable"


class TestCheckCelery:
    @patch("src.tasks.celery_app.app")
    def test_celery_ok(self, mock_app):
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = {"worker1": "pong"}
        mock_app.control.inspect.return_value = mock_inspect
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", True):
            assert _check_celery() == "ok"

    @patch("src.tasks.celery_app.app")
    def test_celery_no_workers(self, mock_app):
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = None
        mock_app.control.inspect.return_value = mock_inspect
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", True):
            assert _check_celery() == "unavailable"

    def test_celery_not_configured(self):
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", False):
            assert _check_celery() == "not_configured"

    @patch("src.tasks.celery_app.app")
    def test_celery_inspect_exception(self, mock_app):
        mock_app.control.inspect.side_effect = Exception("timeout")
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", True):
            assert _check_celery() == "unavailable"


class TestCheckFuseki:
    @patch(
        "src.adapters.outbound.ontology.fuseki_adapter.FusekiAdapter.health_check"
    )
    def test_fuseki_ok(self, mock_health_check):
        mock_health_check.return_value = True
        assert _check_fuseki() == "ok"

    @patch(
        "src.adapters.outbound.ontology.fuseki_adapter.FusekiAdapter.health_check",
        side_effect=ImportError,
    )
    def test_fuseki_import_error(self, mock_health_check):
        assert _check_fuseki() == "not_configured"

    @patch(
        "src.adapters.outbound.ontology.fuseki_adapter.FusekiAdapter.health_check",
        side_effect=Exception("Connection refused"),
    )
    def test_fuseki_unavailable(self, mock_health_check):
        assert _check_fuseki() == "unavailable"


class TestGetSemanticCacheStats:
    @patch("src.adapters.outbound.ontology.semantic_cache.get_semantic_cache")
    def test_cache_with_data(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_cache.triple_count = 1500
        mock_cache.memory_usage_mb = 12.345
        mock_cache.hit_rate = 0.857
        mock_get_cache.return_value = mock_cache
        result = _get_semantic_cache_stats()
        assert result["triples"] == 1500
        assert result["memory_mb"] == 12.3
        assert result["hit_rate"] == 0.86

    @patch("src.adapters.outbound.ontology.semantic_cache.get_semantic_cache")
    def test_cache_empty(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_cache.triple_count = 0
        mock_cache.memory_usage_mb = 0.0
        mock_cache.hit_rate = 0.0
        mock_get_cache.return_value = mock_cache
        result = _get_semantic_cache_stats()
        assert result["triples"] == 0
        assert result["memory_mb"] == 0.0
        assert result["hit_rate"] == 0.0

    @patch(
        "src.adapters.outbound.ontology.semantic_cache.get_semantic_cache",
        side_effect=Exception("init failed"),
    )
    def test_cache_exception(self, mock_get_cache):
        result = _get_semantic_cache_stats()
        assert result == {"triples": 0, "memory_mb": 0.0, "hit_rate": 0.0}


class TestPhase5HealthHelpers:
    def test_z3_solver_helper_reports_ok_when_available(self):
        mock_z3 = MagicMock()
        mock_solver = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        with patch.dict(sys.modules, {"z3": mock_z3}):
            assert _check_z3_solver() == "ok"
            mock_solver.set.assert_called_once_with("timeout", 500)
            mock_solver.check.assert_called_once()

    def test_z3_solver_helper_reports_unavailable_when_missing(self):
        with patch.dict(sys.modules, {"z3": None}):
            assert _check_z3_solver() == "unavailable"

    def test_z3_solver_helper_reports_unavailable_when_solver_fails(self):
        mock_z3 = MagicMock()
        mock_solver = MagicMock()
        mock_solver.check.side_effect = Exception("solver failed")
        mock_z3.Solver.return_value = mock_solver
        with patch.dict(sys.modules, {"z3": mock_z3}):
            assert _check_z3_solver() == "unavailable"

    @patch("src.tasks.celery_app.app")
    def test_induction_worker_status_counts_active_and_reserved(self, mock_app):
        mock_inspect = MagicMock()
        mock_inspect.active.return_value = {"w1": [1, 2], "w2": [3]}
        mock_inspect.reserved.return_value = {"w1": [4]}
        mock_app.control.inspect.return_value = mock_inspect
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", True):
            result = _get_induction_worker_status()
        assert result == {"status": "ok", "active": 3, "pending_jobs": 1}

    def test_induction_worker_status_not_configured(self):
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", False):
            assert _get_induction_worker_status() == {
                "status": "not_configured",
                "active": 0,
                "pending_jobs": 0,
            }

    @patch("src.tasks.celery_app.app")
    def test_induction_worker_status_unavailable_on_exception(self, mock_app):
        mock_app.control.inspect.side_effect = Exception("broker down")
        with patch("src.tasks.celery_app.CELERY_AVAILABLE", True):
            assert _get_induction_worker_status() == {
                "status": "unavailable",
                "active": 0,
                "pending_jobs": 0,
            }

    @patch("src.adapters.inbound.http.dependencies.get_session_store")
    def test_active_session_count_uses_store_count_when_available(self, mock_store_factory):
        store = MagicMock()
        store.count.return_value = 7
        mock_store_factory.return_value = store
        assert _get_active_session_count() == 7

    @patch("src.adapters.inbound.http.dependencies.get_session_store")
    def test_active_session_count_falls_back_to_list_sessions(self, mock_store_factory):
        store = MagicMock()
        del store.count
        store.list_sessions.return_value = ["s1", "s2"]
        mock_store_factory.return_value = store
        assert _get_active_session_count() == 2

    @patch("src.adapters.inbound.http.dependencies.get_session_store", side_effect=Exception("store down"))
    def test_active_session_count_returns_zero_on_exception(self, mock_store_factory):
        assert _get_active_session_count() == 0


class TestHealthEndpointIntegration:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from fastapi.testclient import TestClient
        from src.main import app
        from src.adapters.inbound.http.dependencies import get_db_session

        app.dependency_overrides[get_db_session] = lambda: None
        self.client = TestClient(app)
        yield
        app.dependency_overrides.clear()

    @patch("src.adapters.inbound.http.routes.system._check_redis", return_value="ok")
    @patch("src.adapters.inbound.http.routes.system._check_celery", return_value="ok")
    @patch("src.adapters.inbound.http.routes.system._check_fuseki", return_value="ok")
    @patch(
        "src.adapters.inbound.http.routes.system._get_semantic_cache_stats",
        return_value={"triples": 100, "memory_mb": 1.0, "hit_rate": 0.5},
    )
    def test_health_all_ok(self, mock_cache, mock_fuseki, mock_celery, mock_redis):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")
        assert data["version"] == "2.0.0"
        assert "celery" in data["components"]
        assert "fuseki" in data["components"]
        assert "semantic_cache" in data["components"]
        assert "z3_solver" in data["components"]
        assert "induction_workers" in data["components"]
        assert "active_sessions" in data["components"]
        assert data["components"]["celery"] == "ok"
        assert data["components"]["fuseki"] == "ok"
        assert data["components"]["semantic_cache"]["triples"] == 100

    @patch("src.adapters.inbound.http.routes.system._check_redis", return_value="ok")
    @patch(
        "src.adapters.inbound.http.routes.system._check_celery",
        return_value="unavailable",
    )
    @patch(
        "src.adapters.inbound.http.routes.system._check_fuseki",
        return_value="unavailable",
    )
    @patch(
        "src.adapters.inbound.http.routes.system._get_semantic_cache_stats",
        return_value={"triples": 0, "memory_mb": 0.0, "hit_rate": 0.0},
    )
    def test_health_degraded_when_optional_unavailable(
        self, mock_cache, mock_fuseki, mock_celery, mock_redis
    ):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")

    @patch(
        "src.adapters.inbound.http.routes.system._check_redis",
        return_value="unavailable",
    )
    @patch("src.adapters.inbound.http.routes.system._check_celery", return_value="ok")
    @patch("src.adapters.inbound.http.routes.system._check_fuseki", return_value="ok")
    @patch(
        "src.adapters.inbound.http.routes.system._get_semantic_cache_stats",
        return_value={"triples": 0, "memory_mb": 0.0, "hit_rate": 0.0},
    )
    def test_health_degraded_when_redis_unavailable(
        self, mock_cache, mock_fuseki, mock_celery, mock_redis
    ):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("degraded", "unhealthy")

    @patch(
        "src.adapters.inbound.http.routes.system._check_redis",
        return_value="not_configured",
    )
    @patch(
        "src.adapters.inbound.http.routes.system._check_celery",
        return_value="not_configured",
    )
    @patch(
        "src.adapters.inbound.http.routes.system._check_fuseki",
        return_value="not_configured",
    )
    @patch(
        "src.adapters.inbound.http.routes.system._get_semantic_cache_stats",
        return_value={"triples": 0, "memory_mb": 0.0, "hit_rate": 0.0},
    )
    def test_health_not_configured_components(
        self, mock_cache, mock_fuseki, mock_celery, mock_redis
    ):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["components"]["celery"] == "not_configured"
        assert data["components"]["fuseki"] == "not_configured"

    @patch("src.adapters.inbound.http.routes.system._check_redis", return_value="ok")
    @patch("src.adapters.inbound.http.routes.system._check_celery", return_value="ok")
    @patch("src.adapters.inbound.http.routes.system._check_fuseki", return_value="ok")
    @patch(
        "src.adapters.inbound.http.routes.system._get_semantic_cache_stats",
        return_value={"triples": 100, "memory_mb": 1.0, "hit_rate": 0.5},
    )
    def test_api_v1_health_delegates(
        self, mock_cache, mock_fuseki, mock_celery, mock_redis
    ):
        response = self.client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "components" in data
        assert data["components"]["celery"] == "ok"

    def test_live_endpoint_is_shallow_and_versioned(self):
        response = self.client.get("/api/v1/live")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok", "version": "2.0.0"}

    def test_root_endpoint_returns_service_metadata(self):
        response = self.client.get("/")
        assert response.status_code == 200
        assert response.json()["service"] == "INFERRA Platform"


@pytest.mark.integration
class TestLiveRedisConnection:
    def test_redis_ping_live(self):
        assert _check_redis() == "ok"

    def test_redis_connection_refused(self):
        with patch("redis.Redis.from_url") as mock_factory:
            mock_factory.return_value.ping.side_effect = Exception("Connection refused")
            assert _check_redis() == "unavailable"


@pytest.mark.integration
class TestLiveFusekiConnection:
    def test_fuseki_health_check_live(self):
        assert _check_fuseki() == "ok"

    def test_fuseki_unreachable(self):
        original = __import__(
            "src.adapters.outbound.ontology.fuseki_adapter",
            fromlist=["FusekiAdapter"],
        ).FusekiAdapter.health_check
        with patch(
            "src.adapters.outbound.ontology.fuseki_adapter.FusekiAdapter.health_check",
            side_effect=Exception("Connection refused"),
        ):
            assert _check_fuseki() == "unavailable"


@pytest.mark.integration
class TestLiveHealthEndpoint:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from fastapi.testclient import TestClient
        from src.main import app
        from src.adapters.inbound.http.dependencies import get_db_session

        app.dependency_overrides[get_db_session] = lambda: None
        self.client = TestClient(app)
        yield
        app.dependency_overrides.clear()

    def test_health_with_live_redis_and_fuseki(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["components"]["redis"] == "ok"
        assert data["components"]["fuseki"] == "ok"
        assert "semantic_cache" in data["components"]
        assert isinstance(data["components"]["semantic_cache"], dict)
        assert "triples" in data["components"]["semantic_cache"]
