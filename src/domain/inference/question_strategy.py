from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from src.domain.inference.question_resolver import QuestionResolver
from src.domain.nodes.node import Node
from src.domain.state import FactSource
from src.ports.question_strategy_port import QuestionStrategyPort


def _noop_question_callback(_: object) -> None:
    return None


@dataclass(frozen=True)
class ReachabilityEvidence:
    """Ontology-derived advisory reachability for one candidate question."""

    fact_name: str
    reachable: bool
    reason: str
    ontology_snapshot_ref: str
    confidence: float = 0.0
    stale: bool = False
    source_label: str = FactSource.SEMANTIC.value


@dataclass(frozen=True)
class AbductiveBridgeSuggestion:
    """Hypothetical alternative evidence for a missing fact."""

    missing_fact_name: str
    alternative_fact_name: str
    relationship_iri: str
    basis: str
    suggested_value: Any = True
    confidence: float = 0.0
    source_label: str = FactSource.HYPOTHETICAL.value
    confirmation_status: str = "hypothetical"
    candidate_type: str = "hypothesis"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "abductive_bridge",
            "missingFactName": self.missing_fact_name,
            "alternativeFactName": self.alternative_fact_name,
            "relationshipIri": self.relationship_iri,
            "basis": self.basis,
            "suggestedValue": self.suggested_value,
            "confidence": self.confidence,
            "sourceLabel": self.source_label,
            "confirmationStatus": self.confirmation_status,
            "candidateType": self.candidate_type,
            "altersDeterministicOutcome": False,
        }


