from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.outbound.session.redis_session_store import RedisSessionStore
from src.domain.exceptions import ConcurrentModificationError
from src.domain.inference.assessment import Assessment
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.session import InferenceSession


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expiry = {}

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

    def lock(self, *_args, **_kwargs):
        class _Lock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Lock()


@pytest.fixture
def sample_session():
    return InferenceSession(
        session_id="s1",
        rule_name="rule",
        target_node_name="goal",
        inference_engine=InferenceEngine(),
        assessment=Assessment(),
    )


def test_redis_session_store_save_get_delete(sample_session):
    client = FakeRedis()
    store = RedisSessionStore(
        redis_client=client,
        namespace="test:sessions",
        ttl_seconds=60,
    )

    store.save(sample_session)

    assert store.exists("s1") is True
    assert store.list_sessions() == ["s1"]
    restored = store.get("s1")
    assert restored is not None
    assert restored.session_id == "s1"
    assert restored.rule_name == "rule"
    assert client.expiry["test:sessions:s1"] == 60
    assert store.delete("s1") is True
    assert store.get("s1") is None


def test_redis_session_store_clear_expired(sample_session):
    client = FakeRedis()
    store = RedisSessionStore(redis_client=client, namespace="test:sessions")
    sample_session.last_accessed = datetime.utcnow() - timedelta(hours=2)
    store.save(sample_session)

    assert store.clear_expired(3600) == 1
    assert store.exists("s1") is False


def test_redis_session_store_removes_corrupt_payload():
    client = FakeRedis()
    store = RedisSessionStore(redis_client=client, namespace="test:sessions")
    client.set("test:sessions:bad", b"not pickle")

    assert store.get("bad") is None
    assert store.exists("bad") is False


def test_redis_session_store_rejects_stale_update(sample_session):
    client = FakeRedis()
    store = RedisSessionStore(redis_client=client, namespace="test:sessions")
    store.save(sample_session)

    first_copy = store.get("s1")
    second_copy = store.get("s1")

    assert first_copy is not None
    assert second_copy is not None
    assert first_copy.version == second_copy.version == 0

    store.save(first_copy)
    assert first_copy.version == 1

    with pytest.raises(ConcurrentModificationError):
        store.save(second_copy)


def test_redis_session_store_rejects_invalid_session():
    store = RedisSessionStore(redis_client=FakeRedis(), namespace="test:sessions")

    with pytest.raises(ValueError, match="valid session_id"):
        store.save(None)


def test_redis_session_store_clear_expired_deletes_corrupt_payload():
    client = FakeRedis()
    store = RedisSessionStore(redis_client=client, namespace="test:sessions")
    client.set("test:sessions:bad", b"not pickle")

    assert store.clear_expired(3600) == 1


def test_redis_session_store_clear_expired_skips_missing_payload(sample_session):
    class MissingPayloadRedis(FakeRedis):
        def scan_iter(self, match):
            yield "test:sessions:missing"

        def get(self, key):
            return None

    store = RedisSessionStore(redis_client=MissingPayloadRedis(), namespace="test:sessions")

    assert store.clear_expired(3600) == 0


def test_redis_session_store_clear_all_deletes_all_keys(sample_session):
    client = FakeRedis()
    store = RedisSessionStore(redis_client=client, namespace="test:sessions")
    store.save(sample_session)

    store.clear_all()

    assert store.list_sessions() == []


def test_redis_session_store_decodes_rejects_invalid_envelopes(sample_session):
    store = RedisSessionStore(redis_client=FakeRedis(), namespace="test:sessions")

    with pytest.raises(ValueError, match="Unsupported"):
        store._decode(__import__("pickle").dumps({"version": 999, "session": sample_session}))

    with pytest.raises(ValueError, match="InferenceSession"):
        store._decode(__import__("pickle").dumps({"version": store.ENVELOPE_VERSION, "session": object()}))


def test_redis_session_store_builds_client_from_url(sample_session):
    fake_redis_module = MagicMock()
    fake_client = FakeRedis()
    fake_redis_module.Redis.from_url.return_value = fake_client

    with patch.dict("sys.modules", {"redis": fake_redis_module}):
        store = RedisSessionStore(redis_url="redis://example/0", namespace="test:sessions")

    fake_redis_module.Redis.from_url.assert_called_once_with("redis://example/0")
    assert store.exists("missing") is False


@pytest.mark.integration
def test_redis_session_store_live_round_trip():
    redis = pytest.importorskip("redis")
    client = redis.Redis.from_url("redis://localhost:6379/0")
    try:
        client.ping()
    except Exception as exc:
        pytest.skip(f"Redis is not available: {exc}")

    store = RedisSessionStore(
        redis_client=client,
        namespace="inferra:test:sessions",
        ttl_seconds=60,
    )
    store.clear_all()
    session = InferenceSession(
        session_id="live-s1",
        rule_name="rule",
        target_node_name="goal",
        inference_engine=InferenceEngine(),
        assessment=Assessment(),
    )

    store.save(session)
    restored = store.get("live-s1")

    assert restored is not None
    assert restored.session_id == "live-s1"
    assert store.count() == 1
    store.clear_all()
