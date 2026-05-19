import asyncio
from typing import Any, Dict, Optional

import structlog

from src.domain.fact_values import FactValue
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.question_strategy import ConservativeQuestionStrategy
from src.domain.reasoning.reasoning_router import ReasoningDecision
from src.domain.session.session_manager import ConvergenceResult
from src.domain.state import FactSource
from src.ports.question_strategy_port import QuestionStrategyPort
from src.ports.session_manager_port import SessionManagerPort

log = structlog.get_logger(__name__)


class BackwardChainOrchestrator:
    """Async wrapper around InferenceEngine with convergence management."""

    def __init__(
        self,
        engine: InferenceEngine,
        session_manager: SessionManagerPort,
        strategy: Optional[QuestionStrategyPort] = None,
        reasoning_router: Optional[Any] = None,
    ) -> None:
        self.engine = engine
        self.session_manager = session_manager
        self.strategy = strategy if strategy is not None else ConservativeQuestionStrategy()
        self.reasoning_router = reasoning_router
        self._lock = asyncio.Lock()

    async def run_convergence_loop(
        self,
        session_id: str,
        max_iterations: int = 10,
    ) -> ConvergenceResult:
        async with self._lock:
            trace: list[str] = []
            for iteration in range(1, max_iterations + 1):
                ctx = self.session_manager.get_snapshot(session_id)
                if ctx is not None:
                    ctx.increment_iteration()
                result = self.session_manager.check_convergence(session_id)
                trace.append(result.reason)
                if result.converged:
                    log.info(
                        "convergence_achieved",
                        session_id=session_id,
                        reason=result.reason,
                        iteration=iteration,
                    )
                    return ConvergenceResult(
                        converged=True,
                        reason=result.reason,
                        iteration=iteration,
                        working_memory_hash=result.working_memory_hash,
                        ontology_delta=result.ontology_delta,
                        session_id=session_id,
                        session_duration_ms=result.session_duration_ms,
                        strategy_used=self.strategy.__class__.__name__,
                        convergence_trace=trace,
                    )

                if ctx is not None and self.reasoning_router is not None and not ctx.abduction_attempted:
                    decision = self.reasoning_router.route(
                        session_id=session_id,
                        target=ctx.target,
                        working_memory=ctx.fact_store.get_unified_view(),
                        graph_snapshot=self._graph_snapshot(),
                        iteration_count=iteration,
                        has_unasked_questions=False,
                        converged=False,
                        rule_name=ctx.rule_name,
                    )
                    if decision.mode == "ABDUCTION" and decision.action == "INJECT_HYPOTHESIS":
                        self._inject_best_hypothesis(ctx, decision)
                        trace.append("ABDUCTION_INJECTED")
                        follow_up = self.session_manager.check_convergence(session_id)
                        trace.append(follow_up.reason)
                        if follow_up.converged:
                            log.info(
                                "convergence_achieved_after_abduction",
                                session_id=session_id,
                                node_id=ctx.target,
                                fact_source="HYPOTHETICAL",
                                correlation_id=session_id,
                                reason=follow_up.reason,
                                iteration=iteration,
                            )
                            return ConvergenceResult(
                                converged=True,
                                reason=follow_up.reason,
                                iteration=iteration,
                                working_memory_hash=follow_up.working_memory_hash,
                                ontology_delta=follow_up.ontology_delta,
                                session_id=session_id,
                                session_duration_ms=follow_up.session_duration_ms,
                                strategy_used=self.strategy.__class__.__name__,
                                convergence_trace=trace,
                            )
                    elif decision.mode == "INDUCTION" and decision.induction_job_id:
                        ctx.set_induction_job(decision.induction_job_id)
                        trace.append("INDUCTION_STARTED")

            log.warning(
                "convergence_cap_exceeded",
                session_id=session_id,
                max_iterations=max_iterations,
            )
            return ConvergenceResult(
                converged=False,
                reason="ITERATION_CAP",
                iteration=max_iterations,
                working_memory_hash=self.session_manager.get_wm_hash(session_id),
                ontology_delta=self.session_manager.get_ontology_delta(session_id),
                session_id=session_id,
                strategy_used=self.strategy.__class__.__name__,
                convergence_trace=trace,
            )

    def _graph_snapshot(self) -> Dict[str, Any]:
        graph = self.engine.get_dependency_graph()
        if graph is None:
            return {}
        nodes = sorted(graph.all_node_names())
        return {
            "nodes": nodes,
            "child_groups": {name: graph.get_child_groups(name) for name in nodes},
            "parents": {name: sorted(graph.get_parent_edges(name)) for name in nodes},
        }

    def _inject_best_hypothesis(self, ctx: Any, decision: ReasoningDecision) -> None:
        if not decision.hypotheses:
            return
        best = decision.hypotheses[0]
        fact_name = str(best.get("fact_name", ""))
        if not fact_name:
            return
        ctx.fact_store.set_fact(
            fact_name,
            FactValue(self._coerce_hypothesis_value(best.get("suggested_value"))),
            FactSource.HYPOTHETICAL,
        )
        ctx.record_abduction_attempt(decision.hypotheses)

    @staticmethod
    def _coerce_hypothesis_value(value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if text.lower() == "true":
                return True
            if text.lower() == "false":
                return False
            return text
        return value
