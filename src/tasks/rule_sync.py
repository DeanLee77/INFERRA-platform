"""
Rule sync Celery task.

Decouples rule persistence from RDF projection. Idempotent via source_hash.
Celery handles retries safely. Includes dead-letter queue, circuit breaker,
structured logging, and rate limiting.

Gated by ASYNC_SYNC_ENABLED feature flag — the publisher checks the flag
before submitting tasks to the queue.
"""

import hashlib
import json
import time
from typing import Dict, Optional

import structlog

from src.domain.state.feature_flags import FeatureFlags
from src.tasks.celery_app import CELERY_AVAILABLE, app

log = structlog.get_logger()

_inflight_tasks: Dict[str, str] = {}


def publish_rule_updated_event(
    rule_name: str,
    rule_text: str,
    feature_flags: Optional[FeatureFlags] = None,
) -> Optional[str]:
    """
    Publish a RuleUpdated event as a Celery task.

    Gated by ASYNC_SYNC_ENABLED feature flag. Returns the Celery task ID
    if published, None otherwise (flag disabled or Celery unavailable).

    Idempotency: skips if a task with the same source_hash is already
    in-flight (pending, started, or retrying).

    Args:
        rule_name: Name of the rule that was updated
        rule_text: Full text content of the rule
        feature_flags: FeatureFlags snapshot (uses default if None)

    Returns:
        Celery task ID if published, None otherwise
    """
    flags = feature_flags if feature_flags is not None else FeatureFlags()

    if not flags.async_sync_enabled:
        log.debug("async_sync_disabled", rule_name=rule_name)
        return None

    if not CELERY_AVAILABLE:
        log.warning("celery_not_available", rule_name=rule_name)
        return None

    source_hash = hashlib.sha256(rule_text.encode()).hexdigest()

    if _is_task_pending(rule_name, source_hash):
        log.info(
            "rule_updated_skipped_duplicate",
            rule_name=rule_name,
            source_hash=source_hash,
        )
        return None

    result = compile_and_push_to_fuseki.delay(rule_name, rule_text, source_hash)
    _inflight_tasks[source_hash] = result.id

    log.info(
        "rule_updated_published",
        rule_name=rule_name,
        source_hash=source_hash,
        task_id=result.id,
    )
    return result.id


def _is_task_pending(rule_name: str, source_hash: str) -> bool:
    """Check if a task with the same source_hash is already in-flight."""
    if not CELERY_AVAILABLE:
        return False

    task_id = _inflight_tasks.get(source_hash)
    if task_id is None:
        return False

    try:
        from celery.result import AsyncResult

        result = AsyncResult(task_id)
        if result.status in ("PENDING", "STARTED", "RETRY"):
            return True
        del _inflight_tasks[source_hash]
        return False
    except Exception:
        return False


def publish_dead_letter_event(
    rule_name: str, rule_text: str, source_hash: str, error: str
) -> None:
    """Publish to dead-letter Redis list for manual reprocessing."""
    try:
        import redis

        r = redis.Redis()
        r.lpush(
            "inferra:dead_letter_queue",
            json.dumps(
                {
                    "rule_name": rule_name,
                    "source_hash": source_hash,
                    "error": error,
                    "timestamp": time.time(),
                }
            ),
        )
        log.error("dead_letter_published", rule_name=rule_name, error=error)
    except Exception:
        log.error(
            "dead_letter_publish_failed",
            rule_name=rule_name,
            error=error,
            exc_info=True,
        )


if CELERY_AVAILABLE:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3, default_retry_delay=60, rate_limit="10/m")
    def compile_and_push_to_fuseki(
        self, rule_name: str, rule_text: str, source_hash: str
    ) -> dict:
        """
        Celery task: compile rule to RDF and push to Fuseki.

        Idempotent via source_hash — re-running with the same hash produces
        the same SPARQL INSERT (DELETE/INSERT pattern).

        Rate-limited to 10/m per worker to prevent overwhelming Fuseki
        on bulk rule saves.

        Args:
            self: Bound task instance
            rule_name: Name of the rule
            rule_text: Full text content of the rule
            source_hash: SHA-256 hash of rule_text for idempotency

        Returns:
            Dict with status, rule_name, and source_hash
        """
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            task_id=self.request.id,
            rule_name=rule_name,
            source_hash=source_hash,
        )
        task_log = structlog.get_logger()

        try:
            task_log.info("fuseki_sync_start", rule_name=rule_name)

            from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
                InferraToRdfCompiler,
            )

            rdf_triples = InferraToRdfCompiler.compile(rule_text, rule_name)
            _fuseki_write_with_breaker(rdf_triples, version=source_hash)

            if source_hash in _inflight_tasks:
                del _inflight_tasks[source_hash]

            task_log.info("fuseki_sync_success", rule_name=rule_name)
            return {"status": "success", "rule": rule_name, "hash": source_hash}

        except Exception as exc:
            task_log.warning(
                "fuseki_sync_failed",
                rule_name=rule_name,
                retry=self.request.retries,
                error=str(exc),
            )

            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)

            publish_dead_letter_event(rule_name, rule_text, source_hash, str(exc))
            raise


def _fuseki_write_with_breaker(rdf_triples, version: str) -> None:
    """
    Write RDF triples to Fuseki with circuit breaker protection.

    After 5 consecutive failures, opens the circuit for 60s to prevent
    overwhelming an unavailable Fuseki.
    """
    try:
        from circuitbreaker import circuit

        @circuit(failure_threshold=5, recovery_timeout=60)
        def _write_with_protection():
            from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter

            FusekiAdapter.execute_sparql_idempotent_insert(
                rdf_triples, version=version
            )

        _write_with_protection()

    except ImportError:
        import structlog

        fallback_log = structlog.get_logger()
        fallback_log.debug("circuitbreaker_not_installed_fusing_direct_write")
        from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter

        FusekiAdapter.execute_sparql_idempotent_insert(
            rdf_triples, version=version
        )
