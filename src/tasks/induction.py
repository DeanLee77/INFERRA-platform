import hashlib
import json
import time
from typing import Any, Iterable, List, Optional

import structlog

from src.infrastructure.secrets import redis_client_from_env
from src.tasks.celery_app import CELERY_AVAILABLE, app

log = structlog.get_logger(__name__)


class InductionCircuitOpenError(RuntimeError):
    """Raised when induction processing is temporarily circuit-open."""


class InductionCircuitBreaker:
    """Tiny in-process circuit breaker for induction worker failures."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.recovery_timeout:
            self.failure_count = 0
            self.opened_at = None
            return
        raise InductionCircuitOpenError("Induction circuit is open")

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.monotonic()

    def is_open(self) -> bool:
        return self.opened_at is not None


_induction_circuit = InductionCircuitBreaker()


def build_induction_source_hash(session_ids: Iterable[str], rule_name: str) -> str:
    payload = {
        "rule_name": rule_name,
        "session_ids": sorted(str(session_id) for session_id in session_ids),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def mine_candidate_rules(
    session_ids: Iterable[str],
    rule_name: str,
    session_data_list: Optional[Iterable[dict[str, Any]]] = None,
) -> List[str]:
    """Mine candidate rules from session snapshots, with a deterministic fallback."""
    session_ids = list(session_ids)
    if session_data_list:
        mined = _mine_candidate_rules_from_session_data(session_data_list, rule_name)
        if mined:
            return mined

    if not session_ids:
        return []
    suffix = hashlib.sha256("|".join(sorted(session_ids)).encode("utf-8")).hexdigest()[:8]
    safe_rule = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in rule_name) or "rule"
    trace_fact = f"trace_pattern_{suffix}"
    learned_fact = f"{safe_rule}_learned_{suffix}"
    return [f"INPUT {trace_fact} AS BOOLEAN\n{learned_fact} IS TRUE IF {trace_fact}"]


def _mine_candidate_rules_from_session_data(
    session_data_list: Iterable[dict[str, Any]],
    rule_name: str,
) -> List[str]:
    try:
        from src.domain.reasoning.inferra_compiler import InferraCompiler
        from src.domain.reasoning.pattern_miner import PatternMiner
        from src.domain.reasoning.trace_extractor import TraceExtractor

        extractor = TraceExtractor()
        patterns = []
        for idx, session_data in enumerate(session_data_list):
            patterns.extend(
                extractor.extract_from_dict(
                    session_data,
                    session_id=str(session_data.get("session_id", idx)) if isinstance(session_data, dict) else str(idx),
                    rule_name=rule_name,
                )
            )
        candidates = PatternMiner().mine(patterns)
        compiled = InferraCompiler().compile_batch(candidates)
        log.info(
            "induction_candidates_mined",
            session_id="",
            node_id="",
            fact_source="LEARNED",
            correlation_id="",
            rule_name=rule_name,
            pattern_count=len(patterns),
            candidate_count=len(candidates),
            compiled_count=len(compiled),
        )
        return compiled
    except Exception as exc:
        log.warning(
            "induction_trace_mining_failed",
            session_id="",
            node_id="",
            fact_source="LEARNED",
            correlation_id="",
            rule_name=rule_name,
            error=str(exc),
            exc_info=True,
        )
        return []


def publish_induction_dead_letter(job_id: str, rule_name: str, error: str) -> None:
    try:
        redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0).lpush(
            "inferra:induction:dead_letter_queue",
            json.dumps(
                {
                    "job_id": job_id,
                    "rule_name": rule_name,
                    "error": error,
                    "timestamp": time.time(),
                }
            ),
        )
    except Exception:
        log.error(
            "induction_dead_letter_publish_failed",
            session_id="",
            node_id="",
            fact_source="LEARNED",
            correlation_id=job_id,
            rule_name=rule_name,
            error=error,
            exc_info=True,
        )


if CELERY_AVAILABLE:

    @app.task(bind=True, max_retries=3, default_retry_delay=30, rate_limit="5/m")
    def run_induction_batch(self, session_ids: list[str], rule_name: str) -> dict:
        job_id = self.request.id
        try:
            _induction_circuit.before_call()
            log.info(
                "induction_batch_running",
                session_id="",
                node_id="",
                fact_source="LEARNED",
                correlation_id=job_id,
                rule_name=rule_name,
                session_count=len(session_ids),
            )
            from src.services.rule_sandbox import RuleSandbox

            candidates, errors = RuleSandbox().filter_valid_candidates(
                job_id,
                rule_name,
                mine_candidate_rules(session_ids, rule_name),
            )
            _induction_circuit.record_success()
            return {
                "job_id": job_id,
                "status": "completed",
                "rule_name": rule_name,
                "candidate_rules": candidates,
                "errors": errors,
            }
        except Exception as exc:
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            _induction_circuit.record_failure()
            publish_induction_dead_letter(job_id, rule_name, str(exc))
            raise

else:  # pragma: no cover

    class _ImmediateResult:
        id = ""

    class _RunInductionBatch:
        def delay(self, session_ids, rule_name):
            return _ImmediateResult()

    run_induction_batch = _RunInductionBatch()
