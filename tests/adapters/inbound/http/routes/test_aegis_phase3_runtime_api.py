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
from src.main import app


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
def client():
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
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_proposal(client: TestClient, run_id: str) -> dict:
    response = client.post(
        "/api/v1/aegis/action-proposals",
        json={
            "runId": run_id,
            "proposalId": f"proposal-{run_id}",
            "workflowId": "robot-action-firewall",
            "action": {"kind": "robot.reroute", "target": "AMR-17"},
            "actor": {"kind": "agent", "id": "planner-alpha", "role": "AI planner"},
            "facts": {"obstacleConfidence": 0.72, "batteryReservePercent": 61},
            "evidenceRefs": ["ev-obstacle-confidence", "ev-battery-reserve"],
            "evidenceHashes": {
                "ev-obstacle-confidence": "sha256:obstacle-confidence",
                "ev-battery-reserve": "sha256:battery-reserve",
            },
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_action"),
    [
        ("allow", "allowed", "receipt.seal"),
        ("deny", "denied", "receipt.seal"),
        ("modify", "modified", "option.select"),
        ("escalate", "escalated", "approval.grant"),
        ("require-approval", "approval_required", "approval.grant"),
        ("require-evidence", "evidence_required", "evidence.request"),
        ("fallback", "fallback_ready", "fallback.trigger"),
    ],
)
def test_phase3_preflight_and_gate_contracts_cover_runtime_outcomes(
    client: TestClient,
    outcome: str,
    expected_status: str,
    expected_action: str,
):
    run_id = f"run-{outcome}"
    created = _create_proposal(client, run_id)
    assert created["allowedActions"] == ["preflight.evaluate", "gate.evaluate"]

    preflight = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/preflight",
        json={
            "outcome": "allow",
            "idempotencyKey": f"{run_id}:preflight",
            "actor": {"kind": "system", "id": "aegis-preflight", "role": "policy gate"},
        },
    )
    assert preflight.status_code == 200
    assert preflight.json()["preflightDecision"]["outcome"] == "allow"
    assert preflight.json()["run"]["status"] == "preflight_passed"

    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": outcome,
            "idempotencyKey": f"{run_id}:gate:{outcome}",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
        },
    )

    assert gate.status_code == 200
    data = gate.json()
    assert data["gateDecision"]["outcome"] == outcome.replace("-", "_")
    assert data["run"]["status"] == expected_status
    assert expected_action in data["allowedActions"]
    assert data["event"]["type"] == "gate.evaluated"


def test_phase3_approval_override_receipt_and_passport_are_snapshot_derived(client: TestClient):
    run_id = "run-approval-passport"
    _create_proposal(client, run_id)
    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "require_approval",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
        },
    )
    assert gate.status_code == 200

    approval = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/approvals/approval-primary/decision",
        json={
            "decision": "granted",
            "rationale": "Synthetic safety lead accepts supervised no-op release.",
            "idempotencyKey": f"{run_id}:approval",
            "actor": {"kind": "human", "id": "dock-safety-lead", "role": "override authority"},
        },
    )
    assert approval.status_code == 200
    assert approval.json()["run"]["status"] == "approval_granted"

    override_request = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/overrides",
        json={
            "overrideId": "override-primary",
            "reason": "Operator requests bounded supervised override.",
            "idempotencyKey": f"{run_id}:override-request",
            "actor": {"kind": "human", "id": "operator-1", "role": "operator"},
        },
    )
    assert override_request.status_code == 200
    assert override_request.json()["run"]["status"] == "override_requested"

    override_decision = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/overrides/override-primary/decision",
        json={
            "decision": "granted",
            "rationale": "Override remains inside the no-op actuation boundary.",
            "idempotencyKey": f"{run_id}:override-decision",
            "actor": {"kind": "human", "id": "dock-safety-lead", "role": "override authority"},
        },
    )
    assert override_decision.status_code == 200
    assert override_decision.json()["run"]["status"] == "override_granted"

    receipt = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/receipt",
        json={
            "idempotencyKey": f"{run_id}:receipt",
            "actor": {"kind": "system", "id": "aegis-ledger", "role": "signature authority"},
        },
    )
    assert receipt.status_code == 200
    assert receipt.json()["run"]["status"] == "sealed"
    assert receipt.json()["receipt"]["signatureState"] == "sealed"

    passport = client.get(f"/api/v1/aegis/action-runs/{run_id}/passport")
    assert passport.status_code == 200
    payload = passport.json()
    assert payload["passport"]["sourceSnapshotHash"] == payload["snapshot"]["snapshotHash"]
    assert payload["passport"]["validation"] == {
        "source": "SessionSnapshot",
        "snapshotHashMatches": True,
        "sectionHashesMatch": True,
    }
    assert payload["passport"]["approval"]["status"] == "granted"
    assert payload["passport"]["approval"]["override"]["status"] == "granted"

    receipt_export = client.get(f"/api/v1/aegis/action-runs/{run_id}/receipt")
    dossier = client.get(f"/api/v1/aegis/action-runs/{run_id}/dossier")
    assert receipt_export.status_code == 200
    assert dossier.status_code == 200
    assert dossier.json()["dossier"]["sourceSnapshotHash"] == payload["snapshot"]["snapshotHash"]


