"""
Tests for RuleUpdated event publisher and Celery task.

Tests are designed to run without Celery/Redis installed — they verify
the gating logic, idempotency, and flag behaviour.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.domain.state.feature_flags import FeatureFlags
from src.tasks.rule_sync import (
    _inflight_tasks,
    _is_task_pending,
    _fuseki_write_with_breaker,
    publish_dead_letter_event,
    publish_rule_updated_event,
)


class TestPublishRuleUpdatedEvent:
    def test_returns_none_when_async_sync_disabled(self):
        flags = FeatureFlags(async_sync_enabled=False)
        result = publish_rule_updated_event("rule1", "text", flags)
        assert result is None

    def test_returns_none_when_celery_unavailable(self):
        flags = FeatureFlags(async_sync_enabled=True)
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", False):
            result = publish_rule_updated_event("rule1", "text", flags)
            assert result is None

    def test_publishes_when_enabled_and_available(self):
        flags = FeatureFlags(async_sync_enabled=True)
        mock_task_func = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "task-123"
        mock_task_func.delay.return_value = mock_result

        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            with patch.dict(sys.modules, {"src.tasks.rule_sync": MagicMock(compile_and_push_to_fuseki=mock_task_func)}):
                with patch("src.tasks.rule_sync.compile_and_push_to_fuseki", mock_task_func, create=True):
                    pass

            with patch("src.tasks.rule_sync._is_task_pending", return_value=False):
                mock_app = MagicMock()
                mock_app.delay.return_value = mock_result
                with patch.dict("src.tasks.rule_sync.__dict__", {"compile_and_push_to_fuseki": mock_app}):
                    result = publish_rule_updated_event("rule1", "text", flags)
                    assert result == "task-123"
                    mock_app.delay.assert_called_once()

    def test_skips_duplicate_inflight_task(self):
        flags = FeatureFlags(async_sync_enabled=True)
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            with patch("src.tasks.rule_sync._is_task_pending", return_value=True):
                result = publish_rule_updated_event("rule1", "text", flags)
                assert result is None

    def test_uses_default_flags_when_none(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", False):
            result = publish_rule_updated_event("rule1", "text", None)
            assert result is None

    def test_computes_source_hash(self):
        import hashlib

        flags = FeatureFlags(async_sync_enabled=True)
        expected_hash = hashlib.sha256("text".encode()).hexdigest()
        mock_result = MagicMock()
        mock_result.id = "task-456"

        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            with patch("src.tasks.rule_sync._is_task_pending", return_value=False):
                mock_app = MagicMock()
                mock_app.delay.return_value = mock_result
                with patch.dict("src.tasks.rule_sync.__dict__", {"compile_and_push_to_fuseki": mock_app}):
                    publish_rule_updated_event("rule1", "text", flags)
                    call_args = mock_app.delay.call_args
                    assert call_args[0][2] == expected_hash

    def test_stores_inflight_task_id(self):
        flags = FeatureFlags(async_sync_enabled=True)
        mock_result = MagicMock()
        mock_result.id = "task-789"

        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            with patch("src.tasks.rule_sync._is_task_pending", return_value=False):
                mock_app = MagicMock()
                mock_app.delay.return_value = mock_result
                with patch.dict("src.tasks.rule_sync.__dict__", {"compile_and_push_to_fuseki": mock_app}):
                    _inflight_tasks.clear()
                    publish_rule_updated_event("rule1", "text", flags)
                    import hashlib
                    expected_hash = hashlib.sha256("text".encode()).hexdigest()
                    assert expected_hash in _inflight_tasks
                    assert _inflight_tasks[expected_hash] == "task-789"


class TestIsTaskPending:
    def test_returns_false_when_celery_unavailable(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", False):
            from src.tasks.rule_sync import _is_task_pending
            assert _is_task_pending("rule1", "hash1") is False

    def test_returns_false_when_no_inflight_task(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            _inflight_tasks.clear()
            from src.tasks.rule_sync import _is_task_pending
            assert _is_task_pending("rule1", "hash1") is False

    def test_returns_true_for_pending_task(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            _inflight_tasks["hash1"] = "task-id-1"
            mock_celery_result = MagicMock()
            mock_result = MagicMock()
            mock_result.status = "PENDING"
            mock_celery_result.AsyncResult.return_value = mock_result
            with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
                assert _is_task_pending("rule1", "hash1") is True

    def test_returns_false_for_completed_task(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            _inflight_tasks["hash1"] = "task-id-1"
            mock_celery_result = MagicMock()
            mock_result = MagicMock()
            mock_result.status = "SUCCESS"
            mock_celery_result.AsyncResult.return_value = mock_result
            with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
                assert _is_task_pending("rule1", "hash1") is False
                assert "hash1" not in _inflight_tasks

    def test_returns_false_when_status_lookup_fails(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            _inflight_tasks["hash1"] = "task-id-1"
            mock_celery_result = MagicMock()
            mock_celery_result.AsyncResult.side_effect = Exception("backend down")
            with patch.dict(sys.modules, {"celery.result": mock_celery_result}):
                assert _is_task_pending("rule1", "hash1") is False


class TestPublishDeadLetterEvent:
    def test_pushes_json_payload_to_redis(self):
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_redis_module.Redis.from_url.return_value = mock_client

        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            publish_dead_letter_event("rule1", "text", "hash1", "test error")

        queue_name, payload = mock_client.lpush.call_args.args
        assert queue_name == "inferra:dead_letter_queue"
        decoded = json.loads(payload)
        assert decoded["rule_name"] == "rule1"
        assert decoded["source_hash"] == "hash1"
        assert decoded["error"] == "test error"

    def test_handles_redis_unavailable(self):
        mock_redis_module = MagicMock()
        mock_redis_module.Redis.from_url.side_effect = Exception("Connection refused")
        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            publish_dead_letter_event("rule1", "text", "hash1", "test error")

    def test_dead_letter_event_callable(self):
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", False):
            assert callable(publish_dead_letter_event)


class TestFusekiWriteWithBreaker:
    def test_direct_write_when_circuitbreaker_missing(self):
        with patch.dict(sys.modules, {"circuitbreaker": None}):
            with patch("src.adapters.outbound.ontology.fuseki_adapter.FusekiAdapter.execute_sparql_idempotent_insert") as insert:
                _fuseki_write_with_breaker([("s", "p", "o")], version="hash1")

        insert.assert_called_once_with([("s", "p", "o")], version="hash1")

    def test_uses_circuitbreaker_when_available(self):
        mock_circuitbreaker = MagicMock()

        def circuit(**_kwargs):
            def decorator(func):
                def wrapper():
                    return func()
                return wrapper
            return decorator

        mock_circuitbreaker.circuit.side_effect = circuit
        with patch.dict(sys.modules, {"circuitbreaker": mock_circuitbreaker}):
            with patch("src.adapters.outbound.ontology.fuseki_adapter.FusekiAdapter.execute_sparql_idempotent_insert") as insert:
                _fuseki_write_with_breaker([("s", "p", "o")], version="hash1")

        insert.assert_called_once_with([("s", "p", "o")], version="hash1")


@pytest.mark.skipif(
    not hasattr(sys.modules.get("src.tasks.rule_sync"), "compile_and_push_to_fuseki"),
    reason="Celery task is unavailable",
)
class TestCompileAndPushToFusekiTask:
    def test_task_compiles_pushes_and_clears_inflight(self):
        from src.tasks import rule_sync

        _inflight_tasks["hash1"] = "task-id"
        rule_sync.compile_and_push_to_fuseki.push_request(id="task-id", retries=0)
        try:
            with patch("src.adapters.outbound.ontology.inferra_to_rdf_compiler.InferraToRdfCompiler.compile", return_value=[("s", "p", "o")]) as compile_rule:
                with patch("src.tasks.rule_sync._fuseki_write_with_breaker") as write:
                    result = rule_sync.compile_and_push_to_fuseki.run("rule1", "rule text", "hash1")
        finally:
            rule_sync.compile_and_push_to_fuseki.pop_request()

        compile_rule.assert_called_once_with("rule text", "rule1")
        write.assert_called_once_with([("s", "p", "o")], version="hash1")
        assert result == {"status": "success", "rule": "rule1", "hash": "hash1"}
        assert "hash1" not in _inflight_tasks

    def test_task_retries_before_dead_letter(self):
        from src.tasks import rule_sync

        rule_sync.compile_and_push_to_fuseki.push_request(id="task-id", retries=0)
        try:
            with patch("src.adapters.outbound.ontology.inferra_to_rdf_compiler.InferraToRdfCompiler.compile", side_effect=Exception("bad rule")):
                with patch.object(rule_sync.compile_and_push_to_fuseki, "retry", side_effect=RuntimeError("retry requested")):
                    with pytest.raises(RuntimeError, match="retry requested"):
                        rule_sync.compile_and_push_to_fuseki.run("rule1", "bad", "hash1")
        finally:
            rule_sync.compile_and_push_to_fuseki.pop_request()

    def test_task_publishes_dead_letter_after_final_retry(self):
        from src.tasks import rule_sync

        rule_sync.compile_and_push_to_fuseki.push_request(id="task-id", retries=3)
        try:
            with patch("src.adapters.outbound.ontology.inferra_to_rdf_compiler.InferraToRdfCompiler.compile", side_effect=Exception("bad rule")):
                with patch("src.tasks.rule_sync.publish_dead_letter_event") as dlq:
                    with pytest.raises(Exception, match="bad rule"):
                        rule_sync.compile_and_push_to_fuseki.run("rule1", "bad", "hash1")
        finally:
            rule_sync.compile_and_push_to_fuseki.pop_request()

        dlq.assert_called_once_with("rule1", "bad", "hash1", "bad rule")
