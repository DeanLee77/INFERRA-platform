"""Async ontology post-reasoning task.

The current platform keeps rule execution graph-first and treats Fuseki as an
outbound semantic projection. This task publishes concluded facts as RDF
evidence and emits ontology-delta events that can be consumed into the
``FactSource.SEMANTIC`` layer by ``OntologyDeltaConsumer``.
"""

import hashlib
import json
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import structlog

from src.adapters.outbound.ontology.fuseki_adapter import INF_NS, FusekiAdapter
from src.domain.fact_values import FactValue
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.convergence_metrics import convergence_metrics
from src.infrastructure.secrets import redis_client_from_env
from src.tasks.celery_app import CELERY_AVAILABLE

log = structlog.get_logger(__name__)

DeltaFact = Tuple[str, Any]


def run_post_reasoning(
    session_id: str,
    rule_name: str,
    concluded_facts: Iterable[Mapping[str, Any] | Tuple[str, Any]],
    feature_flags: Optional[FeatureFlags] = None,
) -> Optional[Dict[str, str]]:
    """Publish ontology post-reasoning work if the feature flag is enabled."""
    flags = feature_flags if feature_flags is not None else FeatureFlags()
    if not flags.async_post_reasoning:
        log.debug(
            "async_post_reasoning_disabled",
            session_id=session_id,
            node_id="",
            fact_source="SEMANTIC",
            correlation_id=session_id,
            rule_name=rule_name,
        )
        return None

    if not CELERY_AVAILABLE or _ontology_post_reasoner_task is None:
        log.warning(
            "celery_not_available_post_reasoning",
            session_id=session_id,
            node_id="",
            fact_source="SEMANTIC",
            correlation_id=session_id,
            rule_name=rule_name,
        )
        return None

    facts_payload = _json_ready_facts(concluded_facts)
    result = _ontology_post_reasoner_task.delay(session_id, rule_name, facts_payload)
    log.info(
        "post_reasoning_task_published",
        session_id=session_id,
        node_id="",
        fact_source="SEMANTIC",
        correlation_id=session_id,
        rule_name=rule_name,
        task_id=result.id,
    )
    return {"task_id": result.id, "session_id": session_id}


def execute_post_reasoning(
    session_id: str,
    rule_name: str,
    concluded_facts: Iterable[Mapping[str, Any] | Tuple[str, Any]],
) -> Dict[str, Any]:
    """Run post-reasoning synchronously; used by the Celery task and tests."""
    delta_facts = build_concluded_fact_deltas(concluded_facts)
    source_hash = _source_hash(session_id, rule_name, delta_facts)

    triples = build_conclusion_triples(session_id, rule_name, delta_facts)
    if triples:
        FusekiAdapter.execute_sparql_idempotent_insert(
            triples,
            version=source_hash,
            graph_uri=f"{INF_NS}post_reasoning/{source_hash}",
        )

    if delta_facts:
        publish_ontology_delta_event(session_id, delta_facts)

    convergence_metrics.record_ontology_delta(session_id, len(delta_facts))
    log.info(
        "post_reasoning_success",
        session_id=session_id,
        node_id="",
        fact_source="SEMANTIC",
        correlation_id=session_id,
        rule_name=rule_name,
        delta_count=len(delta_facts),
        triple_count=len(triples),
    )
    return {
        "status": "success",
        "session_id": session_id,
        "rule_name": rule_name,
        "delta_count": len(delta_facts),
        "triple_count": len(triples),
        "source_hash": source_hash,
    }


def build_concluded_fact_deltas(
    concluded_facts: Iterable[Mapping[str, Any] | Tuple[str, Any]],
) -> Tuple[DeltaFact, ...]:
    """Normalize concluded facts into Redis/Fuseki-friendly ``(name, value)`` pairs."""
    deltas: List[DeltaFact] = []
    seen: set[str] = set()
    for item in concluded_facts:
        name, value = _fact_name_value(item)
        fact_name = str(name).strip()
        if not fact_name or fact_name in seen:
            continue
        seen.add(fact_name)
        deltas.append((fact_name, _primitive_value(value)))
    return tuple(deltas)


