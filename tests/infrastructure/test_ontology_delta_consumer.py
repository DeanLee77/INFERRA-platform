import asyncio
import types

from src.domain.fact_values import FactValue
from src.domain.state import FactSource, LayeredFactStore
from src.infrastructure.ontology_delta_consumer import OntologyDeltaConsumer


def test_ontology_delta_consumer_injects_semantic_facts():
    store = LayeredFactStore()
    consumer = OntologyDeltaConsumer(store)

    injected = asyncio.run(
        consumer.on_ontology_delta(
            "s1",
            [("semantic_fact", "yes"), ("typed_fact", FactValue(True)), ("", "ignored")],
        )
    )

    assert injected == 2
    assert store.peek_in_layer("semantic_fact", FactSource.SEMANTIC).get_value() == "yes"
    assert store.peek_in_layer("typed_fact", FactSource.SEMANTIC).get_value() is True


def test_ontology_delta_decode_handles_invalid_events():
    assert OntologyDeltaConsumer._decode_event(b'{"deltas":[["a","b"]]}') == {
        "deltas": [["a", "b"]]
    }
    assert OntologyDeltaConsumer._decode_event("not json") == {}
    assert OntologyDeltaConsumer._decode_event(None) == {}


def test_ontology_delta_consumer_polls_redis_queue(monkeypatch):
    store = LayeredFactStore()
    fake_redis = types.SimpleNamespace(
        lrange=lambda key, start, end: [
            b'{"deltas":[["semantic_fact","yes"]]}',
            '{"deltas":[["typed_fact", true]]}',
            "not json",
        ],
        delete_calls=[],
    )

    def delete(key):
        fake_redis.delete_calls.append(key)

    fake_redis.delete = delete
    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda _url: fake_redis)),
    )

    injected = asyncio.run(OntologyDeltaConsumer(store).poll_deltas("s1"))

    assert injected == 2
    assert fake_redis.delete_calls == ["inferra:ontology_deltas:s1"]
    assert store.peek_in_layer("semantic_fact", FactSource.SEMANTIC).get_value() == "yes"
    assert store.peek_in_layer("typed_fact", FactSource.SEMANTIC).get_value() is True


def test_ontology_delta_consumer_poll_handles_redis_failure(monkeypatch):
    class RedisFactory:
        @staticmethod
        def from_url(_url):
            raise RuntimeError("redis down")

    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        types.SimpleNamespace(Redis=RedisFactory),
    )

    injected = asyncio.run(OntologyDeltaConsumer(LayeredFactStore()).poll_deltas("s1"))

    assert injected == 0


def test_ontology_delta_consumer_cleanup_failure_does_not_lose_injection(monkeypatch):
    store = LayeredFactStore()

    class FakeRedis:
        def __init__(self):
            self.calls = 0

        def lrange(self, *_args):
            return [b'{"deltas":[["semantic_fact","yes"]]}']

        def delete(self, *_args):
            raise RuntimeError("cleanup down")

    fake = FakeRedis()
    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda _url: fake)),
    )

    injected = asyncio.run(OntologyDeltaConsumer(store).poll_deltas("s1"))

    assert injected == 1
    assert store.peek_in_layer("semantic_fact", FactSource.SEMANTIC).get_value() == "yes"
