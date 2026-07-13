import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.inbound.http.dependencies import get_aegis_db_session
from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.models import (
    AegisActionProposalORM,
    AegisEventLedgerEntryORM,
    AegisFileORM,
    AegisHistoryORM,
    AegisRuleORM,
    AegisSessionSnapshotORM,
    AegisWorkflowDefinitionORM,
    AegisWorkflowRunORM,
    AegisWorkflowVersionORM,
)
from src.domain.aegis import reset_synthetic_aegis_runtime
from src.domain.aegis.insurance_fraud_replay import (
    FRAUD_APPROVAL_ID,
    INSURANCE_DEFAULT_RUN_ID,
    INSURANCE_WORKFLOW_ID,
    InsuranceFraudReplayRuntime,
)
from src.main import app


def _client() -> TestClient:
    reset_synthetic_aegis_runtime()
    return TestClient(app)


def _tables():
    return [
        AegisRuleORM.__table__,
        AegisFileORM.__table__,
        AegisHistoryORM.__table__,
        AegisWorkflowDefinitionORM.__table__,
        AegisWorkflowVersionORM.__table__,
        AegisWorkflowRunORM.__table__,
        AegisActionProposalORM.__table__,
        AegisEventLedgerEntryORM.__table__,
        AegisSessionSnapshotORM.__table__,
    ]


@pytest.fixture
def db_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(bind=engine, tables=_tables())
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_aegis_db_session] = _override
    reset_synthetic_aegis_runtime()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_insurance_fraud_workflow_exposes_deterministic_replay_contract():
    client = _client()

    workflow = client.get(f"/api/v1/aegis/workflows/{INSURANCE_WORKFLOW_ID}")
    validation = client.post(f"/api/v1/aegis/workflows/{INSURANCE_WORKFLOW_ID}/validate", json={})
    compiled = client.post(f"/api/v1/aegis/workflows/{INSURANCE_WORKFLOW_ID}/compile", json={})
    run = client.get(f"/api/v1/aegis/workflow-runs/{INSURANCE_DEFAULT_RUN_ID}")

    assert workflow.status_code == 200
    workflow_data = workflow.json()
    assert workflow_data["domain"] == "insurance"
    assert workflow_data["title"] == "Flood-Damaged Warehouse Claim Fraud Gate"
    assert workflow_data["replayInputs"]["publicContext"]["status"] == "cached_fallback"
    assert {branch["branchId"] for branch in workflow_data["replayInputs"]["branches"]} == {
        "allow_payout",
        "request_evidence",
        "escalate_fraud_review",
        "freeze_payout",
        "deny_reject",
    }

    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert validation.json()["invariants"][-1] == {
        "code": "FRAUD_LEAD_ROLE_ENFORCED",
        "valid": True,
    }
    assert compiled.status_code == 200
    assert compiled.json()["grammarExtensionRequired"] is False
    assert len(compiled.json()["compiledPolicyRefs"]) == 4

    assert run.status_code == 200
    run_data = run.json()["run"]
    assert run_data["status"] == "gate_evaluated"
    assert run_data["recommendedOptionId"] == "escalate_fraud_review"
    assert run_data["ruleGate"]["decision"]["outcome"] == "escalate_fraud_review"
    assert run_data["publicContextHash"].startswith("sha256:")
    assert all(event["eventHash"].startswith("sha256:") for event in run_data["events"])
    assert all(evidence["sanitization"]["synthetic"] is True for evidence in run_data["evidence"])