def build_conclusion_triples(
    session_id: str,
    rule_name: str,
    delta_facts: Iterable[DeltaFact],
) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    session_uri = f"{INF_NS}session/{_sanitize_uri(session_id)}"
    rule_uri = f"{INF_NS}rule/{_sanitize_uri(rule_name)}"
    for fact_name, value in delta_facts:
        fact_uri = f"{session_uri}/fact/{_sanitize_uri(fact_name)}"
        triples.extend([
            (fact_uri, f"{INF_NS}session", session_uri),
            (fact_uri, f"{INF_NS}rule", rule_uri),
            (fact_uri, f"{INF_NS}name", fact_name),
            (fact_uri, f"{INF_NS}value", str(value)),
        ])
    return triples


def publish_ontology_delta_event(
    session_id: str,
    delta_facts: Iterable[DeltaFact],
    redis_client: Any = None,
) -> bool:
    payload = {
        "session_id": session_id,
        "deltas": [(name, _primitive_value(value)) for name, value in delta_facts],
        "timestamp": time.time(),
    }
    try:
        client = redis_client
        if client is None:
            client = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
        client.rpush(f"inferra:ontology_deltas:{session_id}", json.dumps(payload))
        log.info(
            "ontology_delta_event_published",
            session_id=session_id,
            node_id="",
            fact_source="SEMANTIC",
            correlation_id=session_id,
            delta_count=len(payload["deltas"]),
        )
        return True
    except Exception:
        log.error(
            "ontology_delta_event_publish_failed",
            session_id=session_id,
            node_id="",
            fact_source="SEMANTIC",
            correlation_id=session_id,
            exc_info=True,
        )
        return False


def publish_dead_letter_event(
    session_id: str,
    rule_name: str,
    concluded_facts: Iterable[Mapping[str, Any] | Tuple[str, Any]],
    error: str,
    redis_client: Any = None,
) -> bool:
    payload = {
        "session_id": session_id,
        "rule_name": rule_name,
        "snapshot_preview": json.dumps(_json_ready_facts(concluded_facts))[:500],
        "error": error,
        "timestamp": time.time(),
    }
    try:
        client = redis_client
        if client is None:
            client = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
        client.lpush("inferra:ontology_post_reasoning_dead_letter", json.dumps(payload))
        log.error(
            "ontology_post_reasoning_dead_letter_published",
            session_id=session_id,
            node_id="",
            fact_source="SEMANTIC",
            correlation_id=session_id,
            rule_name=rule_name,
            error=error,
        )
        return True
    except Exception:
        log.error(
            "ontology_post_reasoning_dead_letter_publish_failed",
            session_id=session_id,
            node_id="",
            fact_source="SEMANTIC",
            correlation_id=session_id,
            rule_name=rule_name,
            exc_info=True,
        )
        return False


def _json_ready_facts(
    concluded_facts: Iterable[Mapping[str, Any] | Tuple[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        {"name": name, "value": _primitive_value(value)}
        for name, value in build_concluded_fact_deltas(concluded_facts)
    ]


def _fact_name_value(item: Mapping[str, Any] | Tuple[str, Any]) -> Tuple[str, Any]:
    if isinstance(item, Mapping):
        return str(item.get("name", item.get("fact_name", ""))), item.get("value")
    if isinstance(item, tuple) and len(item) >= 2:
        return str(item[0]), item[1]
    return "", None


def _primitive_value(value: Any) -> Any:
    if isinstance(value, FactValue):
        return _primitive_value(value.get_value())
    if isinstance(value, list):
        return [_primitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_primitive_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _primitive_value(val) for key, val in value.items()}
    return value


def _source_hash(session_id: str, rule_name: str, delta_facts: Iterable[DeltaFact]) -> str:
    payload = json.dumps(
        {
            "session_id": session_id,
            "rule_name": rule_name,
            "deltas": [(name, _primitive_value(value)) for name, value in delta_facts],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sanitize_uri(value: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(value))


_ontology_post_reasoner_task = None

if CELERY_AVAILABLE:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3, default_retry_delay=30, rate_limit="10/m")
    def _ontology_post_reasoner_task(
        self,
        session_id: str,
        rule_name: str,
        concluded_facts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            task_id=self.request.id,
            session_id=session_id,
            rule_name=rule_name,
            fact_source="SEMANTIC",
            correlation_id=session_id,
        )
        try:
            return execute_post_reasoning(session_id, rule_name, concluded_facts)
        except Exception as exc:
            log.warning(
                "post_reasoning_failed",
                session_id=session_id,
                node_id="",
                fact_source="SEMANTIC",
                correlation_id=session_id,
                rule_name=rule_name,
                retry=self.request.retries,
                error=str(exc),
            )
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            publish_dead_letter_event(session_id, rule_name, concluded_facts, str(exc))
            raise
