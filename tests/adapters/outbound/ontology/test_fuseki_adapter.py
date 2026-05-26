"""
Tests for FusekiAdapter.

Tests are designed to run without a live Fuseki instance — they verify
SPARQL generation and error handling using mocks.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.adapters.outbound.ontology.fuseki_adapter import (
    FusekiAdapter,
    FusekiConnectionError,
    _auth,
    _format_object,
)


class TestExecuteSparqlIdempotentInsert:
    def test_empty_triples_is_noop(self):
        result = FusekiAdapter.execute_sparql_idempotent_insert([], "hash123")
        assert result is None

    def test_generates_delete_insert_sparql(self):
        triples = [
            ("http://inferra.ai/schema#rule/test", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://inferra.ai/schema#Rule"),
        ]
        with patch.object(FusekiAdapter, "_execute_sparql_update") as mock_exec:
            FusekiAdapter.execute_sparql_idempotent_insert(triples, "hash123")
            mock_exec.assert_called_once()
            sparql = mock_exec.call_args[0][0]
            assert "DELETE WHERE" in sparql
            assert "INSERT DATA" in sparql
            assert "hash123" in sparql

    def test_uses_named_graph_from_version(self):
        triples = [("http://s", "http://p", "http://o")]
        with patch.object(FusekiAdapter, "_execute_sparql_update") as mock_exec:
            FusekiAdapter.execute_sparql_idempotent_insert(triples, "abc123")
            sparql = mock_exec.call_args[0][0]
            assert "abc123" in sparql

    def test_uses_custom_graph_uri(self):
        triples = [("http://s", "http://p", "http://o")]
        with patch.object(FusekiAdapter, "_execute_sparql_update") as mock_exec:
            FusekiAdapter.execute_sparql_idempotent_insert(
                triples, "hash", graph_uri="http://example.org/graph"
            )
            sparql = mock_exec.call_args[0][0]
            assert "http://example.org/graph" in sparql

    def test_formats_literal_objects(self):
        triples = [("http://s", "http://p", "hello world")]
        with patch.object(FusekiAdapter, "_execute_sparql_update") as mock_exec:
            FusekiAdapter.execute_sparql_idempotent_insert(triples, "literal")
            sparql = mock_exec.call_args[0][0]
            assert '"hello world"' in sparql


def test_format_object_uri_vs_literal():
    assert _format_object("http://example.com/x") == "<http://example.com/x>"
    assert _format_object('hello "world"') == '"hello \\"world\\""'


def test_auth_defaults_to_local_fuseki_admin():
    assert _auth() == ("admin", "admin")


class TestHealthCheck:
    def test_returns_true_when_healthy(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.get.return_value = mock_resp
                assert FusekiAdapter.health_check() is True

    def test_raises_when_unreachable(self):
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.get.side_effect = Exception("Connection refused")
                with pytest.raises(FusekiConnectionError):
                    FusekiAdapter.health_check()

    def test_raises_on_bad_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.get.return_value = mock_resp
                with pytest.raises(FusekiConnectionError):
                    FusekiAdapter.health_check()

    def test_returns_true_when_requests_unavailable(self):
        with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", False):
            assert FusekiAdapter.health_check() is True


class TestGetRuleTriples:
    def test_returns_empty_when_requests_unavailable(self):
        with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", False):
            result = FusekiAdapter.get_rule_triples("test_rule")
            assert result == []

    def test_parses_sparql_results(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": {
                "bindings": [
                    {
                        "s": {"value": "http://inferra.ai/schema#rule/test"},
                        "p": {"value": "http://inferra.ai/schema#name"},
                        "o": {"value": "test"},
                    }
                ]
            }
        }
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.post.return_value = mock_resp
                result = FusekiAdapter.get_rule_triples("test_rule")
                assert len(result) == 1
                assert result[0][0] == "http://inferra.ai/schema#rule/test"

    def test_returns_empty_on_bad_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.post.return_value = mock_resp
                result = FusekiAdapter.get_rule_triples("test_rule")
                assert result == []

    def test_returns_empty_on_exception(self):
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.post.side_effect = Exception("Connection refused")
                result = FusekiAdapter.get_rule_triples("test_rule")
                assert result == []


class TestExecuteSparqlUpdate:
    def test_raises_connection_error_on_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.post.return_value = mock_resp
                with pytest.raises(FusekiConnectionError):
                    FusekiAdapter._execute_sparql_update("INSERT DATA { ?s ?p ?o }")

    def test_succeeds_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.post.return_value = mock_resp
                FusekiAdapter._execute_sparql_update("INSERT DATA { ?s ?p ?o }")

    def test_succeeds_on_204(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch("src.adapters.outbound.ontology.fuseki_adapter._requests") as mock_req:
            with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", True):
                mock_req.post.return_value = mock_resp
                FusekiAdapter._execute_sparql_update("INSERT DATA { ?s ?p ?o }")

    def test_skips_when_requests_unavailable(self):
        with patch("src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE", False):
            FusekiAdapter._execute_sparql_update("INSERT DATA { ?s ?p ?o }")


@pytest.mark.integration
def test_live_idempotent_insert_and_query_round_trip():
    try:
        FusekiAdapter.health_check()
    except Exception as exc:
        pytest.skip(f"Fuseki is not available: {exc}")

    triples = [
        (
            "http://inferra.ai/schema#rule/live_round_trip",
            "http://inferra.ai/schema#name",
            "live_round_trip",
        ),
        (
            "http://inferra.ai/schema#rule/live_round_trip",
            "http://inferra.ai/schema#sourceText",
            "A IS TRUE IF B",
        ),
    ]

    FusekiAdapter.execute_sparql_idempotent_insert(
        triples,
        "live-round-trip",
        graph_uri="http://inferra.ai/schema#test/live-round-trip",
    )
    result = FusekiAdapter.get_rule_triples("live_round_trip")

    assert any(predicate.endswith("#name") and obj == "live_round_trip" for _, predicate, obj in result)
