"""
Tests for the Prometheus Metrics Router.

Covers:
- /metrics endpoint returns Prometheus text format
- /api/v1/metrics delegates to /metrics
- Counter increments are reflected in output
- Gauge values from SemanticCache are populated
- Histogram observations are tracked
- All expected metric names are present
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from src.adapters.inbound.http.routes.metrics import (
    fuseki_sync_total,
    fuseki_sync_duration,
    propagation_total,
    propagation_duration,
    import_resolve_total,
    import_resolve_depth,
    semantic_cache_triples,
    semantic_cache_memory_mb,
    semantic_cache_hit_rate,
    abduction_total,
    abduction_hypothesis_count,
    induction_total,
    llm_call_total,
    llm_confidence_score,
    llm_response_length,
    reasoning_route_total,
    _refresh_semantic_cache_gauges,
)


def _reset_counters():
    for collector in list(REGISTRY._names_to_collectors.values()):
        if hasattr(collector, "_samples"):
            try:
                if hasattr(collector, "_value"):
                    collector._value.set(0)
                elif hasattr(collector, "_child_values"):
                    collector._child_values.clear()
            except Exception:
                pass


@pytest.fixture(autouse=True)
def _setup_client():
    from src.main import app

    client = TestClient(app)
    yield client


class TestMetricsEndpoint:
    def test_metrics_returns_text(self, _setup_client):
        response = _setup_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        body = response.text
        assert "inferra_fuseki_sync_total" in body
        assert "inferra_propagation_total" in body
        assert "inferra_import_resolve_total" in body
        assert "inferra_fuseki_sync_duration_seconds" in body
        assert "inferra_propagation_duration_seconds" in body
        assert "inferra_import_resolve_depth" in body
        assert "inferra_semantic_cache_triples_loaded" in body
        assert "inferra_semantic_cache_memory_mb" in body
        assert "inferra_semantic_cache_hit_rate" in body
        assert "inferra_abduction_total" in body
        assert "inferra_abduction_hypothesis_count" in body
        assert "inferra_induction_total" in body
        assert "inferra_reasoning_route_total" in body
        assert "inferra_llm_call_total" in body
        assert "inferra_llm_confidence_score" in body
        assert "inferra_llm_response_length_chars" in body

    def test_api_v1_metrics_delegates(self, _setup_client):
        response = _setup_client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert "inferra_fuseki_sync_total" in response.text

    def test_counter_increment_visible(self, _setup_client):
        fuseki_sync_total.labels(status="success").inc()
        response = _setup_client.get("/metrics")
        assert response.status_code == 200
        body = response.text
        assert 'inferra_fuseki_sync_total{status="success"}' in body

    def test_propagation_counter(self, _setup_client):
        propagation_total.labels(direction="forward").inc()
        response = _setup_client.get("/metrics")
        body = response.text
        assert 'inferra_propagation_total{direction="forward"}' in body

    def test_import_resolve_counter(self, _setup_client):
        import_resolve_total.labels(result="resolved").inc()
        response = _setup_client.get("/metrics")
        body = response.text
        assert 'inferra_import_resolve_total{result="resolved"}' in body

    def test_histogram_observation(self, _setup_client):
        fuseki_sync_duration.observe(0.5)
        response = _setup_client.get("/metrics")
        body = response.text
        assert "inferra_fuseki_sync_duration_seconds_count" in body
        assert "inferra_fuseki_sync_duration_seconds_sum" in body

    def test_propagation_duration_histogram(self, _setup_client):
        propagation_duration.labels(direction="backward").observe(1.2)
        response = _setup_client.get("/metrics")
        body = response.text
        assert "inferra_propagation_duration_seconds_count" in body

    def test_import_depth_histogram(self, _setup_client):
        import_resolve_depth.observe(3)
        response = _setup_client.get("/metrics")
        body = response.text
        assert "inferra_import_resolve_depth_count" in body

    def test_phase5_reasoning_metrics_visible(self, _setup_client):
        abduction_total.labels(status="success").inc()
        abduction_hypothesis_count.observe(2)
        induction_total.labels(operation="start", status="submitted").inc()
        reasoning_route_total.labels(mode="ABDUCTION", action="INJECT_HYPOTHESIS").inc()
        response = _setup_client.get("/metrics")
        body = response.text
        assert 'inferra_abduction_total{status="success"}' in body
        assert "inferra_abduction_hypothesis_count_count" in body
        assert 'inferra_induction_total{operation="start",status="submitted"}' in body
        assert 'inferra_reasoning_route_total{action="INJECT_HYPOTHESIS",mode="ABDUCTION"}' in body

    def test_phase4_llm_metrics_visible(self, _setup_client):
        llm_call_total.labels(operation="goal_mapping", status="fallback").inc()
        llm_confidence_score.observe(0.42)
        llm_response_length.observe(120)
        response = _setup_client.get("/metrics")
        body = response.text
        assert 'inferra_llm_call_total{operation="goal_mapping",status="fallback"}' in body
        assert "inferra_llm_confidence_score_count" in body
        assert "inferra_llm_response_length_chars_count" in body


class TestRefreshSemanticCacheGauges:
    @patch("src.adapters.outbound.ontology.semantic_cache.get_semantic_cache")
    def test_refresh_sets_gauge_values(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_cache.triple_count = 500
        mock_cache.memory_usage_mb = 8.5
        mock_cache.hit_rate = 0.75
        mock_get_cache.return_value = mock_cache
        _refresh_semantic_cache_gauges()
        assert semantic_cache_triples._value.get() == 500.0
        assert semantic_cache_memory_mb._value.get() == 8.5
        assert semantic_cache_hit_rate._value.get() == 0.75

    @patch(
        "src.adapters.outbound.ontology.semantic_cache.get_semantic_cache",
        side_effect=Exception("no cache"),
    )
    def test_refresh_on_exception_sets_zeroes(self, mock_get_cache):
        _refresh_semantic_cache_gauges()
        assert semantic_cache_triples._value.get() == 0.0
        assert semantic_cache_memory_mb._value.get() == 0.0
        assert semantic_cache_hit_rate._value.get() == 0.0


@pytest.mark.integration
class TestLiveMetricsEndpoint:
    def test_live_metrics_with_semantic_cache(self, _setup_client):
        response = _setup_client.get("/metrics")
        assert response.status_code == 200
        body = response.text
        assert "inferra_semantic_cache_triples_loaded" in body