def test_phase3_fallback_and_failed_receipt_states_are_contract_visible(client: TestClient):
    run_id = "run-fallback-failed-receipt"
    _create_proposal(client, run_id)
    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "fallback",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
        },
    )
    assert gate.status_code == 200

    fallback = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/fallback",
        json={
            "fallbackId": "return-to-dock",
            "idempotencyKey": f"{run_id}:fallback",
            "actor": {"kind": "system", "id": "aegis-runtime", "role": "workflow runtime"},
        },
    )
    assert fallback.status_code == 200
    assert fallback.json()["run"]["status"] == "fallback_triggered"

    receipt = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/receipt",
        json={
            "simulateFailure": True,
            "failureReason": "Synthetic signer unavailable.",
            "idempotencyKey": f"{run_id}:failed-receipt",
            "actor": {"kind": "system", "id": "aegis-ledger", "role": "signature authority"},
        },
    )
    assert receipt.status_code == 200
    data = receipt.json()
    assert data["run"]["status"] == "receipt_failed"
    assert data["receipt"]["signatureState"] == "failed"
    assert "receipt.seal" in data["allowedActions"]


def test_phase3_role_scoped_write_rejects_unauthorized_mutation_and_preserves_audit_event(
    client: TestClient,
):
    run_id = "run-unauthorized-approval"
    _create_proposal(client, run_id)
    client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "require_approval",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
        },
    )

    rejected = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/approvals/approval-primary/decision",
        json={
            "decision": "granted",
            "idempotencyKey": f"{run_id}:bad-approval",
            "actor": {"kind": "agent", "id": "planner-alpha", "role": "AI planner"},
        },
    )

    assert rejected.status_code == 403
    state = client.get(f"/api/v1/aegis/action-runs/{run_id}").json()
    assert state["run"]["status"] == "approval_required"
    assert "approval.grant" in state["allowedActions"]
    event_types = [event["type"] for event in state["events"]]
    assert "authorization.denied" in event_types
    assert "approval.granted" not in event_types


