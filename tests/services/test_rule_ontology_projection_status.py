from src.adapters.outbound.ontology.inferra_to_rdf_compiler import COMPILER_VERSION
from src.services.rule_service import RuleService


def test_projection_status_current_requires_matching_metadata_count_and_content():
    triples = [("http://s", "http://p", "literal")]
    status = RuleService._build_projection_status(
        compiled_triples=triples,
        stored_triples=list(triples),
        stored_triple_count=1,
        source_hash="hash1",
        metadata={
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
            "sync_timestamp": "2026-06-02T00:00:00Z",
        },
        dead_letters=[],
        fuseki_error=None,
    )

    assert status["sync_status"] == "current"
    assert status["integrity_status"] == "pass"
    assert status["integrity_mismatch_reason"] is None


def test_projection_status_uses_unique_compiled_triples_for_rdf_graph_integrity():
    triples = [
        ("http://s", "http://p", "literal"),
        ("http://s", "http://p", "literal"),
    ]
    status = RuleService._build_projection_status(
        compiled_triples=triples,
        stored_triples=[("http://s", "http://p", "literal")],
        stored_triple_count=1,
        source_hash="hash1",
        metadata={
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
        },
        dead_letters=[],
        fuseki_error=None,
    )

    assert status["sync_status"] == "current"
    assert status["integrity_status"] == "pass"


def test_projection_status_missing_when_stored_graph_has_no_triples():
    status = RuleService._build_projection_status(
        compiled_triples=[("http://s", "http://p", "literal")],
        stored_triples=[],
        stored_triple_count=0,
        source_hash="hash1",
        metadata={
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
        },
        dead_letters=[],
        fuseki_error=None,
    )

    assert status["sync_status"] == "missing"
    assert status["integrity_mismatch_reason"] == "stored_graph_missing"


def test_projection_status_stale_when_stored_count_differs():
    status = RuleService._build_projection_status(
        compiled_triples=[("http://s", "http://p", "literal")],
        stored_triples=[("http://s", "http://p", "literal")],
        stored_triple_count=2,
        source_hash="hash1",
        metadata={
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
        },
        dead_letters=[],
        fuseki_error=None,
    )

    assert status["sync_status"] == "stale"
    assert status["integrity_mismatch_reason"] == "triple_count_mismatch"


def test_projection_status_stale_when_stored_content_differs():
    status = RuleService._build_projection_status(
        compiled_triples=[("http://s", "http://p", "literal")],
        stored_triples=[("http://s", "http://p", "different")],
        stored_triple_count=1,
        source_hash="hash1",
        metadata={
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
        },
        dead_letters=[],
        fuseki_error=None,
    )

    assert status["sync_status"] == "stale"
    assert status["integrity_status"] == "fail"
    assert status["integrity_mismatch_reason"] == "triple_content_mismatch"


def test_projection_status_dead_lettered_is_visible_and_failed():
    status = RuleService._build_projection_status(
        compiled_triples=[("http://s", "http://p", "literal")],
        stored_triples=[],
        stored_triple_count=0,
        source_hash="hash1",
        metadata={},
        dead_letters=[
            {
                "dead_letter_id": "dlq-1",
                "last_error_code": "FUSEKI_SYNC_FAILED",
                "last_error_summary": "Fuseki unavailable",
            }
        ],
        fuseki_error=None,
    )

    assert status["sync_status"] == "dead_lettered"
    assert status["dead_letter_visible"] is True
    assert status["dead_letter_id"] == "dlq-1"
    assert status["last_error_code"] == "FUSEKI_SYNC_FAILED"
