"""Focused branch coverage for the Fuseki ontology adapter."""

import builtins
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.outbound.ontology import fuseki_adapter as fuseki_module
from src.adapters.outbound.ontology.fuseki_adapter import (
    FusekiAdapter,
    FusekiConnectionError,
    _basic_auth,
)


def test_module_import_falls_back_when_requests_is_unavailable(monkeypatch) -> None:
    source_path = Path(fuseki_module.__file__)
    spec = importlib.util.spec_from_file_location(
        "_fuseki_adapter_without_requests",
        source_path,
    )
    assert spec is not None
    assert spec.loader is not None
    isolated_module = importlib.util.module_from_spec(spec)
    real_import = builtins.__import__

    def import_without_requests(name, *args, **kwargs):
        if name == "requests":
            raise ImportError("requests intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_requests)
    spec.loader.exec_module(isolated_module)

    assert isolated_module._requests is None
    assert isolated_module.REQUESTS_AVAILABLE is False


def test_named_graph_listing_skips_missing_graphs_and_defaults_bad_counts() -> None:
    with patch.object(
        FusekiAdapter,
        "_execute_sparql_select",
        return_value=[
            {"count": {"value": "12"}},
            {"g": {"value": "urn:graph:invalid-count"}, "count": {"value": "bad"}},
        ],
    ):
        graphs = FusekiAdapter.list_named_graphs()

    assert graphs == [("urn:graph:invalid-count", 0)]


def test_named_graph_count_defaults_for_empty_and_invalid_results() -> None:
    with patch.object(
        FusekiAdapter,
        "_execute_sparql_select",
        side_effect=[[], [{"count": {"value": None}}]],
    ):
        assert FusekiAdapter.get_named_graph_triple_count("urn:graph:empty") == 0
        assert FusekiAdapter.get_named_graph_triple_count("urn:graph:invalid") == 0


def test_delta_query_placeholder_returns_no_changes() -> None:
    assert FusekiAdapter.query_deltas(123.0) == []


def test_select_skips_transport_when_requests_is_unavailable() -> None:
    with patch.object(fuseki_module, "REQUESTS_AVAILABLE", False):
        assert FusekiAdapter._execute_sparql_select("SELECT * WHERE { ?s ?p ?o }") == []


def test_select_translates_transport_and_status_failures() -> None:
    with patch.object(fuseki_module, "REQUESTS_AVAILABLE", True), patch.object(
        fuseki_module._requests,
        "post",
        side_effect=OSError("network unavailable"),
    ):
        with pytest.raises(FusekiConnectionError, match="network unavailable"):
            FusekiAdapter._execute_sparql_select("SELECT * WHERE { ?s ?p ?o }")

    response = MagicMock(status_code=503)
    with patch.object(fuseki_module, "REQUESTS_AVAILABLE", True), patch.object(
        fuseki_module._requests,
        "post",
        return_value=response,
    ):
        with pytest.raises(FusekiConnectionError, match="status=503"):
            FusekiAdapter._execute_sparql_select("SELECT * WHERE { ?s ?p ?o }")


def test_basic_auth_is_disabled_without_a_username() -> None:
    assert _basic_auth("", "secret") is None
