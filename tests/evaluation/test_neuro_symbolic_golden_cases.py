import json
from pathlib import Path

import pytest

from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.domain.demo.synthetic_decision_receipt import (
    build_decision_receipt,
    build_fixture_manifest,
)
from src.domain.fact_values import FactValue
from src.domain.reasoning import ReasoningRouter
from src.domain.reasoning.semantic_fact_enricher import (
    BoundFact,
    OntologyDiscoveredCandidate,
    RDF_TYPE,
    RDFS_RANGE,
    RDFS_SUBCLASS_OF,
    RDFS_SUBPROPERTY_OF,
    SemanticFactEnricher,
    SemanticHypothesis,
    SemanticReceiptContext,
)
from src.domain.state import FactSource, LayeredFactStore


INF = "http://inferra.ai/schema#"
SYN = "http://inferra.ai/synthetic#"
GOLDEN_CASES = json.loads(Path(__file__).with_name("golden_cases.json").read_text())
CASES_BY_ID = {case["id"]: case for case in GOLDEN_CASES["cases"]}


def _cases(category: str) -> list[dict]:
    return [case for case in GOLDEN_CASES["cases"] if case["category"] == category]


def test_harness_manifest_names_repeatable_command_and_case_categories():
    categories = {case["category"] for case in GOLDEN_CASES["cases"]}

    assert GOLDEN_CASES["harnessVersion"] == "neuro-symbolic-golden-cases-0.1"
    assert GOLDEN_CASES["command"] == (
        "python -m pytest tests/evaluation/test_neuro_symbolic_golden_cases.py"
    )
    assert {
        "symbolic_consistency",
        "retrieval_provenance",
        "abstention",
        "failure_reporting",
    }.issubset(categories)


@pytest.mark.parametrize("case", _cases("symbolic_consistency"), ids=lambda case: case["id"])
def test_symbolic_consistency_golden_cases_are_grounded_and_deterministic(case):
    manifest = build_fixture_manifest()

    receipt = build_decision_receipt(case["fixtureCaseId"])

    assert receipt["caseId"] == case["fixtureCaseId"]
    assert receipt["rule"]["version"] == manifest["ruleVersion"]
    assert receipt["outcome"]["code"] == case["expectedOutcome"]
    assert receipt["outcome"]["expectedForFixture"] == case["expectedOutcome"]
    assert receipt["outcome"]["confidence"] == "rule-determined"
    assert receipt["sourceLabels"]["fixture"] == manifest["sourceLabels"]["fixture"]
    assert receipt["sourceLabels"]["policy"] == "synthetic_policy_label:not_real_payer_policy"
    assert all(
        fact["sourceLabel"] == case["requiredInputFactSource"]
        for fact in receipt["inputFacts"]
    )
    assert {
        prompt["factKey"] for prompt in receipt["missingEvidencePrompts"]
    } == set(case["expectedMissingEvidence"])
    assert receipt["trace"]["sanitization"] == {
        "containsPhi": False,
        "containsCustomerData": False,
        "containsSecrets": False,
        "usesRealPayerPolicy": False,
        "usesProductionIntegration": False,
    }


