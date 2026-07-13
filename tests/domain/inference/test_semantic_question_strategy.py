from unittest.mock import MagicMock

from src.domain.fact_values import FactValue
from src.domain.inference.semantic_question_strategy import SemanticQuestionStrategy
from src.domain.nodes.line_type import LineType
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.reasoning.semantic_fact_enricher import (
    INF_CONFIDENCE,
    INF_NAME,
    RDF_TYPE,
    RDFS_SUBCLASS_OF,
    OntologyIndex,
)
from src.domain.state import FactSource, LayeredFactStore


INF = "http://inferra.ai/schema#"
SYN = "http://inferra.ai/synthetic#"


def _node(name: str, variable: str | None = None):
    node = MagicMock()
    node.get_node_name.return_value = name
    node.get_variable_name.return_value = variable or name
    node.get_line_type.return_value = LineType.VALUE_CONCLUSION
    return node


def _reasoner(snapshot_hash: str | None = "hash", threshold: float = 0.85):
    return OntologyReasoner(
        source_graph_uri="urn:semantic-question-test",
        ontology_snapshot_ref="synthetic-rule:hash",
        ontology_snapshot_hash=snapshot_hash,
        confidence_threshold=threshold,
    )


def _evidence_index(extra_triples=()):
    return OntologyIndex(
        [
            (f"{SYN}order", INF_NAME, "medical order signed"),
            (f"{SYN}order", RDF_TYPE, f"{INF}DmeEvidence"),
            (f"{INF}DmeEvidence", RDFS_SUBCLASS_OF, f"{INF}EligibleEvidence"),
            (f"{INF}EligibleEvidence", INF_NAME, "benefit evidence available"),
            (f"{INF}EligibleEvidence", INF_CONFIDENCE, "0.95"),
            *extra_triples,
        ]
    )


def test_select_next_prioritizes_missing_prerequisite_and_traces_prune():
    target = _node("benefit evidence available")
    prerequisite = _node("medical order signed")
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(),
        ontology_index=_evidence_index(),
        fact_store=LayeredFactStore(),
    )

    selected = strategy.select_next([target, prerequisite], {})

    assert selected is prerequisite
    trace = list(strategy.get_trace())
    assert trace[0]["questionName"] == "benefit evidence available"
    assert trace[0]["action"] == "pruned"
    assert trace[0]["reason"] == "missing_prerequisite_selected_first"
    assert trace[0]["missingPrerequisites"] == ["medical order signed"]
    assert trace[0]["expectedInformationGain"] == 0
    assert trace[1]["questionName"] == "medical order signed"
    assert trace[1]["action"] == "selected"
    assert trace[1]["expectedInformationGain"] == 1
    assert trace[1]["userControlRequired"] is True


def test_tie_breaking_is_deterministic_for_identical_scores():
    first = _node("medical order signed")
    second = _node("medical order signed")
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(),
        ontology_index=_evidence_index(),
        fact_store=LayeredFactStore(),
    )

    assert strategy.select_next([first, second], {}) is first


def test_suggested_default_does_not_collapse_user_control_or_write_fact():
    node = _node("medical order signed")
    store = LayeredFactStore()
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(),
        ontology_index=_evidence_index(),
        fact_store=store,
        value_suggestions={
            "medical order signed": [
                {
                    "factName": "medical order signed",
                    "suggestedValue": True,
                    "confidence": 0.95,
                    "ontologySnapshotHash": "hash",
                }
            ]
        },
    )

    assert strategy.should_ask(node, {}) is True
    suggestion = strategy.suggested_default_for_node(node)

    assert suggestion["suggestedValue"] is True
    assert suggestion["userControlRequired"] is True
    assert suggestion["advisoryOnly"] is True
    assert store.get_fact_sources("medical order signed") == set()


def test_strategy_abstains_on_stale_ontology_snapshot():
    target = _node("benefit evidence available")
    prerequisite = _node("medical order signed")
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(snapshot_hash=None),
        ontology_index=_evidence_index(),
        fact_store=LayeredFactStore(),
    )

    assert strategy.select_next([target, prerequisite], {}) is target
    trace = list(strategy.get_trace())
    assert trace[0]["action"] == "fallback"
    assert trace[0]["abstentionCause"] == "stale_or_unversioned_ontology_snapshot"


def test_strategy_abstains_on_ambiguous_question_binding():
    target = _node("benefit evidence available")
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(),
        ontology_index=_evidence_index(
            [
                (
                    f"{INF}OtherEligibleEvidence",
                    INF_NAME,
                    "benefit evidence available",
                )
            ]
        ),
        fact_store=LayeredFactStore(),
    )

    assert strategy.select_next([target], {}) is target
    assert list(strategy.get_trace())[0]["abstentionCause"] == (
        "ambiguous_question_binding"
    )


def test_strategy_abstains_on_low_confidence_evidence():
    node = _node("medical order signed")
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(threshold=0.85),
        ontology_index=_evidence_index(
            [(f"{SYN}order", INF_CONFIDENCE, "0.2")]
        ),
        fact_store=LayeredFactStore(),
    )

    assert strategy.select_next([node], {}) is node
    assert list(strategy.get_trace())[0]["abstentionCause"] == (
        "below_confidence_threshold"
    )


def test_strategy_abstains_on_contradictory_default_suggestion():
    node = _node("medical order signed")
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(),
        ontology_index=_evidence_index(),
        fact_store=LayeredFactStore(),
        value_suggestions={
            "medical order signed": [
                {
                    "factName": "medical order signed",
                    "suggestedValue": True,
                    "confidence": 0.95,
                    "ontologySnapshotHash": "hash",
                    "status": "contradicted",
                }
            ]
        },
    )

    assert strategy.select_next([node], {}) is node
    assert list(strategy.get_trace())[0]["abstentionCause"] == (
        "ambiguous_or_contradictory_ontology_default"
    )


def test_strategy_does_not_mutate_ontology_index_or_asserted_facts():
    index = _evidence_index()
    before = index.triples()
    store = LayeredFactStore()
    store.set_fact("medical order signed", FactValue(False), FactSource.ASSERTED)
    strategy = SemanticQuestionStrategy(
        reasoner=_reasoner(),
        ontology_index=index,
        fact_store=store,
    )

    strategy.select_next([_node("benefit evidence available")], {})

    assert index.triples() == before
    assert store.peek_in_layer(
        "medical order signed",
        FactSource.ASSERTED,
    ).get_value() is False
