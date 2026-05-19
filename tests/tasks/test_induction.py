import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.tasks.induction import (
    InductionCircuitBreaker,
    InductionCircuitOpenError,
    build_induction_source_hash,
    mine_candidate_rules,
    publish_induction_dead_letter,
    run_induction_batch,
)
from src.tasks.event_publisher import on_rule_updated


def test_mine_candidate_rules_returns_empty_for_no_sessions():
    assert mine_candidate_rules([], "rule") == []


def test_mine_candidate_rules_sanitizes_rule_name_and_is_deterministic():
    first = mine_candidate_rules(["s2", "s1"], "benefit rule!")
    second = mine_candidate_rules(["s1", "s2"], "benefit rule!")

    assert first == second
    assert first[0].startswith("INPUT trace_pattern_")
    assert "benefit_rule__learned_" in first[0]


def test_mine_candidate_rules_uses_default_rule_name_when_sanitized_name_empty():
    result = mine_candidate_rules(["s1"], "")

    assert "_learned_" in result[0]
    assert "rule_learned_" in result[0]


def test_mine_candidate_rules_uses_session_data_pipeline_when_available():
    sessions = [
        {"session_id": "s1", "working_memory": {"eligible": True, "income": True}},
        {"session_id": "s2", "working_memory": {"eligible": True, "income": True}},
        {"session_id": "s3", "working_memory": {"eligible": False, "income": False}},
    ]

    result = mine_candidate_rules(["s1", "s2", "s3"], "benefit rule", session_data_list=sessions)

    assert result
    assert any("eligible IS true" in rule for rule in result)
    assert all("trace_pattern_" not in rule for rule in result)


def test_build_induction_source_hash_is_order_independent():
    first = build_induction_source_hash(["s2", "s1"], "rule")
    second = build_induction_source_hash(["s1", "s2"], "rule")

    assert first == second


def test_induction_circuit_breaker_opens_and_recovers(monkeypatch):
    breaker = InductionCircuitBreaker(failure_threshold=2, recovery_timeout=10)
    breaker.record_failure()
    breaker.before_call()
    breaker.record_failure()

    with pytest.raises(InductionCircuitOpenError):
        breaker.before_call()

    monkeypatch.setattr("src.tasks.induction.time.monotonic", lambda: breaker.opened_at + 11)
    breaker.before_call()
    assert breaker.is_open() is False


def test_on_rule_updated_delegates_to_rule_sync_publisher():
    flags = object()
    with patch("src.tasks.event_publisher.publish_rule_updated_event", return_value="task-1") as publisher:
        assert on_rule_updated("rule", "text", flags) == "task-1"

    publisher.assert_called_once_with("rule", "text", flags)


def test_publish_induction_dead_letter_pushes_payload_to_redis():
    mock_redis_module = MagicMock()
    mock_client = MagicMock()
    mock_redis_module.Redis.from_url.return_value = mock_client

    with patch.dict(sys.modules, {"redis": mock_redis_module}):
        publish_induction_dead_letter("job1", "rule1", "boom")

    queue_name, payload = mock_client.lpush.call_args.args
    assert queue_name == "inferra:induction:dead_letter_queue"
    decoded = json.loads(payload)
    assert decoded["job_id"] == "job1"
    assert decoded["rule_name"] == "rule1"
    assert decoded["error"] == "boom"


def test_publish_induction_dead_letter_handles_redis_failure():
    mock_redis_module = MagicMock()
    mock_redis_module.Redis.from_url.side_effect = Exception("redis down")

    with patch.dict(sys.modules, {"redis": mock_redis_module}):
        publish_induction_dead_letter("job1", "rule1", "boom")


@pytest.mark.skipif(not hasattr(run_induction_batch, "run"), reason="Celery task is unavailable")
class TestRunInductionBatch:
    def test_run_induction_batch_filters_candidates(self):
        run_induction_batch.push_request(id="job1", retries=0)
        try:
            with patch("src.services.rule_sandbox.RuleSandbox.filter_valid_candidates", return_value=(["rule text"], [])) as filter_candidates:
                result = run_induction_batch.run(["s1"], "rule1")
        finally:
            run_induction_batch.pop_request()

        filter_candidates.assert_called_once()
        assert result == {
            "job_id": "job1",
            "status": "completed",
            "rule_name": "rule1",
            "candidate_rules": ["rule text"],
            "errors": [],
        }

    def test_run_induction_batch_retries_before_dead_letter(self):
        run_induction_batch.push_request(id="job1", retries=0)
        try:
            with patch("src.services.rule_sandbox.RuleSandbox.filter_valid_candidates", side_effect=Exception("sandbox down")):
                with patch.object(run_induction_batch, "retry", side_effect=RuntimeError("retry requested")):
                    with pytest.raises(RuntimeError, match="retry requested"):
                        run_induction_batch.run(["s1"], "rule1")
        finally:
            run_induction_batch.pop_request()

    def test_run_induction_batch_dead_letters_after_final_retry(self):
        run_induction_batch.push_request(id="job1", retries=3)
        try:
            with patch("src.services.rule_sandbox.RuleSandbox.filter_valid_candidates", side_effect=Exception("sandbox down")):
                with patch("src.tasks.induction.publish_induction_dead_letter") as dlq:
                    with pytest.raises(Exception, match="sandbox down"):
                        run_induction_batch.run(["s1"], "rule1")
        finally:
            run_induction_batch.pop_request()

        dlq.assert_called_once_with("job1", "rule1", "sandbox down")