def test_phase4_counterfactuals_are_machine_readable_and_deterministic(client: TestClient):
    run_id = "run-phase4-counterfactual"
    _create_proposal(client, run_id)
    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "require_evidence",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
            "requiredFacts": ["operatorOverrideWindow"],
            "requiredEvidenceRefs": ["ev-dock-clearance"],
            "requiredApprovals": ["override authority"],
            "requiredPolicyVersions": {"ruleVersionHash": "sha256:phase4-required-policy"},
            "thresholds": [
                {
                    "id": "risk-score",
                    "currentValue": 0.72,
                    "requiredValue": 0.3,
                    "operator": "<=",
                }
            ],
            "fallbackRequired": True,
            "authorityRequired": "override authority",
        },
    )

    assert gate.status_code == 200
    first = client.get(f"/api/v1/aegis/action-runs/{run_id}/counterfactuals")
    second = client.get(f"/api/v1/aegis/action-runs/{run_id}/counterfactuals")
    by_proposal = client.get(f"/api/v1/aegis/action-proposals/proposal-{run_id}/counterfactuals")

    assert first.status_code == 200
    assert second.status_code == 200
    assert by_proposal.status_code == 200
    data = first.json()
    assert data == second.json()
    assert by_proposal.json()["counterfactualHash"] == data["counterfactualHash"]
    assert data["source"] == "deterministic-rule-graph"
    assert data["authoritative"] is True
    assert data["narrativeAuthoritative"] is False
    assert data["counterfactualHash"].startswith("sha256:")
    categories = {item["category"] for item in data["counterfactuals"]}
    assert categories == {
        "approval",
        "authority",
        "fallback_availability",
        "missing_evidence",
        "missing_fact",
        "policy_version",
        "threshold",
    }
    assert data["summary"]["blockingCount"] == len(data["counterfactuals"])
    assert data["summary"]["canPassWithoutChanges"] is False
    assert all(item["blocking"] is True for item in data["counterfactuals"])
    assert all(item["id"].startswith("sha256:") for item in data["counterfactuals"])


def test_phase4_autonomy_levels_validate_and_gate_above_assigned_level(client: TestClient):
    levels = client.get("/api/v1/aegis/autonomy-levels")
    assert levels.status_code == 200
    levels_data = levels.json()
    assert levels_data["source"] == "platform_live"
    assert levels_data["generatedAt"].endswith("Z")
    assert [entry["level"] for entry in levels_data["scale"]] == [
        "manual",
        "assisted",
        "supervised_autonomy",
        "certified_autonomy",
    ]
    assert levels_data["certifiedConfidenceThreshold"] == 0.85
    assert {rule["subjectId"] for rule in levels_data["rules"]} >= {
        "fleet-planner.alpha",
        "fleet-planner.*",
    }

    invalid = client.post(
        "/api/v1/aegis/autonomy-levels",
        json={"agentId": "policy-bot-1", "level": "unbounded"},
    )
    assert invalid.status_code == 400

    assigned = client.post(
        "/api/v1/aegis/autonomy-levels",
        json={
            "agentId": "policy-bot-1",
            "level": "assisted",
            "assignedBy": "test",
            "rationale": "Synthetic validation assignment.",
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignment"]["assignedLevel"] == "assisted"
    assert any(
        rule["subjectId"] == "policy-bot-1" and rule["level"] == "assisted"
        for rule in assigned.json()["rules"]
    )

    bulk = client.post(
        "/api/v1/aegis/autonomy-levels",
        json={
            "rules": [
                {
                    "id": "autonomy:policy-bot-2",
                    "subjectType": "agent",
                    "subjectId": "policy-bot-2",
                    "level": "certified_autonomy",
                    "minConfidenceThreshold": 0.91,
                    "updatedBy": "test",
                }
            ]
        },
    )
    assert bulk.status_code == 200
    assert any(
        rule["subjectId"] == "policy-bot-2"
        and rule["level"] == "certified_autonomy"
        and rule["minConfidenceThreshold"] == 0.91
        for rule in bulk.json()["rules"]
    )

    run_id = "run-certified-above-assignment"
    created = client.post(
        "/api/v1/aegis/action-proposals",
        json={
            "runId": run_id,
            "proposalId": f"proposal-{run_id}",
            "workflowId": "robot-action-firewall",
            "action": {"kind": "robot.reroute", "target": "AMR-17"},
            "actor": {"kind": "agent", "id": "policy-bot-1", "role": "AI planner"},
            "facts": {"obstacleConfidence": 0.92},
            "evidenceRefs": ["ev-obstacle-confidence"],
            "evidenceHashes": {"ev-obstacle-confidence": "sha256:confidence"},
            "autonomyPolicy": {
                "level": "certified_autonomy",
                "confidence": 0.92,
                "certifiedTemplate": True,
                "fallbackReady": True,
                "evidenceComplete": True,
                "policyValidationStatus": "valid",
                "receiptReady": True,
            },
        },
    )
    assert created.status_code == 200

    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "allow",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
        },
    )

    assert gate.status_code == 200
    data = gate.json()
    assert data["gateDecision"]["outcome"] == "require_approval"
    assert data["run"]["status"] == "approval_required"
    assert data["gateDecision"]["autonomyEnforcement"]["requestedLevel"] == "certified_autonomy"
    assert data["gateDecision"]["autonomyEnforcement"]["assignedLevel"] == "assisted"
    assert data["gateDecision"]["autonomyEnforcement"]["requiresApproval"] is True


