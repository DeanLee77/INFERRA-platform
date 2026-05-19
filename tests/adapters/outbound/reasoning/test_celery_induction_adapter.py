from unittest.mock import MagicMock, patch

from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.ports.induction_port import InductionPort
from src.tasks.induction import mine_candidate_rules


def test_celery_induction_adapter_start_batch():
    CeleryInductionAdapter.clear_idempotency_cache()
    adapter = CeleryInductionAdapter()
    with patch("src.tasks.induction.run_induction_batch") as task:
        task.delay.return_value = MagicMock(id="job-1")

        result = adapter.start_batch(["s1"], "rule")

    assert isinstance(adapter, InductionPort)
    assert result == {"job_id": "job-1", "status": "submitted", "rule_name": "rule"}


def test_celery_induction_adapter_start_batch_is_idempotent():
    CeleryInductionAdapter.clear_idempotency_cache()
    adapter = CeleryInductionAdapter()
    with patch("src.tasks.induction.run_induction_batch") as task:
        task.delay.return_value = MagicMock(id="job-1")

        first = adapter.start_batch(["s2", "s1"], "rule")
        second = adapter.start_batch(["s1", "s2"], "rule")

    assert first == second
    task.delay.assert_called_once_with(["s2", "s1"], "rule")


def test_celery_induction_adapter_get_status_success():
    adapter = CeleryInductionAdapter()
    fake_result = MagicMock()
    fake_result.status = "SUCCESS"
    fake_result.successful.return_value = True
    fake_result.failed.return_value = False
    fake_result.result = {
        "job_id": "job-1",
        "status": "completed",
        "candidate_rules": ["A IS TRUE IF B"],
    }

    with patch("celery.result.AsyncResult", return_value=fake_result):
        result = adapter.get_status("job-1")

    assert result["status"] == "completed"
    assert result["candidate_rules"] == ["A IS TRUE IF B"]


def test_celery_induction_adapter_get_status_failed():
    adapter = CeleryInductionAdapter()
    fake_result = MagicMock()
    fake_result.status = "FAILURE"
    fake_result.successful.return_value = False
    fake_result.failed.return_value = True
    fake_result.result = RuntimeError("sandbox failed")

    with patch("celery.result.AsyncResult", return_value=fake_result):
        result = adapter.get_status("job-1")

    assert result["status"] == "failure"
    assert result["errors"] == ["sandbox failed"]


def test_celery_induction_adapter_promote_rejects_unknown_candidate():
    adapter = CeleryInductionAdapter()
    with patch.object(adapter, "get_status", return_value={"candidate_rules": ["known"], "rule_name": "rule"}):
        result = adapter.promote("job-1", "unknown")

    assert result["status"] == "rejected"
    assert result["errors"] == ["Candidate rule does not belong to induction job"]


def test_celery_induction_adapter_promote_valid_candidate():
    adapter = CeleryInductionAdapter()
    promotion = MagicMock()
    promotion.to_dict.return_value = {"job_id": "job-1", "status": "promoted"}

    with patch.object(adapter, "get_status", return_value={"candidate_rules": ["known"], "rule_name": "rule"}):
        with patch("src.adapters.outbound.reasoning.celery_induction_adapter.RuleSandbox") as sandbox_cls:
            sandbox_cls.return_value.promote_candidate.return_value = promotion
            result = adapter.promote("job-1", "known")

    assert result == {"job_id": "job-1", "status": "promoted"}
    sandbox_cls.return_value.promote_candidate.assert_called_once_with(
        "job-1",
        "known",
        ["known"],
        "rule",
    )


def test_mine_candidate_rules_is_deterministic():
    first = mine_candidate_rules(["s2", "s1"], "rule name")
    second = mine_candidate_rules(["s1", "s2"], "rule name")

    assert first == second
    assert first[0].startswith("INPUT trace_pattern_")
    assert "rule_name_learned_" in first[0]
