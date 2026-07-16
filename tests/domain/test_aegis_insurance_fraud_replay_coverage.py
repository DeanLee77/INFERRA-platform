"""Focused branch coverage for the synthetic insurance-fraud replay runtime."""

import json

import pytest

from src.domain.aegis.insurance_fraud_replay import (
    CASE_BY_RUN_ID,
    FRAUD_APPROVAL_ID,
    INSURANCE_DEFAULT_RUN_ID,
    InsuranceFraudEventSequenceError,
    InsuranceFraudReplayRuntime,
    _default_state_path,
)


@pytest.fixture
def runtime(tmp_path) -> InsuranceFraudReplayRuntime:
    return InsuranceFraudReplayRuntime(tmp_path / "insurance-replay-state.json")


def test_default_state_path_honours_environment(monkeypatch, tmp_path) -> None:
    configured_path = tmp_path / "configured-state.json"
    monkeypatch.setenv("AEGIS_INSURANCE_REPLAY_STATE_PATH", str(configured_path))

    assert _default_state_path() == configured_path


def test_invalid_persisted_snapshots_are_rejected(runtime) -> None:
    state_path = runtime._state_path

    state_path.write_text("{not-json", encoding="utf-8")
    assert runtime._load_state() is False

    state_path.write_text(
        json.dumps({"schemaVersion": 0, "runEvents": {}, "runCases": {}}),
        encoding="utf-8",
    )
    assert runtime._load_state() is False

    state_path.write_text(
        json.dumps({"schemaVersion": 1, "runEvents": [], "runCases": {}}),
        encoding="utf-8",
    )
    assert runtime._load_state() is False


def test_public_read_and_identifier_error_contracts(runtime) -> None:
    with pytest.raises(LookupError, match="Unknown AEGIS workflow"):
        runtime.get_workflow("unknown-workflow")
    with pytest.raises(LookupError, match="Unknown AEGIS workflow"):
        runtime.create_run({"workflowId": "unknown-workflow"})

    timeline = runtime.get_timeline(INSURANCE_DEFAULT_RUN_ID)
    options = runtime.get_options(INSURANCE_DEFAULT_RUN_ID)
    receipt = runtime.get_receipt(INSURANCE_DEFAULT_RUN_ID)

    assert timeline["runId"] == INSURANCE_DEFAULT_RUN_ID
    assert timeline["events"]
    assert options["recommendedOptionId"] == "escalate_fraud_review"
    assert receipt["receipt"]["runId"] == INSURANCE_DEFAULT_RUN_ID


def test_event_and_approval_validation_errors(runtime) -> None:
    run_id = INSURANCE_DEFAULT_RUN_ID

    with pytest.raises(ValueError, match="Event type is required"):
        runtime.append_event(run_id, {})
    with pytest.raises(ValueError, match="idempotencyKey is required"):
        runtime.append_event(run_id, {"type": "custom.event"})
    with pytest.raises(InsuranceFraudEventSequenceError, match="expected"):
        runtime.append_event(
            run_id,
            {
                "type": "custom.event",
                "idempotencyKey": "wrong-sequence",
                "sequence": 999,
            },
        )

    with pytest.raises(LookupError, match="Unknown approval"):
        runtime.decide_approval(run_id, "unknown-approval", {"decision": "granted"})
    with pytest.raises(ValueError, match="decision must be granted or rejected"):
        runtime.decide_approval(run_id, FRAUD_APPROVAL_ID, {"decision": "maybe"})


def test_transition_guards_append_auditable_denials(tmp_path) -> None:
    no_option_runtime = InsuranceFraudReplayRuntime(tmp_path / "no-option.json")
    with pytest.raises(InsuranceFraudEventSequenceError, match="no insurance fraud option"):
        no_option_runtime.transition(
            INSURANCE_DEFAULT_RUN_ID,
            {"idempotencyKey": "transition-without-option"},
        )
    assert no_option_runtime._events_for(INSURANCE_DEFAULT_RUN_ID)[-1]["type"] == (
        "transition.denied"
    )

    approval_runtime = InsuranceFraudReplayRuntime(tmp_path / "approval-missing.json")
    approval_runtime.select_option(
        INSURANCE_DEFAULT_RUN_ID,
        "escalate_fraud_review",
        {"idempotencyKey": "select-escalation"},
    )
    with pytest.raises(InsuranceFraudEventSequenceError, match="approval decision is missing"):
        approval_runtime.transition(
            INSURANCE_DEFAULT_RUN_ID,
            {"idempotencyKey": "transition-without-approval"},
        )
    assert approval_runtime._events_for(INSURANCE_DEFAULT_RUN_ID)[-1]["payload"] == {
        "deniedReason": "fraud lead approval decision is missing"
    }


def test_lazy_case_resolution_and_unknown_cases(runtime) -> None:
    available_run_ids = [
        run_id for run_id in CASE_BY_RUN_ID if run_id != INSURANCE_DEFAULT_RUN_ID
    ]
    event_seed_run, synced_case_run, local_case_run = available_run_ids[:3]

    assert runtime._events_for(event_seed_run)
    assert runtime._case_for_run(synced_case_run)["runId"] == synced_case_run
    assert runtime._case_for_run(local_case_run, sync=False)["runId"] == local_case_run

    with pytest.raises(LookupError, match="Unknown AEGIS workflow run"):
        runtime._events_for("unknown-run")
    with pytest.raises(LookupError, match="Unknown insurance replay run"):
        runtime._case_for_run("unknown-run", sync=False)
    with pytest.raises(LookupError, match="Unknown insurance replay branch"):
        runtime._case_from_request({"branchId": "unknown-branch"})

    known_case = runtime._case_from_request({"runId": event_seed_run})
    default_case = runtime._case_from_request({})
    assert known_case["runId"] == event_seed_run
    assert default_case["branchId"] == "escalate_fraud_review"


def test_unknown_option_and_terminal_type_are_rejected() -> None:
    with pytest.raises(LookupError, match="Unknown option"):
        InsuranceFraudReplayRuntime._option("unknown-option")
    with pytest.raises(LookupError, match="Unknown selected insurance option"):
        InsuranceFraudReplayRuntime._terminal_event_type("unknown-option", [])