def test_phase4_risk_heatmap_returns_ledger_and_synthetic_rows(client: TestClient):
    run_id = "run-risk-heatmap"
    created = client.post(
        "/api/v1/aegis/action-proposals",
        json={
            "runId": run_id,
            "proposalId": f"proposal-{run_id}",
            "workflowId": "robot-action-firewall",
            "action": {"kind": "robot.reroute", "target": "AMR-17"},
            "actor": {"kind": "agent", "id": "heatmap-agent", "role": "AI planner"},
            "facts": {"obstacleConfidence": 0.7},
            "evidenceRefs": ["ev-obstacle-confidence"],
            "evidenceHashes": {"ev-obstacle-confidence": "sha256:confidence"},
            "autonomyPolicy": {"level": "supervised_autonomy", "riskScore": 88},
        },
    )
    assert created.status_code == 200

    response = client.get("/api/v1/aegis/agents/risk-heatmap")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "platform_live"
    assert data["ledgerSource"] == "aegis-event-ledger"
    assert data["generatedAt"].endswith("Z")
    assert data["certifiedConfidenceThreshold"] == 0.85
    by_run = {row["runId"]: row for row in data["rows"]}
    assert by_run[run_id]["agentId"] == "heatmap-agent"
    assert by_run[run_id]["id"] == f"heatmap-agent:{run_id}"
    assert by_run[run_id]["groupBy"] == "agent"
    assert by_run[run_id]["riskScore"] == 88
    assert by_run[run_id]["riskBand"] == "high"
    assert by_run[run_id]["reviewAction"]["actionType"] in {
        "inspect_hash",
        "route_regulator_review",
    }
    assert by_run["wf-robot-124"]["agentId"] == "fleet-planner.alpha"
    assert data["summary"]["rowCount"] == len(data["rows"])


def test_phase4_sla_timer_generates_warning_and_breach_events(client: TestClient):
    run_id = "run-sla-timer"
    created = client.post(
        "/api/v1/aegis/action-proposals",
        json={
            "runId": run_id,
            "proposalId": f"proposal-{run_id}",
            "workflowId": "robot-action-firewall",
            "actor": {"kind": "agent", "id": "sla-agent", "role": "AI planner"},
            "sla": {
                "deadline": "2026-06-08T00:10:00Z",
                "warningAt": "2026-06-08T00:08:00Z",
                "escalationAt": "2026-06-08T00:15:00Z",
            },
        },
    )
    assert created.status_code == 200

    warning = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/sla/tick",
        json={
            "now": "2026-06-08T00:09:00Z",
            "idempotencyKey": f"{run_id}:sla-warning",
        },
    )
    assert warning.status_code == 200
    assert warning.json()["event"]["type"] == "sla.warning"
    assert warning.json()["run"]["slaState"] == "warning"

    breach = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/sla/tick",
        json={
            "now": "2026-06-08T00:11:00Z",
            "idempotencyKey": f"{run_id}:sla-breach",
        },
    )
    assert breach.status_code == 200
    assert breach.json()["event"]["type"] == "sla.breached"
    assert breach.json()["run"]["status"] == "escalated"
    assert breach.json()["run"]["slaState"] == "breached"


