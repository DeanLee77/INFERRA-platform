import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

from src.domain.fact_values import FactValue
from src.domain.session.inference_context import InferenceContext
from src.ports.session_manager_port import SessionManagerPort

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ConvergenceResult:
    converged: bool
    reason: str
    iteration: int
    working_memory_hash: str
    ontology_delta: int
    session_id: str = ""
    session_duration_ms: float = 0.0
    strategy_used: str = "conservative"
    convergence_trace: List[str] = field(default_factory=list)


class SessionManager(SessionManagerPort):
    """LRU session snapshot manager with deterministic convergence checks."""

    MAX_SNAPSHOTS = 1000
    SNAPSHOT_TTL_SECONDS = 86400

    def __init__(
        self,
        max_snapshots: int = MAX_SNAPSHOTS,
        ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._max_snapshots = max_snapshots
        self._ttl_seconds = ttl_seconds
        self._clock = clock if clock is not None else time.time
        self._snapshots: "OrderedDict[str, InferenceContext]" = OrderedDict()
        self._snapshot_timestamps: Dict[str, float] = {}
        self._prev_wm_hashes: Dict[str, str] = {}

    def create_snapshot(self, session_id: str, ctx: InferenceContext) -> None:
        if len(self._snapshots) >= self._max_snapshots and session_id not in self._snapshots:
            oldest = next(iter(self._snapshots))
            self.remove_snapshot(oldest)
            log.warning("session_manager_lru_eviction", evicted_session=oldest)
        self._snapshots[session_id] = ctx
        self._snapshots.move_to_end(session_id)
        self._snapshot_timestamps[session_id] = self._clock()
        log.info("session_snapshot_created", session_id=session_id)

    def get_snapshot(self, session_id: str) -> Optional[InferenceContext]:
        if session_id not in self._snapshots:
            return None
        if self._clock() - self._snapshot_timestamps.get(session_id, 0) > self._ttl_seconds:
            self.remove_snapshot(session_id)
            return None
        self._snapshots.move_to_end(session_id)
        return self._snapshots[session_id]

    def check_convergence(
        self,
        session_id: str,
        goal: Optional[str] = None,
        mandatory: Optional[List[str]] = None,
    ) -> ConvergenceResult:
        ctx = self.get_snapshot(session_id)
        if ctx is None:
            return ConvergenceResult(False, "PENDING", 0, "", 0, session_id=session_id)

        wm = ctx.fact_store.get_unified_view()
        target = goal if goal is not None else ctx.target
        mandatory_nodes = mandatory if mandatory is not None else ctx.mandatory

        goal_reached = self._fact_is_known(wm.get(target))
        mandatory_met = all(self._fact_is_known(wm.get(name)) for name in mandatory_nodes)
        current_hash = self._compute_wm_hash(wm)
        state_stable = self._prev_wm_hashes.get(session_id) == current_hash
        ontology_stable = ctx.ontology_delta == 0
        self._prev_wm_hashes[session_id] = current_hash

        reason = "PENDING"
        converged = False
        if goal_reached and mandatory_met and state_stable and ontology_stable:
            reason = "FIXED_POINT"
            converged = True
        elif goal_reached and mandatory_met and state_stable:
            reason = "GOAL_REACHED_STABLE"
            converged = True
        elif goal_reached and mandatory_met:
            reason = "GOAL_REACHED"
            converged = True

        result = ConvergenceResult(
            converged=converged,
            reason=reason,
            iteration=ctx.iteration_count,
            working_memory_hash=current_hash,
            ontology_delta=ctx.ontology_delta,
            session_id=session_id,
            session_duration_ms=max((self._clock() - ctx.started_at.timestamp()) * 1000, 0.0),
            strategy_used=ctx.question_strategy_name,
            convergence_trace=[*ctx.convergence_trace, reason],
        )
        log.info(
            "session_convergence_checked",
            session_id=session_id,
            reason=reason,
            converged=converged,
        )
        return result

    def get_wm_hash(self, session_id: str) -> str:
        return self._prev_wm_hashes.get(session_id, "")

    def get_ontology_delta(self, session_id: str) -> int:
        ctx = self.get_snapshot(session_id)
        return ctx.ontology_delta if ctx is not None else 0

    def remove_snapshot(self, session_id: str) -> None:
        self._snapshots.pop(session_id, None)
        self._snapshot_timestamps.pop(session_id, None)
        self._prev_wm_hashes.pop(session_id, None)

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    def _compute_wm_hash(self, wm: Dict[str, FactValue]) -> str:
        canonical = {
            key: self._canonical_fact(wm[key])
            for key in sorted(wm.keys())
        }
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _canonical_fact(self, fact: Any) -> Any:
        if hasattr(fact, "get_value") and hasattr(fact, "get_value_type"):
            return {
                "type": str(fact.get_value_type()),
                "value": self._canonical_value(fact.get_value()),
            }
        return self._canonical_value(fact)

    def _canonical_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._canonical_fact(item) for item in value]
        if isinstance(value, dict):
            return {str(k): self._canonical_value(value[k]) for k in sorted(value.keys())}
        return value

    @staticmethod
    def _fact_is_known(value: Optional[FactValue]) -> bool:
        return value is not None and value.get_value() is not None
