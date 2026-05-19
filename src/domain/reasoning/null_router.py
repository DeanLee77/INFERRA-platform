from typing import Any, Dict

from src.domain.reasoning.reasoning_router import ReasoningDecision


class NullReasoningRouter:
    """Fallback router for REASONING_ROUTER=false."""

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
    ) -> ReasoningDecision:
        action = "COMPLETE" if converged else "CONTINUE_LOOP"
        reason = "converged" if converged else "router_disabled"
        return ReasoningDecision("DEDUCTION", action, reason=reason)
