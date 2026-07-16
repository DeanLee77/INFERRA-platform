"""
Rule sync Celery task.

Decouples rule persistence from RDF projection. Idempotent via source_hash.
Celery handles retries safely. Includes dead-letter queue, circuit breaker,
structured logging, and rate limiting.

Gated by ASYNC_SYNC_ENABLED feature flag — the publisher checks the flag
before submitting tasks to the queue.
"""

import json
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, Optional

import structlog

from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter
from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
    COMPILER_VERSION,
    InferraToRdfCompiler,
)
from src.domain.state.feature_flags import (
    FeatureFlags,
    assert_feature_flag_snapshot_match,
    get_effective_feature_flag_snapshot_hash,
)
from src.infrastructure.secrets import redis_client_from_env
from src.tasks.celery_app import CELERY_AVAILABLE, app

log = structlog.get_logger()

_inflight_tasks: Dict[str, str] = {}
DEAD_LETTER_QUEUE = "inferra:dead_letter_queue"
PROJECTION_METADATA_KEY_PREFIX = "inferra:ontology_projection"


def build_projection_source_hash(rule_text: str) -> str:
    """Hash the exact import-aware source text compiled into the RDF projection."""
    return sha256(rule_text.encode("utf-8")).hexdigest()


def get_projection_metadata(rule_name: str) -> Optional[dict[str, Any]]:
    """Read stored projection metadata from Redis, if available."""
    try:
        r = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
        raw = r.get(_projection_metadata_key(rule_name))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        log.warning("projection_metadata_read_failed", rule_name=rule_name, exc_info=True)
        return None


def record_projection_metadata(
    rule_name: str,
    metadata: dict[str, Any],
) -> bool:
    """Persist sanitized projection metadata for status APIs and AXIOM display."""
    payload = {
        "rule_name": rule_name,
        "compiler_version": COMPILER_VERSION,
        "graph_uri": FusekiAdapter.rule_projection_graph_uri(rule_name),
        "sync_timestamp": _utc_timestamp(),
        **metadata,
    }
    try:
        r = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
        r.set(_projection_metadata_key(rule_name), json.dumps(payload, sort_keys=True))
        return True
    except Exception:
        log.warning("projection_metadata_write_failed", rule_name=rule_name, exc_info=True)
        return False


