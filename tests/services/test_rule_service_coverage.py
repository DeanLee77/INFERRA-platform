from unittest.mock import MagicMock

import pytest

import src.services.rule_service as rule_service_module
from src.domain.exceptions import RuleValidationError
from src.domain.imports.import_resolver import (
    CircularImportError,
    ImportDepthExceededError,
    RuleLoadTimeoutError,
)
from src.domain.nodes.record import HistoryRecord
from src.services.rule_service import RuleService


@pytest.fixture
def service():
    return RuleService(MagicMock())


def test_graph_reads_reject_parsers_without_dependency_graphs(service, monkeypatch):
    latest_file = MagicMock()
    latest_file.decode_graph_json.return_value = None
    node_set = MagicMock()
    node_set.get_graph.return_value = None
    parser = MagicMock()
    parser.get_node_set.return_value = node_set

    monkeypatch.setattr(service, "get_latest_rule_file", MagicMock(return_value=latest_file))
    monkeypatch.setattr(service, "decode_rule_file", MagicMock(return_value="rule text"))
    monkeypatch.setattr(
        service,
        "_build_import_aware_rule_text",
        MagicMock(return_value="expanded rule text"),
    )
    monkeypatch.setattr(service, "_parse_rule_text", MagicMock(return_value=parser))

    with pytest.raises(ValueError, match="dependency graph"):
        service.get_rule_graph_data("stored-rule")

    with pytest.raises(ValueError, match="dependency graph"):
        service.get_rule_graph_data_for_text("draft-rule", "rule text")


def test_rule_ontology_artifact_rebuilds_triples_and_returns_response(service, monkeypatch):
    ontology = {
        "source_hash": "sha256:source",
        "graph_uri": "urn:graph:rule",
        "triples": [
            {"subject": "urn:rule", "predicate": "urn:name", "object": "Rule"},
        ],
    }
    artifact = MagicMock()
    artifact.response_dict.return_value = {"artifact_name": "rule_ontology.ttl"}
    builder = MagicMock(return_value=artifact)
    monkeypatch.setattr(service, "get_rule_ontology_data", MagicMock(return_value=ontology))
    monkeypatch.setattr(rule_service_module, "build_rule_set_ontology_artifact", builder)

    result = service.get_rule_ontology_artifact("Rule")

    assert result == {"artifact_name": "rule_ontology.ttl"}
    builder.assert_called_once_with(
        rule_name="Rule",
        triples=[("urn:rule", "urn:name", "Rule")],
        source_hash="sha256:source",
        graph_uri="urn:graph:rule",
        metadata=ontology,
    )


def test_collection_and_all_rule_syncs_forward_normalized_names(service, monkeypatch):
    get_text = MagicMock(return_value="IMPORT: child")
    collection_names = MagicMock(return_value=["root", "child"])
    sync_names = MagicMock(return_value={"status": "published"})
    monkeypatch.setattr(service, "get_rule_text", get_text)
    monkeypatch.setattr(service, "_rule_collection_names", collection_names)
    monkeypatch.setattr(service, "_sync_rule_names", sync_names)

    assert service.sync_rule_collection_ontology("root") == {"status": "published"}
    collection_names.assert_called_once_with("root", "IMPORT: child")
    sync_names.assert_called_once_with(["root", "child"])

    monkeypatch.setattr(
        service,
        "list_rules",
        MagicMock(
            return_value=[
                {"rule_name": "one"},
                {"name": "two"},
                {"rule_name": ""},
                {},
            ]
        ),
    )
    sync_names.reset_mock()

    assert service.sync_all_rule_ontologies() == {"status": "published"}
    sync_names.assert_called_once_with(["one", "two"])


def test_ontology_type_and_dependency_helpers_cover_fallback_mappings():
    assert RuleService._ontology_node_type_key(["urn:types#CustomNode"]) == "custom_node"
    assert RuleService._ontology_node_type_key([]) is None

    expected = {
        "notDependsOn": "NOT",
        "mandatoryDependsOn": "MANDATORY",
        "knownDependsOn": "KNOWN",
        "optionalDependsOn": "OPTIONALLY",
        "possibleDependsOn": "POSSIBLY",
    }
    assert {
        predicate: RuleService._ontology_dependency_type(predicate)
        for predicate in expected
    } == expected


def test_stored_projection_read_converts_fuseki_failure_to_status_data(monkeypatch):
    monkeypatch.setattr(
        rule_service_module.FusekiAdapter,
        "get_named_graph_triple_count",
        MagicMock(side_effect=RuntimeError("Fuseki unavailable")),
    )

    triples, count, error = RuleService._read_stored_projection("urn:graph:rule")

    assert triples == []
    assert count == 0
    assert error == "Fuseki unavailable"


