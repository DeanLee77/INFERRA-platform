import asyncio
import json
from typing import Any, Iterable, Optional, Tuple

import structlog

from src.domain.fact_values import FactValue
from src.domain.state.fact_source import FactSource
from src.infrastructure.secrets import redis_client_from_env
from src.ports.fact_store_port import FactStorePort

log = structlog.get_logger(__name__)


class OntologyDeltaConsumer:
    """Inject ontology-derived deltas into the semantic fact layer."""

    def __init__(
        self,
        fact_store: FactStorePort,
        lock: Optional[asyncio.Lock] = None,
    ) -> None:
        self._store = fact_store
        self._lock = lock or asyncio.Lock()

    async def on_ontology_delta(
        self,
        session_id: str,
        delta_facts: Iterable[Tuple[str, Any]],
    ) -> int:
        injected = 0
        async with self._lock:
            for name, value in delta_facts:
                fact_name = str(name).strip()
                if not fact_name:
                    continue
                fact_value = value if isinstance(value, FactValue) else FactValue(value)
                self._store.set_fact(fact_name, fact_value, source=FactSource.SEMANTIC)
                injected += 1
        log.info(
            "ontology_delta_injected",
            session_id=session_id,
            node_id="",
            fact_source=FactSource.SEMANTIC.value,
            correlation_id=session_id,
            delta_count=injected,
        )
        return injected

    async def poll_deltas(self, session_id: str) -> int:
        key = f"inferra:ontology_deltas:{session_id}"
        try:
            client = redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)
            raw_events = client.lrange(key, 0, -1)
        except Exception:
            log.warning(
                "ontology_delta_poll_failed",
                session_id=session_id,
                node_id="",
                fact_source=FactSource.SEMANTIC.value,
                correlation_id=session_id,
                exc_info=True,
            )
            return 0

        injected = 0
        for raw_event in raw_events:
            event = self._decode_event(raw_event)
            delta_facts = event.get("deltas", []) if isinstance(event, dict) else []
            injected += await self.on_ontology_delta(session_id, delta_facts)

        if raw_events:
            try:
                redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0).delete(key)
            except Exception:
                log.warning(
                    "ontology_delta_cleanup_failed",
                    session_id=session_id,
                    node_id="",
                    fact_source=FactSource.SEMANTIC.value,
                    correlation_id=session_id,
                    exc_info=True,
                )
        return injected

    @staticmethod
    def _decode_event(raw_event: Any) -> dict:
        if isinstance(raw_event, bytes):
            raw_event = raw_event.decode("utf-8")
        try:
            payload = json.loads(raw_event)
        except (TypeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