@pytest.mark.parametrize(
    ("branch_id", "option_id", "terminal_event"),
    [
        ("allow_payout", "allow_payout", "payout.allowed"),
        ("request_evidence", "request_evidence", "evidence.requested"),
        ("escalate_fraud_review", "escalate_fraud_review", "fraud.escalated"),
        ("freeze_payout", "freeze_payout", "payout.frozen"),
        ("deny_reject", "deny_reject", "claim.denied"),
    ],
)
def test_insurance_fraud_replay_branches_seal_receipts(branch_id: str, option_id: str, terminal_event: str):
    client = _client()
    created = client.post(
        "/api/v1/aegis/workflow-runs",
        json={
            "workflowId": INSURANCE_WORKFLOW_ID,
            "branchId": branch_id,
            "reset": True,
        },
    )
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]

    gate = client.post(
        "/api/v1/aegis/gates/evaluate",
        json={"workflowId": INSURANCE_WORKFLOW_ID, "branchId": branch_id, "runId": run_id},
    )
    assert gate.status_code == 200
    assert gate.json()["decision"]["selectedOptionId"] == option_id

    selected = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/options/{option_id}/select",
        json={
            "idempotencyKey": f"{run_id}:test:select",
            "actor": {"kind": "human", "id": "claims-handler-1", "role": "claims handler"},
        },
    )
    assert selected.status_code == 200

    if option_id in {"escalate_fraud_review", "freeze_payout", "deny_reject"}:
        approved = client.post(
            f"/api/v1/aegis/workflow-runs/{run_id}/approvals/{FRAUD_APPROVAL_ID}/decision",
            json={
                "decision": "granted",
                "idempotencyKey": f"{run_id}:test:fraud-approval",
                "actor": {"kind": "human", "id": "fraud-lead-2", "role": "fraud lead"},
            },
        )
        assert approved.status_code == 200

    transitioned = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/transition",
        json={"idempotencyKey": f"{run_id}:test:transition"},
    )
    assert transitioned.status_code == 200
    sealed_run = transitioned.json()["run"]
    receipt = sealed_run["receipt"]

    assert sealed_run["status"] == "sealed"
    assert receipt["signatureState"] == "sealed"
    assert receipt["ruleOutcome"] == branch_id
    assert receipt["selectedOption"] == option_id
    assert receipt["terminalAction"] == terminal_event
    assert receipt["policyHashes"]["ruleVersionHash"].startswith("sha256:")
    assert receipt["policyHashes"]["publicContextHash"].startswith("sha256:")
    assert receipt["eventHashes"][-1] == sealed_run["eventCursor"]["latestHash"]

    dossier = client.get(f"/api/v1/aegis/workflow-runs/{run_id}/dossier")
    assert dossier.status_code == 200
    assert dossier.json()["dossier"]["replayInput"]["branchId"] == branch_id
    assert dossier.json()["dossier"]["publicContext"]["status"] == "cached_fallback"


def test_insurance_fraud_approval_persists_across_runtime_instances(tmp_path):
    state_path = tmp_path / "insurance-replay-state.json"
    worker_a = InsuranceFraudReplayRuntime(state_path=state_path)
    worker_b = InsuranceFraudReplayRuntime(state_path=state_path)

    created = worker_a.create_run(
        {
            "workflowId": INSURANCE_WORKFLOW_ID,
            "branchId": "freeze_payout",
            "reset": True,
        }
    )
    run_id = created["run"]["id"]

    selected = worker_a.select_option(
        run_id,
        "freeze_payout",
        {
            "idempotencyKey": f"{run_id}:test:select-shared-state",
            "actor": {"kind": "human", "id": "claims-handler-1", "role": "claims handler"},
        },
    )
    assert selected["run"]["status"] == "approval_required"

    approved = worker_a.decide_approval(
        run_id,
        FRAUD_APPROVAL_ID,
        {
            "decision": "granted",
            "idempotencyKey": f"{run_id}:test:fraud-approval-shared-state",
            "actor": {"kind": "human", "id": "fraud-lead-2", "role": "fraud lead"},
        },
    )
    assert approved["run"]["status"] == "approval_granted"

    observed = worker_b.get_run(run_id)["run"]
    assert observed["status"] == "approval_granted"
    assert observed["receipt"]["approvalActor"]["role"] == "fraud lead"

    transitioned = worker_b.transition(
        run_id,
        {"idempotencyKey": f"{run_id}:test:transition-shared-state"},
    )
    receipt = transitioned["run"]["receipt"]
    assert transitioned["run"]["status"] == "sealed"
    assert receipt["terminalAction"] == "payout.frozen"
    assert receipt["approvalActor"]["role"] == "fraud lead"