def test_projection_status_reports_metadata_fuseki_and_staleness_failures():
    compiled = [("s", "p", "o")]
    base = {
        "compiled_triples": compiled,
        "stored_triples": compiled,
        "stored_triple_count": 1,
        "source_hash": "sha256:current",
        "dead_letters": [],
        "fuseki_error": None,
    }
    cases = [
        (
            {"metadata": {"sync_status": "failed", "source_hash": "sha256:current"}},
            ("failed", "failed"),
        ),
        (
            {"metadata": {"sync_status": "syncing", "source_hash": "sha256:current"}},
            ("syncing", None),
        ),
        (
            {"metadata": {}, "fuseki_error": "query failed\nwith detail"},
            ("failed", "fuseki_query_failed"),
        ),
        (
            {"metadata": {"source_hash": "sha256:other"}},
            ("stale", "source_hash_mismatch"),
        ),
        (
            {"metadata": {}},
            ("stale", "projection_metadata_missing"),
        ),
        (
            {
                "metadata": {
                    "source_hash": "sha256:current",
                    "compiler_version": "old-compiler",
                }
            },
            ("stale", "compiler_version_mismatch"),
        ),
    ]

    for overrides, expected in cases:
        result = RuleService._build_projection_status(**{**base, **overrides})
        assert (result["sync_status"], result["integrity_mismatch_reason"]) == expected


def test_rule_collection_names_handle_no_imports_and_deduplicate_resolved_modules(
    service,
    monkeypatch,
):
    assert service._rule_collection_names("root", "INPUT value AS NUMBER") == ["root"]

    monkeypatch.setattr(
        service,
        "_load_imported_rule_texts",
        MagicMock(
            return_value=[
                ("child", "child text"),
                ("root", "root text"),
                ("child", "child text"),
            ]
        ),
    )

    assert service._rule_collection_names("root", "IMPORT: child") == ["root", "child"]


def test_sync_rule_names_deduplicates_and_summarizes_partial_failures(service, monkeypatch):
    def sync_rule(name):
        if name == "broken":
            raise RuntimeError("request failed   remotely")
        return {"rule_name": name, "status": "published" if name == "published" else "skipped"}

    monkeypatch.setattr(service, "sync_rule_ontology", MagicMock(side_effect=sync_rule))

    result = service._sync_rule_names(
        ["", "published", "published", "skipped", "broken"]
    )

    assert result["status"] == "partial_failed"
    assert result["requested_count"] == 3
    assert result["published_count"] == 1
    assert result["skipped_count"] == 1
    assert result["failed_count"] == 1
    assert result["items"][-1]["last_error_summary"] == "request failed remotely"


def test_history_payload_normalization_handles_records_scalars_and_bad_counts(service):
    existing = HistoryRecord(name="existing", true_count=2, false_count=1)

    assert service._history_records_from_payload("invalid") == {}
    records = service._history_records_from_payload(
        {
            "existing": existing,
            "skip": "invalid",
            "converted": {"true": True, "false": object()},
        }
    )

    assert records == {
        "existing": existing,
        "converted": HistoryRecord(name="converted", true_count=1, false_count=0),
    }


def test_import_aware_text_returns_original_when_resolver_has_no_modules(service, monkeypatch):
    rule_text = "IMPORT: child\n\nroot conclusion"
    monkeypatch.setattr(service, "_load_imported_rule_texts", MagicMock(return_value=[]))

    assert service._build_import_aware_rule_text("root", rule_text) == rule_text


@pytest.mark.parametrize(
    ("resolver_error", "expected_code", "expected_node"),
    [
        (CircularImportError(["root", "child", "root"]), "CIRCULAR_IMPORT", "root"),
        (
            ImportDepthExceededError(101, "deep-module"),
            "IMPORT_DEPTH_EXCEEDED",
            "deep-module",
        ),
        (RuleLoadTimeoutError("slow-module", 1.0), "IMPORT_LOAD_TIMEOUT", "slow-module"),
    ],
)
def test_import_resolver_failures_become_structured_validation_errors(
    service,
    monkeypatch,
    resolver_error,
    expected_code,
    expected_node,
):
    resolver = MagicMock()
    resolver.resolve.side_effect = resolver_error
    monkeypatch.setattr(
        rule_service_module,
        "RuleSetImportResolver",
        MagicMock(return_value=resolver),
    )

    with pytest.raises(RuleValidationError) as caught:
        service._load_imported_rule_texts("root", "IMPORT: child")

    assert caught.value.rule_name == "root"
    assert caught.value.errors[0].code == expected_code
    assert caught.value.errors[0].node_name == expected_node


def test_get_node_names_filters_missing_and_blank_graph_labels(service, monkeypatch):
    monkeypatch.setattr(
        service,
        "get_rule_graph_data",
        MagicMock(
            return_value={
                "nodes": [
                    {"name": " first "},
                    {"name": ""},
                    {},
                    {"name": "second"},
                ]
            }
        ),
    )

    assert service.get_node_names("rule") == ["first", "second"]
