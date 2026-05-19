from threading import Lock
from typing import Dict, List, Optional

import structlog

log = structlog.get_logger(__name__)


class ConvergenceMetrics:
    """In-memory collector for reasoning convergence evidence."""

    def __init__(self) -> None:
        self._iterations: Dict[str, int] = {}
        self._time_to_converge_ms: Dict[str, float] = {}
        self._convergence_reasons: Dict[str, str] = {}
        self._wm_hash_stability: Dict[str, List[str]] = {}
        self._ontology_delta_counts: Dict[str, int] = {}
        self._prov_o_triple_counts: Dict[str, int] = {}
        self._lock = Lock()

    def record_convergence(
        self,
        session_id: str,
        iterations: int,
        time_ms: float,
        reason: str,
    ) -> None:
        with self._lock:
            self._iterations[session_id] = max(int(iterations), 0)
            self._time_to_converge_ms[session_id] = max(float(time_ms), 0.0)
            self._convergence_reasons[session_id] = str(reason)
        log.info(
            "convergence_metrics_recorded",
            session_id=session_id,
            node_id="",
            fact_source="",
            correlation_id=session_id,
            iterations=max(int(iterations), 0),
            time_ms=max(float(time_ms), 0.0),
            reason=str(reason),
        )

    def record_wm_hash_transition(
        self,
        session_id: str,
        old_hash: str,
        new_hash: str,
    ) -> None:
        with self._lock:
            self._wm_hash_stability.setdefault(session_id, []).append(str(new_hash))

    def record_ontology_delta(self, session_id: str, delta_count: int) -> None:
        with self._lock:
            self._ontology_delta_counts[session_id] = max(int(delta_count), 0)

    def record_prov_o_triple_count(self, session_id: str, count: int) -> None:
        with self._lock:
            self._prov_o_triple_counts[session_id] = max(int(count), 0)

    def get_metrics(self) -> dict:
        with self._lock:
            return {
                "convergence_iterations": dict(self._iterations),
                "time_to_converge_ms": dict(self._time_to_converge_ms),
                "convergence_reasons": dict(self._convergence_reasons),
                "working_memory_hashes": {
                    session_id: list(hashes)
                    for session_id, hashes in self._wm_hash_stability.items()
                },
                "ontology_delta_counts": dict(self._ontology_delta_counts),
                "prov_o_triple_counts": dict(self._prov_o_triple_counts),
            }

    def get_session_metrics(self, session_id: str) -> Optional[dict]:
        with self._lock:
            if session_id not in self._iterations:
                return None
            return {
                "iterations": self._iterations.get(session_id, 0),
                "time_to_converge_ms": self._time_to_converge_ms.get(session_id, 0.0),
                "convergence_reason": self._convergence_reasons.get(session_id, ""),
                "working_memory_hashes": list(self._wm_hash_stability.get(session_id, [])),
                "ontology_delta_count": self._ontology_delta_counts.get(session_id, 0),
                "prov_o_triple_count": self._prov_o_triple_counts.get(session_id, 0),
            }

    def clear(self) -> None:
        with self._lock:
            self._iterations.clear()
            self._time_to_converge_ms.clear()
            self._convergence_reasons.clear()
            self._wm_hash_stability.clear()
            self._ontology_delta_counts.clear()
            self._prov_o_triple_counts.clear()


convergence_metrics = ConvergenceMetrics()