def test_retrieval_provenance_case_keeps_ontology_tags_advisory():
    case = CASES_BY_ID["retrieval_provenance.semantic_ontology_tags"]
    store = LayeredFactStore()
    store.set_fact(
        case["assertedFact"]["name"],
        FactValue(case["assertedFact"]["value"]),
        FactSource.ASSERTED,
    )
    store.set_fact(
        case["inferredFact"]["name"],
        FactValue(case["inferredFact"]["value"]),
        FactSource.INFERRED,
    )

    result = SemanticFactEnricher().enrich(
        store,
        bindings=[
            BoundFact(
                fact_name=case["assertedFact"]["name"],
                subject_iri=f"{SYN}request/001",
                predicate_iri=f"{INF}requestedService",
                object_iri=f"{SYN}power_wheelchair_request",
            )
        ],
        ontology_triples=[
            (
                f"{SYN}power_wheelchair_request",
                RDF_TYPE,
                f"{INF}PowerWheelchairRequest",
            ),
            (
                f"{INF}PowerWheelchairRequest",
                RDFS_SUBCLASS_OF,
                f"{INF}DurableMedicalEquipmentRequest",
            ),
            (f"{INF}requestedService", RDFS_RANGE, f"{INF}PriorAuthServiceRequest"),
            (
                f"{INF}requestedService",
                RDFS_SUBPROPERTY_OF,
                f"{INF}requestedIntervention",
            ),
            (f"{INF}requestedIntervention", RDFS_RANGE, f"{INF}CareIntervention"),
        ],
        context=SemanticReceiptContext(
            receipt_id="golden-semantic-provenance-001",
            generated_at="2026-05-31T00:00:00Z",
            session_id="golden-session-001",
            rule_name="synthetic_prior_auth_v0",
            target_node_name=case["inferredFact"]["name"],
            outcome_code=case["inferredFact"]["value"],
        ),
        ontology_snapshot_ref=case["ontologySnapshotRef"],
        hypotheses=[
            SemanticHypothesis(
                fact_name="face_to_face_exam_documented",
                suggested_value=True,
                basis="DME ontology suggests documentation evidence for review.",
                confidence=0.4,
            )
        ],
        ontology_discovered_candidates=[
            OntologyDiscoveredCandidate(
                fact_name="face_to_face_exam_documented",
                suggested_value=True,
                basis="Derived from DME request class tags.",
                ontology_iri=f"{INF}DurableMedicalEquipmentRequest",
            )
        ],
    )

    receipt = result.receipt
    semantic_tag_fact = store.peek_in_layer(
        "requested_service__semantic_tags",
        FactSource.SEMANTIC,
    )
    event_kinds = {
        event["kind"]
        for event in receipt["trace"]["provO"]["value"]["provenanceEvents"]
    }

    assert store.get_unified_view()["requested_service"].get_value() == "power_wheelchair"
    assert "requested_service" not in store.get_overrides()
    assert semantic_tag_fact is not None
    assert receipt["trace"]["externalReasonerCalls"] is False
    assert receipt["replayInputs"]["ontologySnapshotRef"] == case["ontologySnapshotRef"]
    assert set(case["expectedEventKinds"]).issubset(event_kinds)
    assert receipt["semanticTags"]
    assert all(tag["sourceLabel"] == FactSource.SEMANTIC.value for tag in receipt["semanticTags"])
    assert all(
        tag["provenance"]["ontologySource"] == "in_memory_triples"
        and tag["provenance"]["subject"]
        and tag["provenance"]["predicate"]
        and tag["provenance"]["object"]
        for tag in receipt["semanticTags"]
    )
    assert receipt["ontologyDiscoveredCandidates"][0]["requiresRuleApproval"] is True
    assert receipt["ontologyDiscoveredCandidates"][0]["altersDeterministicOutcome"] is False


def test_abstention_case_reports_no_alternate_route_without_model_calls():
    case = CASES_BY_ID["abstention.no_alternate_route"]
    router = ReasoningRouter(
        NullAbductionAdapter(),
        induction=None,
        abduction_enabled=False,
        induction_pipeline=False,
    )

    decision = router.route(
        session_id="golden-abstain-001",
        target="authorization_outcome",
        working_memory={"supplier order complete": False},
        graph_snapshot={},
        iteration_count=3,
        has_unasked_questions=False,
        trace_backlog_size=0,
        rule_name="synthetic_prior_auth_v0",
    )

    assert {
        "mode": decision.mode,
        "action": decision.action,
        "reason": decision.reason,
    } == case["expectedDecision"]
    assert decision.hypotheses == []
    assert decision.induction_job_id is None


def test_failure_reporting_case_lists_known_fixture_ids():
    case = CASES_BY_ID["failure_reporting.unknown_fixture_case"]
    known_case_ids = {
        fixture["caseId"]
        for fixture in build_fixture_manifest()["cases"]
    }

    with pytest.raises(ValueError) as exc:
        build_decision_receipt(case["unknownCaseId"])

    message = str(exc.value)
    assert case["unknownCaseId"] in message
    assert "Expected one of:" in message
    assert known_case_ids
    assert all(case_id in message for case_id in known_case_ids)
