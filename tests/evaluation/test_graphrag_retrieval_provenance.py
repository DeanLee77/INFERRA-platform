import copy
import json

from src.domain.fact_values import FactValue
from src.domain.state import FactSource, LayeredFactStore

from tests.evaluation.retrieval_provenance_harness import (
    EVALUATION_ONLY_AUTHORITY,
    evaluate_retrieval_cases,
    guard_retrieval_for_authoritative_state,
    load_golden_cases,
    load_source_manifest,
    missing_provenance_fields,
    run_retrieval_provenance_evaluation,
    try_apply_retrieval_to_authoritative_state,
)


def test_source_manifest_declares_fixture_corpus_and_non_authority_policy():
    manifest = load_source_manifest()
    source_ids = {source["sourceId"] for source in manifest["sources"]}

    assert manifest["manifestVersion"] == "graphrag-retrieval-source-manifest-0.1"
    assert manifest["snapshot"]["id"] == "inferra-reference-fixture-corpus-2026-05-31"
    assert manifest["authorityPolicy"]["mode"] == EVALUATION_ONLY_AUTHORITY
    assert "production answer authority" in manifest["authorityPolicy"]["forbiddenUses"]
    assert "live model context injection" in manifest["authorityPolicy"]["forbiddenUses"]
    assert {
        "reference.examples.drca.part_i.sections_1_to_13a",
        "reference.examples.drca.part_ii.sections_14_to_33",
        "reference.examples.mrca.chapter_11.sections_404_to_440",
        "active_docs.roadmap",
        "active_docs.implementation_status",
    } == source_ids
    assert {
        "source_id",
        "snapshot_version",
        "source_path",
        "extraction_path",
        "content_sha256",
        "retrieved_at",
        "rank",
        "score",
        "matched_terms",
        "authority",
    }.issubset(set(manifest["requiredProvenanceFields"]))


def test_retrieval_golden_cases_report_metrics_and_no_failures():
    report = run_retrieval_provenance_evaluation()
    minimums = load_golden_cases()["minimumMetrics"]

    assert report["authority"] == EVALUATION_ONLY_AUTHORITY
    assert report["authoritativeStateAllowed"] is False
    assert report["failures"] == {"missingProvenance": [], "staleSources": []}
    assert report["metrics"]["precision"] >= minimums["precision"]
    assert report["metrics"]["recall"] >= minimums["recall"]
    assert report["metrics"]["freshness"] >= minimums["freshness"]
    assert report["metrics"]["provenanceCoverage"] >= minimums["provenanceCoverage"]
    assert len(report["cases"]) == 5
    json.dumps(report)


def test_each_retrieval_result_carries_complete_provenance():
    manifest = load_source_manifest()
    report = run_retrieval_provenance_evaluation()

    for case in report["cases"]:
        assert case["retrievedSourceIds"] == case["expectedSourceIds"]
        assert case["precision"] == 1.0
        assert case["recall"] == 1.0
        assert case["freshness"] == 1.0
        assert case["provenanceCoverage"] == 1.0
        for result in case["results"]:
            assert missing_provenance_fields(result, manifest["requiredProvenanceFields"]) == []
            assert result["content_sha256"]
            assert len(result["content_sha256"]) == 64
            assert result["authority"] == EVALUATION_ONLY_AUTHORITY
            assert result["rank"] == 1
            assert result["score"] > 0
            assert result["matched_terms"]


def test_report_flags_missing_provenance_and_stale_source_snapshots():
    manifest = load_source_manifest()
    result = run_retrieval_provenance_evaluation()["cases"][0]["results"][0]
    unprovenanced = dict(result)
    del unprovenanced["content_sha256"]

    assert missing_provenance_fields(
        unprovenanced,
        manifest["requiredProvenanceFields"],
    ) == ["content_sha256"]

    stale_manifest = copy.deepcopy(manifest)
    stale_manifest["snapshot"]["capturedAt"] = "2025-01-01T00:00:00Z"
    stale_report = evaluate_retrieval_cases(stale_manifest, load_golden_cases())

    assert stale_report["metrics"]["freshness"] == 0.0
    assert stale_report["failures"]["staleSources"]
    assert {
        failure["sourceId"]
        for failure in stale_report["failures"]["staleSources"]
    }.issuperset(
        {
            "reference.examples.drca.part_i.sections_1_to_13a",
            "active_docs.roadmap",
        }
    )


def test_unprovenanced_retrieval_cannot_enter_authoritative_reasoning_state():
    manifest = load_source_manifest()
    store = LayeredFactStore()
    store.set_fact("authorization_outcome", FactValue("CERTIFY"), FactSource.INFERRED)
    unprovenanced_result = {
        "source_id": "untrusted.unmanifested.source",
        "authority": EVALUATION_ONLY_AUTHORITY,
        "matched_terms": ["authority"],
    }

    guard = guard_retrieval_for_authoritative_state(
        unprovenanced_result,
        manifest["requiredProvenanceFields"],
    )
    apply_result = try_apply_retrieval_to_authoritative_state(
        store,
        "authorization_outcome",
        unprovenanced_result,
        manifest["requiredProvenanceFields"],
    )

    assert guard["allowed"] is False
    assert apply_result["allowed"] is False
    assert apply_result["stateMutated"] is False
    assert {reason["code"] for reason in guard["reasons"]} == {
        "missing_provenance",
        "retrieval_is_evaluation_only",
    }
    assert store.peek_in_layer("authorization_outcome", FactSource.ASSERTED) is None
    assert store.peek_in_layer("authorization_outcome", FactSource.INFERRED).get_value() == "CERTIFY"
    assert store.get_fact_sources("authorization_outcome") == {FactSource.INFERRED}
