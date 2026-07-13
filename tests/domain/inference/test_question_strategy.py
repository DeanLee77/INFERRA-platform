from unittest.mock import MagicMock

from src.domain.fact_values import FactValue
from src.domain.inference.question_strategy import (
    AbductiveBridgeSuggestion,
    ConservativeQuestionStrategy,
    OntologyReachabilityQuestionStrategy,
    ReachabilityEvidence,
)
from src.domain.nodes.line_type import LineType


def _node(name="n1", variable="v1", line_type=LineType.VALUE_CONCLUSION):
    node = MagicMock()
    node.get_node_name.return_value = name
    node.get_variable_name.return_value = variable
    node.get_line_type.return_value = line_type
    return node


def test_should_ask_value_conclusion_leaf():
    strategy = ConservativeQuestionStrategy()

    assert strategy.should_ask(_node(), {}, has_children=False) is True


def test_should_not_ask_when_known():
    strategy = ConservativeQuestionStrategy()

    assert strategy.should_ask(_node(variable="known"), {"known": FactValue(True)}) is False


def test_select_next_returns_first_askable_candidate():
    strategy = ConservativeQuestionStrategy()
    known = _node(name="known_node", variable="known")
    unknown = _node(name="unknown_node", variable="unknown")

    result = strategy.select_next([known, unknown], {"known": FactValue(True)})

    assert result is unknown


def test_reachability_strategy_prioritizes_reachable_question_and_traces_skip():
    baseline = ConservativeQuestionStrategy()
    unreachable = _node(name="clinical_note_branch", variable="clinical_note_available")
    reachable = _node(
        name="face_to_face_branch",
        variable="face_to_face_exam_documented",
    )

    assert baseline.select_next([unreachable, reachable], {}) is unreachable

    guided = OntologyReachabilityQuestionStrategy(
        [
            ReachabilityEvidence(
                fact_name="clinical_note_available",
                reachable=False,
                reason="ontology path does not connect note evidence to DME request",
                ontology_snapshot_ref="synthetic-pa-ontology-v1",
                confidence=0.7,
            ),
            ReachabilityEvidence(
                fact_name="face_to_face_exam_documented",
                reachable=True,
                reason="DME request class has documentation evidence bridge",
                ontology_snapshot_ref="synthetic-pa-ontology-v1",
                confidence=0.8,
            ),
        ]
    )

    result = guided.select_next([unreachable, reachable], {})

    assert result is reachable
    trace = list(guided.get_trace())
    assert trace[0]["questionName"] == "clinical_note_available"
    assert trace[0]["action"] == "skipped"
    assert trace[0]["sourceLabel"] == "SEMANTIC"
    assert trace[0]["reversible"] is True
    assert trace[0]["fallbackAvailable"] is True
    assert trace[0]["performanceClaim"] == "experimental_unmeasured"
    assert trace[1]["questionName"] == "face_to_face_exam_documented"
    assert trace[1]["action"] == "selected"


def test_reachability_strategy_falls_back_when_ontology_evidence_is_stale():
    stale = _node(name="stale_branch", variable="stale_fact")
    next_candidate = _node(name="next_branch", variable="next_fact")
    strategy = OntologyReachabilityQuestionStrategy(
        [
            ReachabilityEvidence(
                fact_name="stale_fact",
                reachable=False,
                reason="old ontology said unreachable",
                ontology_snapshot_ref="synthetic-pa-ontology-old",
                stale=True,
            )
        ]
    )

    result = strategy.select_next([stale, next_candidate], {})

    assert result is stale
    trace = list(strategy.get_trace())
    assert trace[0]["action"] == "fallback"
    assert trace[0]["reason"] == "ontology_missing_or_stale"
    assert trace[0]["sourceLabel"] == "NONE"


def test_abductive_bridge_suggestion_is_labeled_hypothesis():
    strategy = OntologyReachabilityQuestionStrategy(
        {},
        bridge_suggestions=[
            AbductiveBridgeSuggestion(
                missing_fact_name="face_to_face_exam_documented",
                alternative_fact_name="clinician_order_signed",
                relationship_iri="http://inferra.ai/schema#supportsEvidenceFor",
                basis=(
                    "Ontology bridge suggests a signed clinician order as "
                    "alternative DME documentation evidence."
                ),
                confidence=0.42,
            )
        ],
    )

    suggestion = strategy.suggest_alternative_evidence(
        "face_to_face_exam_documented"
    )

    assert suggestion["candidateType"] == "hypothesis"
    assert suggestion["sourceLabel"] == "HYPOTHETICAL"
    assert suggestion["confirmationStatus"] == "hypothetical"
    assert suggestion["altersDeterministicOutcome"] is False
    assert suggestion["alternativeFactName"] == "clinician_order_signed"
    assert list(strategy.get_trace())[0]["action"] == "hypothesis_suggested"
