import hashlib
import json
import time
from typing import Iterable, List

import structlog

from src.tasks.celery_app import CELERY_AVAILABLE, app

log = structlog.get_logger(__name__)


def mine_candidate_rules(session_ids: Iterable[str], rule_name: str) -> List[str]:
    """Small deterministic trace-mining baseline for induction jobs."""
    session_ids = list(session_ids)
    if not session_ids:
        return []
    suffix = hashlib.sha256("|".join(sorted(session_ids)).encode("utf-8")).hexdigest()[:8]
    safe_rule = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in rule_name) or "rule"
    trace_fact = f"trace_pattern_{suffix}"
    learned_fact = f"{safe_rule}_learned_{suffix}"
    return [f"INPUT {trace_fact} AS BOOLEAN\n{learned_fact} IS TRUE IF {trace_fact}"]


def publish_induction_dead_letter(job_id: str, rule_name: str, error: str) -> None:
    try:
        import redis

        redis.Redis().lpush(
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
            publish_induction_dead_letter(job_id, rule_name, str(exc))
            raise

else:  # pragma: no cover

    class _ImmediateResult:
        id = ""

    class _RunInductionBatch:
        def delay(self, session_ids, rule_name):
            return _ImmediateResult()

    run_induction_batch = _RunInductionBatch()
