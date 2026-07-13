from fastapi.testclient import TestClient

from src.domain.aegis import reset_synthetic_aegis_runtime
from src.main import app


def _client() -> TestClient:
    reset_synthetic_aegis_runtime()
    return TestClient(app)


def test_robot_runtime_run_exposes_executable_contract():
    client = _client()

    response = client.get("/api/v1/aegis/workflow-runs/wf-robot-124")

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["id"] == "wf-robot-124"
    assert run["definitionId"] == "synthetic-robot-task-approval"
    assert run["status"] == "escalated"
    assert run["currentNodeId"] == "robot-option-set"
    assert run["selectedOptionId"] == "robot-escalate"
    assert "approval.granted" in run["allowedActions"]
    assert run["ruleGate"]["validation"]["valid"] is True
    assert run["receipt"]["signatureState"] == "pending"
    assert run["evidence"][0]["sanitization"] == {
        "synthetic": True,
        "containsCustomerData": False,
        "containsPhi": False,
        "containsSecrets": False,
    }
    evidence_ids = {payload["id"] for payload in run["evidence"]}
    node_contract_keys = {
        "entryCriteria",
        "exitCriteria",
        "conditionMetadata",
        "requiredEvidenceRefs",
        "producedEvidenceRefs",
        "slaState",
        "blockedReason",
        "recoveryActions",
    }
    for node in run["nodes"]:
        missing_keys = node_contract_keys - set(node)
        assert missing_keys == set(), f"{node['id']} missing node contract keys {missing_keys}"
        assert node["entryCriteria"], f"{node['id']} has no entry criteria"
        assert node["exitCriteria"], f"{node['id']} has no exit criteria"
        assert isinstance(node["requiredEvidenceRefs"], list)
        assert isinstance(node["producedEvidenceRefs"], list)
        assert node["slaState"] in {"met", "warning", "breached", "not_started"}
        assert isinstance(node["recoveryActions"], list)
        if node["status"] in {"blocked", "failed", "escalated"}:
            assert node["blockedReason"], f"{node['id']} is {node['status']} without a blocked reason"
            assert node["recoveryActions"], f"{node['id']} is {node['status']} without recovery actions"

        unresolved_refs = set(node["requiredEvidenceRefs"]) | set(node["producedEvidenceRefs"])
        unresolved_refs -= evidence_ids
        assert unresolved_refs == set(), f"{node['id']} has unresolved evidence refs {unresolved_refs}"
        assert isinstance(node["conditionMetadata"], dict)
        assert isinstance(node["conditionMetadata"].get("entryConditions"), list)
        assert isinstance(node["conditionMetadata"].get("exitConditions"), list)
        for condition in node["conditionMetadata"].get("entryConditions", []):
            assert isinstance(condition, dict)
            assert "condition" in condition
            if condition.get("evidenceRefs"):
                assert set(condition["evidenceRefs"]) <= evidence_ids
        for condition in node["conditionMetadata"].get("exitConditions", []):
            assert isinstance(condition, dict)
            assert "condition" in condition
            if condition.get("evidenceRefs"):
                assert set(condition["evidenceRefs"]) <= evidence_ids
    sequences = [event["sequence"] for event in run["events"]]
    assert sequences == sorted(sequences)


def test_event_append_assigns_sequence_and_replays_duplicate_idempotency_key():
    client = _client()
    body = {
        "type": "approval.granted",
        "idempotencyKey": "test:approval-granted",
        "actor": {"kind": "human", "id": "dock-safety-lead", "role": "override authority"},
        "payload": {"approvalId": "approval-robot-operator-1", "rationale": "Synthetic approval"},
    }

    first = client.post("/api/v1/aegis/workflow-runs/wf-robot-124/events", json=body)
    second = client.post("/api/v1/aegis/workflow-runs/wf-robot-124/events", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()
    second_data = second.json()
    assert first_data["event"]["sequence"] == 9
    assert first_data["idempotentReplay"] is False
    assert second_data["event"]["sequence"] == 9
    assert second_data["idempotentReplay"] is True
    assert second_data["run"]["eventCursor"]["latestSequence"] == 9


def test_event_append_rejects_out_of_order_sequence():
    client = _client()

    response = client.post(
        "/api/v1/aegis/workflow-runs/wf-robot-124/events",
        json={
            "type": "approval.granted",
            "idempotencyKey": "test:sequence-gap",
            "sequence": 42,
        },
    )

    assert response.status_code == 409
    assert "expected 9" in response.json()["detail"]


def test_sla_breach_surfaces_fallback_recovery_state():
    client = _client()

    response = client.post(
        "/api/v1/aegis/workflow-runs/wf-robot-124/events",
        json={
            "type": "sla.breached",
            "idempotencyKey": "test:sla-breach",
            "payload": {"reason": "Operator approval SLA expired"},
        },
    )

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["slaState"] == "breached"
    assert run["currentNodeId"] == "robot-dock"
    assert run["selectedOptionId"] == "robot-dock"
    assert "trigger return-to-dock fallback" in run["recoveryActions"]
    assert run["blockedReason"] == "Operator approval SLA expired before an override decision."


def test_transition_after_approval_runs_noop_actuation_and_seals_receipt():
    client = _client()
    approval = client.post(
        "/api/v1/aegis/workflow-runs/wf-robot-124/approvals/approval-robot-operator-1/decision",
        json={
            "decision": "granted",
            "idempotencyKey": "test:approval-decision-granted",
        },
    )
    assert approval.status_code == 200

    transition = client.post(
        "/api/v1/aegis/workflow-runs/wf-robot-124/transition",
        json={"idempotencyKey": "test:transition-happy-path"},
    )

    assert transition.status_code == 200
    run = transition.json()["run"]
    assert run["status"] == "sealed"
    assert run["currentNodeId"] == "robot-receipt"
    assert run["receipt"]["signatureState"] == "sealed"
    assert {event["type"] for event in run["events"]} >= {
        "transition.allowed",
        "actuation.allowed",
        "actuation.noop.completed",
        "receipt.sealed",
    }


def test_transition_can_surface_receipt_seal_failure_boundary():
    client = _client()
    client.post(
        "/api/v1/aegis/workflow-runs/wf-robot-124/approvals/approval-robot-operator-1/decision",
        json={
            "decision": "granted",
            "idempotencyKey": "test:approval-before-receipt-failure",
        },
    )

    transition = client.post(
        "/api/v1/aegis/workflow-runs/wf-robot-124/transition",
        json={
            "idempotencyKey": "test:transition-receipt-failure",
            "simulateReceiptSealFailure": True,
        },
    )

    assert transition.status_code == 200
    run = transition.json()["run"]
    assert run["status"] == "failed"
    assert run["receipt"]["signatureState"] == "failed"
    assert "retry_receipt_seal" in run["allowedActions"]
    assert run["blockedReason"] == "Receipt seal failed after preserving event history."


def test_gate_evaluate_uses_synthetic_rule_boundary():
    client = _client()

    response = client.post("/api/v1/aegis/gates/evaluate", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["validation"]["valid"] is True
    assert data["safetyBoundarySatisfied"] is False
    assert data["operatorEscalationRequired"] is True
    assert data["autonomyEligibility"] == {
        "eligible": False,
        "reason": "obstacle confidence below threshold or route import blocks autonomous actuation",
    }
