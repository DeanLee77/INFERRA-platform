"""Semantic question strategy for ontology-guided question flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.domain.inference.question_strategy import ConservativeQuestionStrategy
from src.domain.nodes.node import Node
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.reasoning.semantic_fact_enricher import OntologyIndex
from src.domain.state.fact_source import FactSource
from src.ports.fact_store_port import FactStorePort


PERFORMANCE_CLAIM = "experimental_unmeasured"


@dataclass(frozen=True)
class SemanticQuestionSignal:
    """Ontology evidence used to rank one askable question."""

    fact_name: str
    node_name: str
    missing_prerequisites: Tuple[str, ...]
    expected_information_gain: int
    can_derive_from_current_facts: bool
    confidence: float
    ontology_snapshot_ref: str
    ontology_snapshot_hash: Optional[str]
    status: str = "usable"
    abstention_cause: Optional[str] = None
    suggested_default: Optional[Dict[str, Any]] = None

    def to_trace_payload(self) -> Dict[str, Any]:
        return {
            "questionName": self.fact_name,
            "nodeName": self.node_name,
            "status": self.status,
            "missingPrerequisites": list(self.missing_prerequisites),
            "expectedInformationGain": self.expected_information_gain,
            "canDeriveFromCurrentFacts": self.can_derive_from_current_facts,
            "confidence": self.confidence,
            "ontologySnapshotRef": self.ontology_snapshot_ref,
            "ontologySnapshotHash": self.ontology_snapshot_hash,
            "abstentionCause": self.abstention_cause,
            "suggestedDefault": (
                dict(self.suggested_default)
                if self.suggested_default is not None
                else None
            ),
            "sourceLabel": FactSource.SEMANTIC.value,
            "advisoryOnly": True,
            "userControlRequired": True,
            "altersDeterministicOutcome": False,
            "reversible": True,
            "fallbackAvailable": True,
            "performanceClaim": PERFORMANCE_CLAIM,
        }


class SemanticQuestionStrategy(ConservativeQuestionStrategy):
    """
    Rank askable questions using frozen ontology reasoning evidence.

    The strategy is deliberately advisory. It does not set facts, mutate rules,
    or auto-answer. When ontology evidence is stale, ambiguous, contradictory,
    or below the configured confidence threshold, it falls back to conservative
    question order and records the abstention cause.
    """

    def __init__(
        self,
        *,
        reasoner: OntologyReasoner,
        ontology_index: OntologyIndex,
        fact_store: FactStorePort,
        value_suggestions: Optional[Mapping[str, Sequence[Dict[str, Any]]]] = None,
        allow_pruning: bool = False,
    ) -> None:
        super().__init__()
        self._reasoner = reasoner
        self._ontology_index = ontology_index
        self._fact_store = fact_store
        self._value_suggestions = {
            str(fact_name): [dict(item) for item in suggestions]
            for fact_name, suggestions in (value_suggestions or {}).items()
        }
        self._allow_pruning = allow_pruning
        self._trace: List[Dict[str, Any]] = []

    def should_ask(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        if not super().should_ask(node, working_memory, has_children=has_children):
            return False

        signal = self.signal_for_node(node)
        if signal.status != "usable":
            self._record(node, "fallback", signal.abstention_cause or "abstained", signal)
            return True

        if (
            self._allow_pruning
            and signal.can_derive_from_current_facts
            and self._has_inferred_fact(signal.fact_name)
        ):
            self._record(
                node,
                "pruned",
                "already_derived_from_current_facts",
                signal,
            )
            return False

        self._record(node, "selected", "conservative_single_candidate", signal)
        return True

    def select_next(
        self,
        candidates: Iterable[Node],
        working_memory: Dict[str, Any],
        has_children_by_name: Optional[Dict[str, bool]] = None,
    ) -> Optional[Node]:
        children_map = has_children_by_name or {}
        askable: List[Tuple[int, Node, SemanticQuestionSignal]] = []
        for index, node in enumerate(candidates):
            if not super().should_ask(
                node,
                working_memory,
                has_children=children_map.get(node.get_node_name(), False),
            ):
                continue
            askable.append((index, node, self.signal_for_node(node)))

        if not askable:
            return None

        usable = [item for item in askable if item[2].status == "usable"]
        if not usable:
            _, selected, signal = askable[0]
            self._record(
                selected,
                "fallback",
                signal.abstention_cause or "ontology_evidence_unusable",
                signal,
            )
            return selected

        prerequisite_names = {
            prerequisite
            for _, _, signal in usable
            for prerequisite in signal.missing_prerequisites
        }

        def rank(item: Tuple[int, Node, SemanticQuestionSignal]) -> Tuple[int, int, int]:
            index, node, signal = item
            fact_name = _question_key_for_node(node)
            prerequisite_priority = 1 if fact_name in prerequisite_names else 0
            return (
                prerequisite_priority,
                signal.expected_information_gain,
                -index,
            )

        _, selected, selected_signal = max(usable, key=rank)
        selected_name = _question_key_for_node(selected)
        for _, node, signal in askable:
            if node is selected:
                continue
            if signal.status != "usable":
                self._record(
                    node,
                    "fallback",
                    signal.abstention_cause or "ontology_evidence_unusable",
                    signal,
                )
                continue
            action = "deferred"
            reason = "higher_information_gain_available"
            if selected_name in signal.missing_prerequisites:
                action = "pruned"
                reason = "missing_prerequisite_selected_first"
            self._record(node, action, reason, signal)

        self._record(selected, "selected", "highest_semantic_question_score", selected_signal)
        return selected

    def signal_for_node(self, node: Node) -> SemanticQuestionSignal:
        fact_name = _question_key_for_node(node)
        node_name = _safe_node_name(node)
        snapshot_ref = self._reasoner.ontology_snapshot_ref
        snapshot_hash = self._reasoner.ontology_snapshot_hash

        if not snapshot_hash:
            return self._abstained_signal(
                fact_name,
                node_name,
                "stale_or_unversioned_ontology_snapshot",
            )

        subjects = self._ontology_index.subjects_for_label(fact_name)
        if len(subjects) != 1:
            return self._abstained_signal(
                fact_name,
                node_name,
                "ungrounded_question_binding"
                if not subjects
                else "ambiguous_question_binding",
            )
        subject_confidence = self._ontology_index.confidence_for(subjects[0], 1.0)
        if subject_confidence < self._reasoner.confidence_threshold:
            return self._abstained_signal(
                fact_name,
                node_name,
                "below_confidence_threshold",
                confidence=subject_confidence,
            )

        suggested_default, suggestion_abstention = self._suggested_default(fact_name)
        if suggestion_abstention is not None:
            return self._abstained_signal(
                fact_name,
                node_name,
                suggestion_abstention,
                suggested_default=suggested_default,
            )

        can_derive, _, confidence = self._reasoner.can_derive(
            fact_name,
            self._fact_store,
            self._ontology_index,
        )
        if can_derive and confidence < self._reasoner.confidence_threshold:
            return self._abstained_signal(
                fact_name,
                node_name,
                "below_confidence_threshold",
                confidence=confidence,
                suggested_default=suggested_default,
            )

        return SemanticQuestionSignal(
            fact_name=fact_name,
            node_name=node_name,
            missing_prerequisites=tuple(
                self._reasoner.missing_prerequisites(fact_name, self._ontology_index)
            ),
            expected_information_gain=self._reasoner.estimate_information_gain(
                fact_name,
                self._ontology_index,
            ),
            can_derive_from_current_facts=can_derive,
            confidence=max(confidence, subject_confidence),
            ontology_snapshot_ref=snapshot_ref,
            ontology_snapshot_hash=snapshot_hash,
            suggested_default=suggested_default,
        )

    def suggested_default_for_node(self, node: Node) -> Optional[Dict[str, Any]]:
        """Return an advisory default payload without suppressing the question."""
        signal = self.signal_for_node(node)
        if signal.status != "usable":
            return None
        if signal.suggested_default is None:
            return None
        payload = dict(signal.suggested_default)
        payload["userControlRequired"] = True
        payload["advisoryOnly"] = True
        payload["altersDeterministicOutcome"] = False
        return payload

    def get_trace(self) -> Sequence[Dict[str, Any]]:
        return tuple(dict(item) for item in self._trace)

    def _abstained_signal(
        self,
        fact_name: str,
        node_name: str,
        cause: str,
        *,
        confidence: float = 0.0,
        suggested_default: Optional[Dict[str, Any]] = None,
    ) -> SemanticQuestionSignal:
        return SemanticQuestionSignal(
            fact_name=fact_name,
            node_name=node_name,
            missing_prerequisites=(),
            expected_information_gain=0,
            can_derive_from_current_facts=False,
            confidence=confidence,
            ontology_snapshot_ref=self._reasoner.ontology_snapshot_ref,
            ontology_snapshot_hash=self._reasoner.ontology_snapshot_hash,
            status="abstained",
            abstention_cause=cause,
            suggested_default=suggested_default,
        )

    def _suggested_default(
        self,
        fact_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        suggestions = [
            dict(item)
            for item in self._value_suggestions.get(fact_name, ())
            if item.get("suggestedValue") is not None
        ]
        if not suggestions:
            return None, None

        available = [
            item for item in suggestions
            if item.get("status", "available") == "available"
        ]
        if len(available) != 1:
            return suggestions[0], "ambiguous_or_contradictory_ontology_default"

        suggestion = available[0]
        if suggestion.get("ontologySnapshotHash") != self._reasoner.ontology_snapshot_hash:
            return suggestion, "stale_or_unversioned_ontology_snapshot"

        try:
            confidence = float(suggestion.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < self._reasoner.confidence_threshold:
            return suggestion, "below_confidence_threshold"

        return suggestion, None

    def _has_inferred_fact(self, fact_name: str) -> bool:
        return FactSource.INFERRED in self._fact_store.get_fact_sources(fact_name)

    def _record(
        self,
        node: Node,
        action: str,
        reason: str,
        signal: SemanticQuestionSignal,
    ) -> None:
        payload = signal.to_trace_payload()
        payload.update(
            {
                "questionName": _question_key_for_node(node),
                "nodeName": _safe_node_name(node),
                "action": action,
                "reason": reason,
            }
        )
        self._trace.append(payload)


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
