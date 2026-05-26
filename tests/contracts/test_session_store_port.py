from dataclasses import dataclass
from typing import Callable

import pytest

from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.adapters.outbound.session.redis_session_store import RedisSessionStore
from src.domain.exceptions import ConcurrentModificationError
from src.domain.inference.assessment import Assessment
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.session import InferenceSession
from src.ports.session_store_port import SessionStorePort


@dataclass
class _FakeRedis:
    values: dict
    expiry: dict

    def ping(self):
        return True

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.expiry[key] = ex
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.expiry.pop(key, None)
        return 1 if existed else 0

    def exists(self, key):
        return 1 if key in self.values else 0

    def scan_iter(self, match):
        prefix = match[:-1]
        for key in list(self.values):
            if key.startswith(prefix):
                yield key


def _session(session_id: str = "contract-s1", version: int = 0) -> InferenceSession:
    return InferenceSession(
        session_id=session_id,
        rule_name="rule",
        target_node_name="goal",
        inference_engine=InferenceEngine(),
        assessment=Assessment(),
        version=version,
    )


def _in_memory_store() -> SessionStorePort:
    return InMemorySessionStore()


def _redis_store() -> SessionStorePort:
    return RedisSessionStore(
        redis_client=_FakeRedis(values={}, expiry={}),
        namespace="contract:sessions",
        ttl_seconds=60,
    )


@pytest.mark.parametrize("store_factory", [_in_memory_store, _redis_store])
class TestSessionStorePortContract:
    def test_lifecycle(self, store_factory: Callable[[], SessionStorePort]):
        store = store_factory()
        session = _session()

        store.save(session)

        assert store.exists(session.session_id) is True
        assert session.session_id in store.list_sessions()
        loaded = store.get(session.session_id)
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert store.delete(session.session_id) is True
        assert store.get(session.session_id) is None

    def test_stale_update_is_rejected(self, store_factory: Callable[[], SessionStorePort]):
        store = store_factory()
        session = _session()
        store.save(session)

        fresh = store.get(session.session_id)
        stale = _session(session.session_id, version=fresh.version)

        store.save(fresh)

        with pytest.raises(ConcurrentModificationError):
            store.save(stale)

    def test_clear_all_removes_sessions(self, store_factory: Callable[[], SessionStorePort]):
        store = store_factory()
        store.save(_session("a"))
        store.save(_session("b"))

        store.clear_all()

        assert store.list_sessions() == []
