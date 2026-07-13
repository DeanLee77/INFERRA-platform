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
    _read_auth,
    _validate_graph_uri,
    _write_auth,
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


def test_read_auth_uses_distinct_read_credentials():
    with patch.dict(
        "os.environ",
        {
            "FUSEKI_USER": "admin",
            "FUSEKI_PASSWORD": "admin-password",
            "FUSEKI_READ_USER": "inferra_reader",
            "FUSEKI_READ_PASSWORD": "read-password",
        },
        clear=True,
    ):
        assert _read_auth() == ("inferra_reader", "read-password")
        assert _write_auth() == ("admin", "admin-password")


def test_read_auth_falls_back_to_write_credentials_for_legacy_envs():
    with patch.dict(
        "os.environ",
        {"FUSEKI_USER": "legacy-admin", "FUSEKI_PASSWORD": "legacy-password"},
        clear=True,
    ):
        assert _read_auth() == ("legacy-admin", "legacy-password")


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


class TestNamedGraphQueries:
    def test_rule_projection_graph_uri_is_stable_and_sanitized(self):
        assert (
            FusekiAdapter.rule_projection_graph_uri("Benefit Rule v1")
            == "http://inferra.ai/schema#projection/rule/Benefit_Rule_v1"
        )

    def test_list_named_graphs_parses_counts(self):
        with patch.object(FusekiAdapter, "_execute_sparql_select") as select:
            select.return_value = [
                {
                    "g": {"value": "http://inferra.ai/schema#version/hash"},
                    "count": {"value": "12"},
                }
            ]

            result = FusekiAdapter.list_named_graphs()

        assert result == [("http://inferra.ai/schema#version/hash", 12)]
        assert "GROUP BY ?g" in select.call_args.args[0]

    def test_get_named_graph_triples_uses_safe_graph_uri_and_paging(self):
        with patch.object(FusekiAdapter, "_execute_sparql_select") as select:
            select.return_value = [
                {
                    "s": {"value": "http://s"},
                    "p": {"value": "http://p"},
                    "o": {"value": "http://o"},
                }
            ]

            result = FusekiAdapter.get_named_graph_triples(
                "http://inferra.ai/schema#version/hash",
                offset=5,
                limit=10,
            )

        assert result == [("http://s", "http://p", "http://o")]
        sparql = select.call_args.args[0]
        assert "GRAPH <http://inferra.ai/schema#version/hash>" in sparql
        assert "OFFSET 5 LIMIT 10" in sparql

    def test_get_named_graph_triples_rejects_non_uri_graph_name(self):
        with pytest.raises(ValueError):
            FusekiAdapter.get_named_graph_triples("not a uri")

    def test_get_named_graph_all_triples_uses_unpaged_graph_query(self):
        with patch.object(FusekiAdapter, "_execute_sparql_select") as select:
            select.return_value = [
                {
                    "s": {"value": "http://s"},
                    "p": {"value": "http://p"},
                    "o": {"value": "literal"},
                }
            ]

            result = FusekiAdapter.get_named_graph_all_triples(
                "http://inferra.ai/schema#projection/rule/r1"
            )

        assert result == [("http://s", "http://p", "literal")]
        sparql = select.call_args.args[0]
        assert "GRAPH <http://inferra.ai/schema#projection/rule/r1>" in sparql
        assert "LIMIT" not in sparql

    def test_get_named_graph_triple_count_parses_count(self):
        with patch.object(FusekiAdapter, "_execute_sparql_select") as select:
            select.return_value = [{"count": {"value": "42"}}]

            result = FusekiAdapter.get_named_graph_triple_count(
                "http://inferra.ai/schema#projection/rule/r1"
            )

        assert result == 42
        assert "COUNT(*) AS ?count" in select.call_args.args[0]

    def test_validate_graph_uri_rejects_sparql_breakout_characters(self):
        with pytest.raises(ValueError):
            _validate_graph_uri("http://example.org/graph> } UNION { ?s ?p ?o")


class TestExecuteGuardedSelect:
    def test_uses_read_credentials_for_select_requests(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": {"bindings": []}}
        with patch.dict(
            "os.environ",
            {
                "FUSEKI_USER": "admin",
                "FUSEKI_PASSWORD": "admin-password",
                "FUSEKI_READ_USER": "inferra_reader",
                "FUSEKI_READ_PASSWORD": "read-password",
            },
            clear=True,
        ), patch(
            "src.adapters.outbound.ontology.fuseki_adapter._requests"
        ) as mock_req:
            with patch(
                "src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE",
                True,
            ):
                mock_req.post.return_value = mock_resp
                FusekiAdapter.execute_guarded_select(
                    "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"
                )

        assert mock_req.post.call_args.kwargs["auth"] == (
            "inferra_reader",
            "read-password",
        )

    def test_passes_timeout_and_retries_once(self):
        with patch.object(
            FusekiAdapter,
            "_execute_sparql_select",
            side_effect=[
                FusekiConnectionError("temporary"),
                [{"s": {"type": "uri", "value": "http://s"}}],
            ],
        ) as select:
            result = FusekiAdapter.execute_guarded_select(
                "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1",
                timeout_seconds=99,
                max_retries=1,
            )

        assert result == [{"s": {"type": "uri", "value": "http://s"}}]
        assert select.call_count == 2
        assert select.call_args.kwargs["timeout_seconds"] == 10

    def test_raises_last_error_after_bounded_attempts(self):
        with patch.object(
            FusekiAdapter,
            "_execute_sparql_select",
            side_effect=FusekiConnectionError("down"),
        ) as select:
            with pytest.raises(FusekiConnectionError):
                FusekiAdapter.execute_guarded_select(
                    "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1",
                    max_retries=1,
                )

        assert select.call_count == 2


class TestExecuteSparqlUpdate:
    def test_uses_write_credentials_for_update_requests(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.dict(
            "os.environ",
            {
                "FUSEKI_USER": "admin",
                "FUSEKI_PASSWORD": "admin-password",
                "FUSEKI_READ_USER": "inferra_reader",
                "FUSEKI_READ_PASSWORD": "read-password",
            },
            clear=True,
        ), patch(
            "src.adapters.outbound.ontology.fuseki_adapter._requests"
        ) as mock_req:
            with patch(
                "src.adapters.outbound.ontology.fuseki_adapter.REQUESTS_AVAILABLE",
                True,
            ):
                mock_req.post.return_value = mock_resp
                FusekiAdapter._execute_sparql_update("INSERT DATA { ?s ?p ?o }")

        assert mock_req.post.call_args.kwargs["auth"] == (
            "admin",
            "admin-password",
        )

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