class ConservativeQuestionStrategy(QuestionStrategyPort):
    """
    Zero-behaviour-change question strategy.

    This wraps the existing QuestionResolver decision rules behind a port so
    ontology- or LLM-enhanced strategies can be introduced without touching the
    inference engine.
    """

    def __init__(self) -> None:
        self._resolver = QuestionResolver(_noop_question_callback)

    def should_ask(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        return self._resolver._requires_user_input(
            node,
            working_memory,
            has_children=has_children,
        )

    def select_next(
        self,
        candidates: Iterable[Node],
        working_memory: Dict[str, Any],
        has_children_by_name: Optional[Dict[str, bool]] = None,
    ) -> Optional[Node]:
        children_map = has_children_by_name or {}
        for node in candidates:
            has_children = children_map.get(node.get_node_name(), False)
            if self.should_ask(node, working_memory, has_children=has_children):
                return node
        return None


class OntologyReachabilityQuestionStrategy(ConservativeQuestionStrategy):
    """
    Advisory reachability pruning for backward-chaining candidate questions.

    Ontology data can prioritize or skip branches only when the evidence is
    current and explicit. Missing or stale reachability falls back to the
    conservative strategy and records the fallback reason.
    """

    PERFORMANCE_CLAIM = "experimental_unmeasured"

    def __init__(
        self,
        reachability: Iterable[ReachabilityEvidence]
        | Mapping[str, ReachabilityEvidence | bool | Dict[str, Any]],
        *,
        bridge_suggestions: Iterable[AbductiveBridgeSuggestion] = (),
        skip_unreachable: bool = True,
    ) -> None:
        super().__init__()
        self._reachability = _normalize_reachability(reachability)
        self._bridge_suggestions = {
            item.missing_fact_name: item for item in bridge_suggestions
        }
        self._skip_unreachable = skip_unreachable
        self._trace: list[Dict[str, Any]] = []

    def should_ask(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        if not super().should_ask(node, working_memory, has_children=has_children):
            return False

        evidence = self._usable_evidence_for(node)
        if evidence is None:
            self._record(node, "fallback", "ontology_missing_or_stale", None)
            return True
        if evidence.reachable:
            self._record(node, "selected", evidence.reason, evidence)
            return True
        if self._skip_unreachable:
            self._record(node, "skipped", evidence.reason, evidence)
            return False

        self._record(node, "deprioritized", evidence.reason, evidence)
        return True

    def select_next(
        self,
        candidates: Iterable[Node],
        working_memory: Dict[str, Any],
        has_children_by_name: Optional[Dict[str, bool]] = None,
    ) -> Optional[Node]:
        children_map = has_children_by_name or {}
        askable: list[Node] = []
        for node in candidates:
            if ConservativeQuestionStrategy.should_ask(
                self,
                node,
                working_memory,
                has_children=children_map.get(node.get_node_name(), False),
            ):
                askable.append(node)

        if not askable:
            return None

        reachable: list[tuple[Node, ReachabilityEvidence]] = []
        unknown: list[Node] = []
        unreachable: list[tuple[Node, ReachabilityEvidence]] = []

        for node in askable:
            evidence = self._usable_evidence_for(node)
            if evidence is None:
                unknown.append(node)
            elif evidence.reachable:
                reachable.append((node, evidence))
            else:
                unreachable.append((node, evidence))

        if reachable:
            selected, selected_evidence = reachable[0]
            for node, evidence in unreachable:
                self._record(node, "skipped", evidence.reason, evidence)
            self._record(selected, "selected", selected_evidence.reason, selected_evidence)
            return selected

        if unknown:
            selected = unknown[0]
            self._record(selected, "fallback", "ontology_missing_or_stale", None)
            return selected

        selected, evidence = unreachable[0]
        self._record(
            selected,
            "fallback",
            "all_reachable_alternatives_pruned",
            evidence,
        )
        return selected

    def suggest_alternative_evidence(
        self,
        missing_fact_name: str,
    ) -> Optional[Dict[str, Any]]:
        suggestion = self._bridge_suggestions.get(missing_fact_name)
        if suggestion is None:
            return None
        payload = suggestion.to_dict()
        self._trace.append(
            {
                "questionName": missing_fact_name,
                "action": "hypothesis_suggested",
                "reason": suggestion.basis,
                "sourceLabel": FactSource.HYPOTHETICAL.value,
                "candidateType": suggestion.candidate_type,
                "reversible": True,
                "fallbackAvailable": True,
                "performanceClaim": self.PERFORMANCE_CLAIM,
            }
        )
        return payload

    def get_trace(self) -> Sequence[Dict[str, Any]]:
        return tuple(dict(item) for item in self._trace)

    def _usable_evidence_for(self, node: Node) -> Optional[ReachabilityEvidence]:
        evidence = self._reachability.get(_question_key_for_node(node))
        if evidence is None or evidence.stale:
            return None
        return evidence

    def _record(
        self,
        node: Node,
        action: str,
        reason: str,
        evidence: Optional[ReachabilityEvidence],
    ) -> None:
        self._trace.append(
            {
                "questionName": _question_key_for_node(node),
                "nodeName": _safe_node_name(node),
                "action": action,
                "reason": reason,
                "sourceLabel": (
                    evidence.source_label if evidence is not None else "NONE"
                ),
                "ontologySnapshotRef": (
                    evidence.ontology_snapshot_ref if evidence is not None else None
                ),
                "confidence": evidence.confidence if evidence is not None else 0.0,
                "reversible": True,
                "fallbackAvailable": True,
                "performanceClaim": self.PERFORMANCE_CLAIM,
            }
        )


def _normalize_reachability(
    reachability: Iterable[ReachabilityEvidence]
    | Mapping[str, ReachabilityEvidence | bool | Dict[str, Any]],
) -> Dict[str, ReachabilityEvidence]:
    if isinstance(reachability, Mapping):
        items = reachability.items()
        return {
            fact_name: _coerce_reachability(fact_name, value)
            for fact_name, value in items
        }
    return {item.fact_name: item for item in reachability}


def _coerce_reachability(
    fact_name: str,
    value: ReachabilityEvidence | bool | Dict[str, Any],
) -> ReachabilityEvidence:
    if isinstance(value, ReachabilityEvidence):
        return value
    if isinstance(value, bool):
        return ReachabilityEvidence(
            fact_name=fact_name,
            reachable=value,
            reason="boolean_fixture",
            ontology_snapshot_ref="inline",
        )
    return ReachabilityEvidence(
        fact_name=fact_name,
        reachable=bool(value.get("reachable", False)),
        reason=str(value.get("reason", "ontology_reachability")),
        ontology_snapshot_ref=str(value.get("ontologySnapshotRef", "inline")),
        confidence=float(value.get("confidence", 0.0)),
        stale=bool(value.get("stale", False)),
    )


def _question_key_for_node(node: Node) -> str:
    variable_name = node.get_variable_name()
    if isinstance(variable_name, str) and variable_name:
        return variable_name
    return _safe_node_name(node)


def _safe_node_name(node: Node) -> str:
    node_name = node.get_node_name()
    if isinstance(node_name, str):
        return node_name
    return str(node_name)
