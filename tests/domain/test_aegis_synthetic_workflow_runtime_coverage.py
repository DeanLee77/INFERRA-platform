from unittest.mock import MagicMock

import pytest

from src.domain.aegis.synthetic_workflow_runtime import (
    ROBOT_RUN_ID,
    ROBOT_WORKFLOW_ID,
    EventSequenceError,
    SyntheticAegisWorkflowRuntime,
    _condition_metadata,
)


@pytest.fixture
def runtime():
    return SyntheticAegisWorkflowRuntime()


def test_condition_metadata_includes_an_explicit_source():
    assert _condition_metadata("verified", source="unit-test") == {
        "condition": "verified",
        "source": "unit-test",
    }


def test_robot_workflow_catalog_validation_compile_and_unknown_identifier(runtime):
    catalog = runtime.list_workflows()
    workflow_ids = {workflow["id"] for workflow in catalog["workflows"]}
    assert ROBOT_WORKFLOW_ID in workflow_ids

    workflow = runtime.get_workflow(ROBOT_WORKFLOW_ID)
    assert workflow["domain"] == "robotics"

    validation = runtime.validate_workflow(ROBOT_WORKFLOW_ID)
    assert validation["valid"] is True
    assert validation["workflowId"] == ROBOT_WORKFLOW_ID

    compiled = runtime.compile_workflow(ROBOT_WORKFLOW_ID)
    assert compiled["workflowId"] == ROBOT_WORKFLOW_ID
    assert compiled["grammarExtensionRequired"] is False

    with pytest.raises(LookupError, match="unknown-workflow"):
        runtime.get_workflow("unknown-workflow")


def test_create_run_rejects_unknown_identifiers_and_supports_reset(runtime, monkeypatch):
    with pytest.raises(LookupError, match="unknown-workflow"):
        runtime.create_run({"workflowId": "unknown-workflow"})

    with pytest.raises(ValueError, match=ROBOT_RUN_ID):
        runtime.create_run({"runId": "unknown-run"})

    reset = MagicMock(wraps=runtime.reset)
    monkeypatch.setattr(runtime, "reset", reset)
    result = runtime.create_run({"reset": True})

    reset.assert_called_once_with()
    assert result["run"]["id"] == ROBOT_RUN_ID


def test_timeline_options_receipt_and_dossier_expose_robot_projection(runtime):
    timeline = runtime.get_timeline(ROBOT_RUN_ID)
    assert timeline["eventCursor"]["latestSequence"] == 8
    assert timeline["timeline"][-1]["eventType"] == "approval.requested"

    options = runtime.get_options(ROBOT_RUN_ID)
    assert options["selectedOptionId"] == "robot-escalate"
    assert {option["id"] for option in options["options"]} >= {
        "robot-reroute",
        "robot-dock",
    }

    receipt = runtime.get_receipt(ROBOT_RUN_ID)["receipt"]
    assert receipt["signatureState"] == "pending"

    dossier = runtime.get_dossier(ROBOT_RUN_ID)["dossier"]
    assert dossier["runId"] == ROBOT_RUN_ID
    assert dossier["sanitization"]["synthetic"] is True


def test_insurance_run_reads_delegate_to_the_owned_runtime(runtime):
    insurance_runtime = MagicMock()
    insurance_runtime.owns_run_id.return_value = True
    insurance_runtime.get_timeline.return_value = {"timeline": "insurance"}
    insurance_runtime.get_options.return_value = {"options": "insurance"}
    insurance_runtime.get_receipt.return_value = {"receipt": "insurance"}
    runtime._insurance_runtime = insurance_runtime

    assert runtime.get_timeline("insurance-run") == {"timeline": "insurance"}
    assert runtime.get_options("insurance-run") == {"options": "insurance"}
    assert runtime.get_receipt("insurance-run") == {"receipt": "insurance"}

    insurance_runtime.get_timeline.assert_called_once_with("insurance-run")
    insurance_runtime.get_options.assert_called_once_with("insurance-run")
    insurance_runtime.get_receipt.assert_called_once_with("insurance-run")


def test_append_event_requires_type_and_idempotency_key(runtime):
    with pytest.raises(ValueError, match="Event type is required"):
        runtime.append_event(ROBOT_RUN_ID, {})

    with pytest.raises(ValueError, match="idempotencyKey is required"):
        runtime.append_event(ROBOT_RUN_ID, {"type": "custom.event"})


def test_blocked_option_records_a_denied_transition(runtime):
    result = runtime.select_option(
        ROBOT_RUN_ID,
        "robot-reroute",
        {
            "idempotencyKey": "coverage:blocked-option",
            "selectionReason": "Exercise imported policy denial",
        },
    )

    assert result["event"]["type"] == "transition.denied"
    assert result["event"]["payload"]["optionId"] == "robot-reroute"
    assert result["event"]["payload"]["deniedReason"] == (
        "Selected option is blocked by workflow constraints"
    )

    with pytest.raises(LookupError, match="unknown-option"):
        runtime.select_option(ROBOT_RUN_ID, "unknown-option", {})


def test_rejected_approval_validates_identifiers_and_projects_blocked_state(runtime):
    with pytest.raises(LookupError, match="unknown-approval"):
        runtime.decide_approval(ROBOT_RUN_ID, "unknown-approval", {"decision": "rejected"})

    with pytest.raises(ValueError, match="granted or rejected"):
        runtime.decide_approval(
            ROBOT_RUN_ID,
            "approval-robot-operator-1",
            {"decision": "maybe"},
        )

    result = runtime.decide_approval(
        ROBOT_RUN_ID,
        "approval-robot-operator-1",
        {"decision": "rejected", "idempotencyKey": "coverage:approval-rejected"},
    )

    assert result["run"]["status"] == "blocked"
    assert result["run"]["currentNodeId"] == "robot-operator"
    assert result["run"]["timeline"][-1]["detail"] == (
        "Synthetic override rejected; fallback required"
    )


def test_transition_without_approval_appends_denial_before_raising(runtime):
    with pytest.raises(EventSequenceError, match="has not been granted"):
        runtime.transition(
            ROBOT_RUN_ID,
            {"idempotencyKey": "coverage:transition-without-approval"},
        )

    assert runtime._run_events[ROBOT_RUN_ID][-1]["type"] == "transition.denied"
    assert runtime._run_events[ROBOT_RUN_ID][-1]["payload"]["targetNodeId"] == "robot-actuate"


def test_fallback_transition_seals_receipt_and_projects_safe_option(runtime):
    result = runtime.transition(
        ROBOT_RUN_ID,
        {
            "idempotencyKey": "coverage:fallback",
            "triggerFallback": True,
            "rationale": "Approval window expired",
        },
    )
    run = result["run"]

    assert run["status"] == "sealed"
    assert run["currentNodeId"] == "robot-receipt"
    assert run["selectedOptionId"] == "robot-dock"
    assert run["receipt"]["signatureState"] == "sealed"
    dock_node = next(node for node in run["nodes"] if node["id"] == "robot-dock")
    assert dock_node["status"] == "complete"
    assert [event["type"] for event in run["events"][-2:]] == [
        "fallback.triggered",
        "receipt.sealed",
    ]


def test_persisted_gate_requires_rule_service_and_unknown_run_is_rejected(runtime):
    with pytest.raises(ValueError, match="rule service is required"):
        runtime.evaluate_gate({"ruleName": "persisted-rule"})

    with pytest.raises(LookupError, match="unknown-run"):
        runtime.get_run("unknown-run")