def test_phase4_policy_replay_groups_route_release_changes(client: TestClient):
    response = client.post(
        "/api/v1/aegis/policies/autonomy_base_safety.robot.route_release/replay",
        json={},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "platform_live"
    assert data["policyGraphSource"] == "deterministic-policy-graph"
    assert data["authoritative"] is True
    assert data["narrativeAuthoritative"] is False
    assert data["replayHash"].startswith("sha256:")
    assert data["policyVersionHash"].startswith("sha256:")
    assert data["generatedAt"].endswith("Z")
    assert data["summary"] == {
        "unchanged": 1,
        "newlyAllowed": 1,
        "newlyDenied": 1,
        "newlyEscalated": 1,
        "evidenceInsufficient": 1,
    }
    assert {row["group"] for row in data["rows"]} == {
        "unchanged",
        "newly_allowed",
        "newly_denied",
        "newly_escalated",
        "evidence_insufficient",
    }
    evidence_row = next(row for row in data["rows"] if row["group"] == "evidence_insufficient")
    assert evidence_row["replayedOutcome"] == "EVIDENCE_INSUFFICIENT"
    assert evidence_row["recoveryActionType"] == "repair_evidence"
    assert data["groups"]["newlyDenied"][0]["counterfactuals"][0]["source"] == "deterministic-policy-graph"


def test_phase4_dossier_exports_json_ld_and_svg_baselines(client: TestClient):
    run_id = "run-dossier-export"
    _create_proposal(client, run_id)
    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "deny",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
        },
    )
    assert gate.status_code == 200
    receipt = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/receipt",
        json={
            "idempotencyKey": f"{run_id}:receipt",
            "actor": {"kind": "system", "id": "aegis-ledger", "role": "signature authority"},
        },
    )
    assert receipt.status_code == 200

    json_ld = client.get(f"/api/v1/aegis/action-runs/{run_id}/dossier?format=json-ld")
    svg = client.get(f"/api/v1/aegis/action-runs/{run_id}/dossier?format=svg")

    assert json_ld.status_code == 200
    assert json_ld.json()["export"]["format"] == "json-ld"
    assert json_ld.json()["export"]["document"]["@type"] == "aegis:DecisionDossier"
    assert json_ld.json()["dossier"]["sourceSnapshotHash"] == receipt.json()["snapshot"]["snapshotHash"]
    assert svg.status_code == 200
    assert svg.json()["export"]["mediaType"] == "image/svg+xml"
    assert svg.json()["export"]["document"].startswith("<svg")


def test_evidence_fact_ingestion_preserves_provenance_and_can_satisfy_authoritative_gate(
    client: TestClient,
):
    run_id = "run-evidence-facts"
    _create_proposal(client, run_id)

    ingested = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/evidence-facts",
        json={
            "idempotencyKey": f"{run_id}:facts",
            "extractionMethod": "deterministic-dock-evidence-map",
            "authorityClass": "asserted",
            "evidence": [
                {
                    "id": "ev-dock-clearance",
                    "sourceLabel": "synthetic dock sensor",
                    "sourceUri": "synthetic://dock/C/clearance",
                    "contentHash": "sha256:dock-clearance",
                    "facts": [
                        {
                            "name": "dockClearanceAvailable",
                            "value": True,
                            "valueType": "boolean",
                            "confidence": 0.93,
                        }
                    ],
                }
            ],
        },
    )

    assert ingested.status_code == 200
    fact = ingested.json()["factLedger"]["extractedFacts"][0]
    assert fact["factName"] == "dockClearanceAvailable"
    assert fact["sourceRefs"] == ["ev-dock-clearance"]
    assert fact["sourceHashes"] == ["sha256:dock-clearance"]
    assert fact["extractionMethod"] == "deterministic-dock-evidence-map"
    assert fact["authorityClass"] == "asserted"
    assert fact["canSatisfyAuthoritativeRules"] is True

    state = client.get(f"/api/v1/aegis/action-runs/{run_id}/evidence-facts")
    assert state.status_code == 200
    provenance = state.json()["factProvenance"]["dockClearanceAvailable"]
    assert provenance["factHash"].startswith("sha256:")
    assert provenance["canSatisfyAuthoritativeRules"] is True
    assert state.json()["facts"]["dockClearanceAvailable"] is True

    gate = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/gate",
        json={
            "outcome": "allow",
            "idempotencyKey": f"{run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
            "requiredFacts": ["dockClearanceAvailable"],
        },
    )
    assert gate.status_code == 200
    assert gate.json()["gateDecision"]["factAuthority"] == {
        "requiredFacts": ["dockClearanceAvailable"],
        "checked": True,
        "source": "aegis-evidence-fact-ledger",
    }