def list_rule_dead_letters(
    rule_name: Optional[str] = None,
    source_hash: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return visible Fuseki sync dead letters, filtered by rule/source when supplied."""
    try:
        r = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
        raw_items = r.lrange(DEAD_LETTER_QUEUE, 0, max(0, int(limit)) - 1)
    except Exception:
        log.warning("dead_letter_read_failed", rule_name=rule_name, exc_info=True)
        return []

    events: list[dict[str, Any]] = []
    for raw in raw_items:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            event = json.loads(raw)
        except Exception:
            continue
        if not isinstance(event, dict):
            continue
        if rule_name is not None and event.get("rule_name") != rule_name:
            continue
        if source_hash is not None and event.get("source_hash") != source_hash:
            continue
        events.append(event)
    return events


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

    source_hash = build_projection_source_hash(rule_text)

    if _is_task_pending(rule_name, source_hash):
        log.info(
            "rule_updated_skipped_duplicate",
            rule_name=rule_name,
            source_hash=source_hash,
        )
        return None

    result = compile_and_push_to_fuseki.delay(
        rule_name,
        rule_text,
        source_hash,
        get_effective_feature_flag_snapshot_hash(),
    )
    _inflight_tasks[source_hash] = result.id
    record_projection_metadata(
        rule_name,
        {
            "source_hash": source_hash,
            "sync_status": "syncing",
            "job_id": result.id,
        },
    )

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
    timestamp = _utc_timestamp()
    dead_letter_id = uuid.uuid4().hex
    error_summary = _sanitize_error_summary(error)
    graph_uri = FusekiAdapter.rule_projection_graph_uri(rule_name)
    payload = {
        "dead_letter_id": dead_letter_id,
        "rule_name": rule_name,
        "source_hash": source_hash,
        "compiler_version": COMPILER_VERSION,
        "graph_uri": graph_uri,
        "last_error_code": "FUSEKI_SYNC_FAILED",
        "last_error_summary": error_summary,
        "error": error_summary,
        "timestamp": timestamp,
    }
    try:
        r = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
        r.lpush(DEAD_LETTER_QUEUE, json.dumps(payload, sort_keys=True))
        record_projection_metadata(
            rule_name,
            {
                "source_hash": source_hash,
                "sync_status": "dead_lettered",
                "dead_letter_visible": True,
                "dead_letter_id": dead_letter_id,
                "last_error_code": "FUSEKI_SYNC_FAILED",
                "last_error_summary": error_summary,
                "graph_uri": graph_uri,
                "sync_timestamp": timestamp,
            },
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

    @app.task(bind=True, max_retries=3, default_retry_delay=60, rate_limit="10/m")
    def compile_and_push_to_fuseki(
        self,
        rule_name: str,
        rule_text: str,
        source_hash: str,
        publisher_snapshot_hash: Optional[str] = None,
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
        assert_feature_flag_snapshot_match(publisher_snapshot_hash)

        try:
            task_log.info("fuseki_sync_start", rule_name=rule_name)

            rdf_triples = InferraToRdfCompiler.compile(rule_text, rule_name)
            unique_triple_count = len(set(rdf_triples))
            graph_uri = FusekiAdapter.rule_projection_graph_uri(rule_name)
            _fuseki_write_with_breaker(
                rdf_triples,
                version=source_hash,
                graph_uri=graph_uri,
            )
            stored_triple_count = FusekiAdapter.get_named_graph_triple_count(graph_uri)
            record_projection_metadata(
                rule_name,
                {
                    "source_hash": source_hash,
                    "compiled_triple_count": unique_triple_count,
                    "stored_triple_count": stored_triple_count,
                    "sync_status": (
                        "current"
                        if stored_triple_count == unique_triple_count
                        else "stale"
                    ),
                    "graph_uri": graph_uri,
                    "job_id": self.request.id,
                    "dead_letter_visible": False,
                },
            )

            if source_hash in _inflight_tasks:
                del _inflight_tasks[source_hash]

            task_log.info("fuseki_sync_success", rule_name=rule_name)
            return {
                "status": "success",
                "rule": rule_name,
                "hash": source_hash,
                "compiler_version": COMPILER_VERSION,
                "compiled_triple_count": unique_triple_count,
                "stored_triple_count": stored_triple_count,
                "graph_uri": graph_uri,
            }

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


def _fuseki_write_with_breaker(
    rdf_triples,
    version: str,
    graph_uri: Optional[str] = None,
) -> None:
    """
    Write RDF triples to Fuseki with circuit breaker protection.

    After 5 consecutive failures, opens the circuit for 60s to prevent
    overwhelming an unavailable Fuseki.
    """
    try:
        from circuitbreaker import circuit

        @circuit(failure_threshold=5, recovery_timeout=60)
        def _write_with_protection():
            _write_fuseki_projection(rdf_triples, version=version, graph_uri=graph_uri)

        _write_with_protection()

    except ImportError:
        import structlog

        fallback_log = structlog.get_logger()
        fallback_log.debug("circuitbreaker_not_installed_fusing_direct_write")

        _write_fuseki_projection(rdf_triples, version=version, graph_uri=graph_uri)


def _write_fuseki_projection(
    rdf_triples,
    version: str,
    graph_uri: Optional[str] = None,
) -> None:
    if graph_uri is None:
        FusekiAdapter.execute_sparql_idempotent_insert(rdf_triples, version=version)
        return
    FusekiAdapter.execute_sparql_idempotent_insert(
        rdf_triples,
        version=version,
        graph_uri=graph_uri,
    )


def _projection_metadata_key(rule_name: str) -> str:
    digest = sha256(rule_name.encode("utf-8")).hexdigest()[:24]
    return f"{PROJECTION_METADATA_KEY_PREFIX}:{digest}"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize_error_summary(error: str) -> str:
    summary = " ".join(str(error).split())
    return summary[:300]
