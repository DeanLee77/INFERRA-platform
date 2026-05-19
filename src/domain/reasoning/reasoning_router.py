from dataclasses import dataclass, field
import os
from typing import Any, Dict, Iterable, List, Optional

import structlog

from src.ports.abduction_port import AbductionPort
from src.ports.induction_port import InductionPort

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ReasoningDecision:
    mode: str
    action: str
    confidence: float = 1.0
    reason: str = ""
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    induction_job_id: Optional[str] = None


class ReasoningRouter:
    """
    Deduction-first router for optional abduction/induction flows.

    The router is intentionally read-only: it can propose a routing decision
    and return hypotheses, but mutation of LayeredFactStore remains the
    orchestrator's responsibility under its session lock.
    """

    MIN_DEDUCTION_ITERATIONS_BEFORE_ABDUCTION = 2

    def __init__(
        self,
        abduction: AbductionPort,
        induction: Optional[InductionPort] = None,
        *,
        abduction_enabled: bool = False,
        induction_pipeline: bool = False,
        confidence_thresholds: bool = True,
        min_confidence: Optional[float] = None,
        rule_confidence_thresholds: Optional[Dict[str, float]] = None,
        max_hypotheses: int = 5,
    ) -> None:
        self.abduction = abduction
        self.induction = induction
        self.abduction_enabled = abduction_enabled
        self.induction_pipeline = induction_pipeline
        self.confidence_thresholds = confidence_thresholds
        self.min_confidence = (
            float(min_confidence)
            if min_confidence is not None
            else self._confidence_threshold_from_env()
        )
        self.rule_confidence_thresholds = dict(rule_confidence_thresholds or {})
        self.max_hypotheses = max_hypotheses

    def route(
        self,
        *,
        session_id: str,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
        iteration_count: int,
        has_unasked_questions: bool,
        converged: bool = False,
        trace_backlog_size: int = 0,
        rule_name: str = "",
        rule_min_confidence: Optional[float] = None,
        session_min_confidence: Optional[float] = None,
    ) -> ReasoningDecision:
        if converged:
            return ReasoningDecision("DEDUCTION", "COMPLETE", reason="converged")
        if has_unasked_questions:
            return ReasoningDecision("DEDUCTION", "CONTINUE_LOOP", reason="unasked_questions")
        if iteration_count < self.MIN_DEDUCTION_ITERATIONS_BEFORE_ABDUCTION:
            return ReasoningDecision("DEDUCTION", "CONTINUE_LOOP", reason="deduction_warmup")

        if self.abduction_enabled:
            min_confidence = self._threshold_for(
                rule_name=rule_name,
                rule_min_confidence=rule_min_confidence,
                session_min_confidence=session_min_confidence,
            )
            hypotheses = self._rank_hypotheses(
                self.abduction.propose_hypotheses(
                    target=target,
                    working_memory=working_memory,
                    graph_snapshot=graph_snapshot,
                ),
                min_confidence=min_confidence,
            )
            if hypotheses:
                best = hypotheses[0]
                log.info(
                    "abduction_route_selected",
                    session_id=session_id,
                    node_id=target,
                    fact_source="HYPOTHETICAL",
                    correlation_id=session_id,
                    hypothesis_count=len(hypotheses),
                    best_confidence=best["confidence"],
                )
                return ReasoningDecision(
                    mode="ABDUCTION",
                    action="INJECT_HYPOTHESIS",
                    confidence=best["confidence"],
                    reason="deduction_stalled",
                    hypotheses=hypotheses,
                )

        if self.induction_pipeline and self.induction is not None and trace_backlog_size > 0:
            job = self.induction.start_batch([session_id], rule_name)
            return ReasoningDecision(
                mode="INDUCTION",
                action="START_BATCH",
                confidence=0.5,
                reason="trace_backlog",
                induction_job_id=job.get("job_id"),
            )

        return ReasoningDecision("DEDUCTION", "CONTINUE_LOOP", reason="no_alternate_route")

    def _rank_hypotheses(
        self,
        hypotheses: Iterable[Dict[str, Any]],
        *,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        threshold = self.min_confidence if min_confidence is None else min_confidence
        pruned: List[Dict[str, Any]] = []
        for hypothesis in hypotheses:
            confidence = float(hypothesis.get("confidence", 0.0))
            if self.confidence_thresholds and confidence < threshold:
                continue
            if not bool(hypothesis.get("ontology_consistent", True)):
                continue
            item = dict(hypothesis)
            item["confidence"] = confidence
            pruned.append(item)
        pruned.sort(key=lambda item: (-item["confidence"], str(item.get("fact_name", ""))))
        return pruned[: self.max_hypotheses]

    def _threshold_for(
        self,
        *,
        rule_name: str,
        rule_min_confidence: Optional[float],
        session_min_confidence: Optional[float],
    ) -> float:
        if session_min_confidence is not None:
            return min(max(float(session_min_confidence), 0.0), 1.0)
        if rule_min_confidence is not None:
            return min(max(float(rule_min_confidence), 0.0), 1.0)
        if rule_name in self.rule_confidence_thresholds:
            return min(max(float(self.rule_confidence_thresholds[rule_name]), 0.0), 1.0)
        return self.min_confidence

    @staticmethod
    def _confidence_threshold_from_env() -> float:
        raw = os.environ.get("INFERRA_CONFIDENCE_THRESHOLD") or os.environ.get("CONFIDENCE_THRESHOLD")
        if raw is None:
            return 0.65
        try:
            return min(max(float(raw), 0.0), 1.0)
        except ValueError:
            log.warning("invalid_confidence_threshold", value=raw)
            return 0.65