def test_authoritative_fact_ingestion_rejects_missing_provenance(client: TestClient):
    run_id = "run-missing-fact-provenance"
    _create_proposal(client, run_id)

    rejected = client.post(
        f"/api/v1/aegis/action-runs/{run_id}/evidence-facts",
        json={
            "idempotencyKey": f"{run_id}:facts",
            "authorityClass": "asserted",
            "evidence": [
                {
                    "id": "ev-unhashed-dock-clearance",
                    "sourceLabel": "synthetic dock sensor",
                    "facts": [{"name": "dockClearanceAvailable", "value": True}],
                }
            ],
        },
    )

    assert rejected.status_code == 400
    assert "source refs and source hashes" in rejected.json()["detail"]


def test_similar_cases_are_scored_advisory_and_cannot_satisfy_authoritative_rules(
    client: TestClient,
):
    prior_run_id = "run-prior-similar-case"
    target_run_id = "run-target-similar-case"
    _create_proposal(client, prior_run_id)
    _create_proposal(client, target_run_id)
    client.post(
        f"/api/v1/aegis/action-runs/{prior_run_id}/evidence-facts",
        json={
            "idempotencyKey": f"{prior_run_id}:facts",
            "authorityClass": "asserted",
            "evidence": [
                {
                    "id": "ev-prior-dock-clearance",
                    "contentHash": "sha256:prior-dock-clearance",
                    "facts": [{"name": "dockClearanceAvailable", "value": True}],
                }
            ],
        },
    )
    client.post(
        f"/api/v1/aegis/action-runs/{prior_run_id}/gate",
        json={
            "outcome": "allow",
            "idempotencyKey": f"{prior_run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
            "requiredFacts": ["dockClearanceAvailable"],
        },
    )

    similar = client.get(f"/api/v1/aegis/action-runs/{target_run_id}/similar-cases?limit=1")
    assert similar.status_code == 200
    data = similar.json()
    assert data["scope"]["workflowId"] == "robot-action-firewall"
    assert data["authorityBoundary"]["canSatisfyAuthoritativeRules"] is False
    assert data["readModelHash"].startswith("sha256:")
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["caseRunId"] == prior_run_id
    assert result["score"] > 0
    assert {component["name"] for component in result["scoreComponents"]} == {
        "actionKind",
        "targetAsset",
        "factOverlap",
        "policyHash",
        "evidenceCompleteness",
        "optionOutcome",
    }
    advisory_fact = next(
        fact for fact in result["advisoryFacts"] if fact["factName"] == "dockClearanceAvailable"
    )
    assert advisory_fact["authorityClass"] == "similar_case_advisory"
    assert advisory_fact["canSatisfyAuthoritativeRules"] is False

    advisory_ingest = client.post(
        f"/api/v1/aegis/action-runs/{target_run_id}/evidence-facts",
        json={
            "idempotencyKey": f"{target_run_id}:similar-fact",
            "facts": [advisory_fact],
        },
    )
    assert advisory_ingest.status_code == 200

    blocked_gate = client.post(
        f"/api/v1/aegis/action-runs/{target_run_id}/gate",
        json={
            "outcome": "allow",
            "idempotencyKey": f"{target_run_id}:gate",
            "actor": {"kind": "system", "id": "aegis-gate", "role": "policy gate"},
            "requiredFacts": ["dockClearanceAvailable"],
        },
    )
    assert blocked_gate.status_code == 400
    assert "missing or advisory only" in blocked_gate.json()["detail"]