def test_insurance_fraud_lead_approval_is_role_enforced_and_rejection_is_audited():
    client = _client()
    run_id = INSURANCE_DEFAULT_RUN_ID

    selected = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/options/escalate_fraud_review/select",
        json={"idempotencyKey": f"{run_id}:test:select-escalate"},
    )
    assert selected.status_code == 200

    unauthorized = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/approvals/{FRAUD_APPROVAL_ID}/decision",
        json={
            "decision": "granted",
            "idempotencyKey": f"{run_id}:test:bad-approval",
            "actor": {"kind": "agent", "id": "claims-bot", "role": "claims automation"},
        },
    )
    assert unauthorized.status_code == 403
    state_after_rejection = client.get(f"/api/v1/aegis/workflow-runs/{run_id}").json()["run"]
    event_types = [event["type"] for event in state_after_rejection["events"]]
    assert "authorization.denied" in event_types
    assert "approval.granted" not in event_types

    rejected = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/approvals/{FRAUD_APPROVAL_ID}/decision",
        json={
            "decision": "rejected",
            "idempotencyKey": f"{run_id}:test:fraud-rejected",
            "actor": {"kind": "human", "id": "fraud-lead-2", "role": "fraud lead"},
        },
    )
    assert rejected.status_code == 200

    transitioned = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/transition",
        json={"idempotencyKey": f"{run_id}:test:transition-rejected"},
    )
    receipt = transitioned.json()["run"]["receipt"]
    assert transitioned.status_code == 200
    assert receipt["signatureState"] == "sealed"
    assert receipt["approvalStatus"] == "rejected"
    assert receipt["terminalAction"] == "claim.denied"
    assert receipt["approvalActor"]["role"] == "fraud lead"


def test_insurance_replay_events_are_idempotent_and_content_hashed():
    client = _client()
    run_id = INSURANCE_DEFAULT_RUN_ID
    body = {
        "type": "case.note.recorded",
        "idempotencyKey": f"{run_id}:test:case-note",
        "actor": {"kind": "system", "id": "test", "role": "workflow runtime"},
        "payload": {"note": "deterministic replay audit marker"},
    }

    first = client.post(f"/api/v1/aegis/workflow-runs/{run_id}/events", json=body)
    second = client.post(f"/api/v1/aegis/workflow-runs/{run_id}/events", json=body)
    conflict = client.post(
        f"/api/v1/aegis/workflow-runs/{run_id}/events",
        json={**body, "payload": {"note": "different content"}},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert conflict.status_code == 409
    assert first.json()["idempotentReplay"] is False
    assert second.json()["idempotentReplay"] is True
    assert first.json()["event"]["contentHash"].startswith("sha256:")
    assert first.json()["event"]["eventHash"] == second.json()["event"]["eventHash"]


def test_insurance_payload_exercises_action_run_gate_approval_receipt_and_dossier(db_client: TestClient):
    run_id = "run-insurance-action-fraud-review"
    created = db_client.post(
        "/api/v1/aegis/action-proposals",
        json={
            "runId": run_id,
            "proposalId": f"proposal-{run_id}",
            "workflowId": INSURANCE_WORKFLOW_ID,
            "action": {"kind": "insurance.claim.payout", "target": "synthetic-claim-flood-4305-001"},
            "actor": {"kind": "agent", "id": "claims-automation", "role": "AI planner"},
            "facts": {
                "claimAmount": 33600,
                "duplicateBankAccountDetected": True,
                "publicFloodContextMatchesPostcode": True,
            },
            "evidenceRefs": ["ev-claim-form", "ev-public-flood-context", "ev-payment-instruction"],
            "evidenceHashes": {
                "ev-claim-form": "sha256:claim-form",
                "ev-public-flood-context": "sha256:public-context",
                "ev-payment-instruction": "sha256:payment-instruction",
            },
            "policyHashes": {
                "ruleVersionHash": "sha256:insurance-rule",
                "publicContextHash": "sha256:public-context",
            },
        },
    )
    assert created.status_code == 200

    gate = db_client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "require_approval",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
            "requiredApprovals": ["override authority"],
            "requiredEvidenceRefs": ["ev-public-flood-context"],
        },
    )
    assert gate.status_code == 200
    assert gate.json()["run"]["status"] == "approval_required"

    approval = db_client.post(
        f"/api/v1/aegis/action-runs/{run_id}/approvals/approval-primary/decision",
        json={
            "decision": "granted",
            "idempotencyKey": f"{run_id}:approval",
            "actor": {"kind": "human", "id": "fraud-lead-2", "role": "override authority"},
        },
    )
    assert approval.status_code == 200

    receipt = db_client.post(
        f"/api/v1/aegis/action-runs/{run_id}/receipt",
        json={
            "idempotencyKey": f"{run_id}:receipt",
            "actor": {"kind": "system", "id": "aegis-ledger", "role": "signature authority"},
        },
    )
    assert receipt.status_code == 200
    assert receipt.json()["receipt"]["signatureState"] == "sealed"

    dossier = db_client.get(f"/api/v1/aegis/action-runs/{run_id}/dossier")
    assert dossier.status_code == 200
    assert dossier.json()["dossier"]["runId"] == run_id
    assert dossier.json()["dossier"]["policy"]["publicContextHash"] == "sha256:public-context"
