import json
import types
from unittest.mock import patch

from src.domain.fact_values import FactValue
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.convergence_metrics import convergence_metrics
import src.tasks.ontology_post_reasoner as post_reasoner
from src.tasks.ontology_post_reasoner import (
    build_concluded_fact_deltas,
    build_conclusion_triples,
    execute_post_reasoning,
    publish_dead_letter_event,
    publish_ontology_delta_event,
    run_post_reasoning,
)


class FakeRedis:
    def __init__(self):
        self.rpush_calls = []
        self.lpush_calls = []

    def rpush(self, key, payload):
        self.rpush_calls.append((key, payload))

    def lpush(self, key, payload):
        self.lpush_calls.append((key, payload))


def test_build_concluded_fact_deltas_unwraps_fact_values_and_dedupes():
    deltas = build_concluded_fact_deltas([
        {"name": "approved", "value": FactValue(True)},
        ("score", FactValue(42)),
        ("nested_list", [FactValue(1)]),
        ("nested_tuple", (FactValue(2),)),
        object(),
        {"name": "approved", "value": False},
        {"name": "", "value": "ignored"},
    ])

    assert deltas == (
        ("approved", True),
        ("score", 42),
        ("nested_list", [1]),
        ("nested_tuple", (2,)),
    )


def test_build_conclusion_triples_emits_four_triples_per_delta():
    triples = build_conclusion_triples("session 1", "rule 1", (("approved", True),))

    assert len(triples) == 4
    assert any(predicate.endswith("#value") and value == "True" for _, predicate, value in triples)


def test_publish_ontology_delta_event_pushes_consumer_payload():
    fake_redis = FakeRedis()

    assert publish_ontology_delta_event("s1", (("approved", True),), fake_redis) is True

    key, payload = fake_redis.rpush_calls[0]
    assert key == "inferra:ontology_deltas:s1"
    decoded = json.loads(payload)
    assert decoded["session_id"] == "s1"
    assert decoded["deltas"] == [["approved", True]]


def test_publish_dead_letter_event_uses_post_reasoning_queue():
    fake_redis = FakeRedis()

    assert publish_dead_letter_event("s1", "rule", [{"name": "x", "value": 1}], "boom", fake_redis) is True

    key, payload = fake_redis.lpush_calls[0]
    assert key == "inferra:ontology_post_reasoning_dead_letter"
    assert json.loads(payload)["error"] == "boom"


def test_run_post_reasoning_returns_none_when_disabled():
    result = run_post_reasoning(
        "s1",
        "rule",
        [{"name": "approved", "value": True}],
        FeatureFlags(async_post_reasoning=False),
    )

    assert result is None


def test_run_post_reasoning_returns_none_when_celery_unavailable(monkeypatch):
    monkeypatch.setattr(post_reasoner, "CELERY_AVAILABLE", False)
    monkeypatch.setattr(post_reasoner, "_ontology_post_reasoner_task", None)

    result = run_post_reasoning(
        "s1",
        "rule",
        [{"name": "approved", "value": True}],
        FeatureFlags(async_post_reasoning=True),
    )

    assert result is None


def test_run_post_reasoning_publishes_celery_payload(monkeypatch):
    class FakeAsyncResult:
        id = "task-1"

    class FakeTask:
        def __init__(self):
            self.calls = []

        def delay(self, *args):
            self.calls.append(args)
            return FakeAsyncResult()

    task = FakeTask()
    monkeypatch.setattr(post_reasoner, "CELERY_AVAILABLE", True)
    monkeypatch.setattr(post_reasoner, "_ontology_post_reasoner_task", task)

    result = run_post_reasoning(
        "s1",
        "rule",
        [{"name": "approved", "value": FactValue(True)}],
        FeatureFlags(async_post_reasoning=True),
    )

    assert result == {"task_id": "task-1", "session_id": "s1"}
    assert task.calls == [("s1", "rule", [{"name": "approved", "value": True}])]


def test_execute_post_reasoning_writes_fuseki_and_records_metrics():
    convergence_metrics.clear()

    with patch("src.tasks.ontology_post_reasoner.FusekiAdapter.execute_sparql_idempotent_insert") as write, \
            patch("src.tasks.ontology_post_reasoner.publish_ontology_delta_event", return_value=True) as publish:
        result = execute_post_reasoning("s1", "rule", [{"name": "approved", "value": True}])

    assert result["status"] == "success"
    assert result["delta_count"] == 1
    assert result["triple_count"] == 4
    write.assert_called_once()
    publish.assert_called_once_with("s1", (("approved", True),))
    assert convergence_metrics.get_metrics()["ontology_delta_counts"]["s1"] == 1


def test_execute_post_reasoning_handles_empty_delta_without_writes():
    convergence_metrics.clear()

    with patch("src.tasks.ontology_post_reasoner.FusekiAdapter.execute_sparql_idempotent_insert") as write, \
            patch("src.tasks.ontology_post_reasoner.publish_ontology_delta_event") as publish:
        result = execute_post_reasoning("s1", "rule", [{"name": "", "value": True}])

    assert result["delta_count"] == 0
    assert result["triple_count"] == 0
    write.assert_not_called()
    publish.assert_not_called()


def test_publish_events_return_false_on_redis_failure():
    class BrokenRedis:
        def rpush(self, *_args):
            raise RuntimeError("redis down")

        def lpush(self, *_args):
            raise RuntimeError("redis down")

    assert publish_ontology_delta_event("s1", (("approved", True),), BrokenRedis()) is False
    assert publish_dead_letter_event("s1", "rule", [{"name": "x", "value": 1}], "boom", BrokenRedis()) is False


def test_publish_events_create_default_redis_client(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setitem(
        __import__("sys").modules,
        "redis",
        types.SimpleNamespace(Redis=types.SimpleNamespace(from_url=lambda _url: fake)),
    )

    assert publish_ontology_delta_event("s1", (("approved", FactValue(True)),)) is True
    assert publish_dead_letter_event("s1", "rule", [{"fact_name": "x", "value": {"nested": FactValue(1)}}], "boom") is True
    assert fake.rpush_calls
    assert fake.lpush_calls


def test_celery_post_reasoner_task_success_when_available():
    task = post_reasoner._ontology_post_reasoner_task
    if task is None or not hasattr(task, "run"):
        return

    task.push_request(id="task-1", retries=0)
    try:
        with patch("src.tasks.ontology_post_reasoner.execute_post_reasoning", return_value={"status": "success"}) as execute:
            result = task.run("s1", "rule", [{"name": "x", "value": 1}])
    finally:
        task.pop_request()

    assert result == {"status": "success"}
    execute.assert_called_once()


def test_celery_post_reasoner_task_dead_letters_final_failure():
    task = post_reasoner._ontology_post_reasoner_task
    if task is None or not hasattr(task, "run"):
        return

    task.push_request(id="task-1", retries=3)
    try:
        with patch("src.tasks.ontology_post_reasoner.execute_post_reasoning", side_effect=RuntimeError("boom")), \
                patch("src.tasks.ontology_post_reasoner.publish_dead_letter_event", return_value=True) as publish:
            try:
                task.run("s1", "rule", [{"name": "x", "value": 1}])
            except RuntimeError:
                pass
            else:  # pragma: no cover
                raise AssertionError("task failure should be re-raised")
    finally:
        task.pop_request()

    publish.assert_called_once()
