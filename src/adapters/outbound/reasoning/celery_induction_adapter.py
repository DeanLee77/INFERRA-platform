from typing import Iterable
from threading import Lock

import structlog

from src.services.rule_sandbox import RuleSandbox
from src.ports.induction_port import InductionPort

log = structlog.get_logger(__name__)


class CeleryInductionAdapter(InductionPort):
    """Celery-backed induction adapter with graceful status reporting."""

    _idempotency_lock = Lock()
    _submitted_jobs: dict[str, dict] = {}

    @classmethod
    def clear_idempotency_cache(cls) -> None:
        with cls._idempotency_lock:
            cls._submitted_jobs.clear()

    def start_batch(self, session_ids: Iterable[str], rule_name: str) -> dict:
        session_ids = list(session_ids)
        from src.tasks.induction import build_induction_source_hash, run_induction_batch

        source_hash = build_induction_source_hash(session_ids, rule_name)
        with self._idempotency_lock:
            existing = self._submitted_jobs.get(source_hash)
            if existing is not None:
                log.info(
                    "induction_batch_idempotency_hit",
                    session_id="",
                    node_id="",
                    fact_source="LEARNED",
                    correlation_id=existing["job_id"],
                    rule_name=rule_name,
                    source_hash=source_hash,
                )
                return dict(existing)

        result = run_induction_batch.delay(session_ids, rule_name)
        payload = {
            "job_id": result.id,
            "status": "submitted",
            "rule_name": rule_name,
        }
        with self._idempotency_lock:
            self._submitted_jobs[source_hash] = dict(payload)
        log.info(
            "induction_batch_start",
            session_id="",
            node_id="",
            fact_source="LEARNED",
            correlation_id=getattr(result, "id", ""),
            rule_name=rule_name,
            source_hash=source_hash,
        )
        return payload

    def get_status(self, job_id: str) -> dict:
        from celery.result import AsyncResult

        result = AsyncResult(job_id)
        payload = {
            "job_id": job_id,
            "status": result.status.lower(),
            "candidate_rules": [],
            "errors": [],
        }
        if result.successful() and isinstance(result.result, dict):
            payload.update(result.result)
            payload["status"] = payload.get("status", "completed")
        elif result.failed():
            payload["errors"] = [str(result.result)]
        return payload

    def promote(self, job_id: str, candidate_rule: str) -> dict:
        status = self.get_status(job_id)
        candidates = status.get("candidate_rules", [])
        if candidate_rule not in candidates:
            return {
                "job_id": job_id,
                "status": "rejected",
                "candidate_rules": candidates,
                "errors": ["Candidate rule does not belong to induction job"],
            }
        return RuleSandbox().promote_candidate(
            job_id,
            candidate_rule,
            candidates,
            status.get("rule_name", "induced_rule"),
        ).to_dict()
