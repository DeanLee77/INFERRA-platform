from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.persistence.database import Base
from src.adapters.outbound.persistence.models import (
    AegisFileORM,
    AegisHistoryORM,
    AegisRuleORM,
    AegisWorkflowDefinitionORM,
    AegisWorkflowVersionORM,
)
from src.main import app


AEGIS_RULE_TEXT = """INPUT age AS NUMBER

eligible
    AND age >= 18
"""


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _seed_rule(SessionLocal):
    db = SessionLocal()
    try:
        rule = AegisRuleORM(
            rule_name="robot_safety_gate",
            rule_category="AEGIS Testing",
            rule_description="Synthetic robot policy gate.",
        )
        rule.rule_id = 1
        db.add(rule)
        file_record = AegisFileORM(
            rule_id=1,
            files=bytearray(AEGIS_RULE_TEXT.encode("utf-8")),
        )
        file_record.file_id = 1
        db.add(file_record)
        db.commit()
    finally:
        db.close()


@contextmanager
def _aegis_db_override(SessionLocal):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _client():
    engine = _engine()
    Base.metadata.create_all(
        bind=engine,
        tables=[
            AegisRuleORM.__table__,
            AegisFileORM.__table__,
            AegisHistoryORM.__table__,
            AegisWorkflowDefinitionORM.__table__,
            AegisWorkflowVersionORM.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _seed_rule(SessionLocal)

    def _get_aegis_db():
        with _aegis_db_override(SessionLocal) as db:
            yield db

    from src.adapters.inbound.http.dependencies import get_aegis_db_session

    @contextmanager
    def _patched_client():
        app.dependency_overrides[get_aegis_db_session] = _get_aegis_db
        try:
            with patch("src.adapters.inbound.http.routes.aegis.get_aegis_db", _get_aegis_db):
                yield
        finally:
            app.dependency_overrides.pop(get_aegis_db_session, None)

    return _patched_client()


def _workflow_payload():
    return {
        "id": "robot-action-firewall",
        "title": "Robot Action Firewall",
        "domain": "robotics",
        "evidence": [
            {
                "id": "ev-request",
                "sourceLayer": "ASSERTED",
                "value": "robot reroute request",
                "valueType": "string",
                "confidence": 1.0,
                "trustScore": 0.95,
                "sourceLabel": "synthetic_fleet_planner",
                "sourceUri": "synthetic://robot/request",
                "contentHash": "sha256:request",
                "freshnessState": "fresh",
                "sanitization": {"synthetic": True},
            }
        ],
        "nodes": [
            {
                "id": "robot-request",
                "label": "Task request",
                "type": "REQUEST",
                "owner": "fleet-planner.alpha",
                "role": "AI planner",
                "entryCriteria": ["proposal received"],
                "exitCriteria": ["request fields complete"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "proposal received"}],
                    "exitConditions": [{"condition": "request fields complete"}],
                },
                "requiredEvidenceRefs": ["ev-request"],
                "producedEvidenceRefs": [],
                "recoveryActions": ["reject request"],
                "requester": "fleet-planner.alpha",
                "requestedOutcome": "reroute AMR-17",
                "actionDomain": "robotics",
                "inputFacts": {"age": 19},
                "idempotencyKey": "wf-authoring:robot-request",
            },
            {
                "id": "robot-rule",
                "label": "Safety gate",
                "type": "RULE_GATE",
                "owner": "INFERRA sidecar",
                "role": "policy gate",
                "entryCriteria": ["request complete"],
                "exitCriteria": ["policy target evaluated"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "request complete"}],
                    "exitConditions": [{"condition": "policy target evaluated"}],
                },
                "requiredEvidenceRefs": ["ev-request"],
                "producedEvidenceRefs": ["ev-rule-result"],
                "recoveryActions": ["request evidence", "escalate"],
                "ruleName": "robot_safety_gate",
                "targetNodeName": "eligible",
            },
            {
                "id": "robot-options",
                "label": "Route options",
                "type": "OPTION_SET",
                "owner": "AEGIS",
                "role": "options engine",
                "entryCriteria": ["policy result available"],
                "exitCriteria": ["operator option selected"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "policy result available"}],
                    "exitConditions": [{"condition": "operator option selected"}],
                },
                "requiredEvidenceRefs": ["ev-rule-result"],
                "producedEvidenceRefs": ["ev-selected-option"],
                "recoveryActions": ["select fallback"],
                "options": [
                    {
                        "id": "operator-escalation",
                        "label": "Escalate to operator",
                        "status": "available",
                        "confidence": 0.9,
                        "risk": 0.4,
                        "supportingEvidenceRefs": ["ev-rule-result"],
                        "opposingEvidenceRefs": [],
                        "constraints": ["requires approval"],
                        "rationale": "Human authority required before actuation.",
                        "requiredRole": "override authority",
                        "requiresApproval": True,
                        "wouldTriggerNodeId": "robot-approval",
                        "fallbackIfRejected": "robot-receipt",
                    }
                ],
            },
            {
                "id": "robot-approval",
                "label": "Operator approval",
                "type": "HUMAN_APPROVAL",
                "owner": "Dock safety lead",
                "role": "override authority",
                "entryCriteria": ["option selected"],
                "exitCriteria": ["approval recorded"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "option selected"}],
                    "exitConditions": [{"condition": "approval recorded"}],
                },
                "requiredEvidenceRefs": ["ev-selected-option"],
                "producedEvidenceRefs": ["ev-approval"],
                "recoveryActions": ["reject and seal"],
                "approverRole": "override authority",
                "authoritySource": "synthetic role matrix",
                "allowedDecisions": ["granted", "rejected"],
                "rationaleRequired": True,
            },
            {
                "id": "robot-actuation",
                "label": "Actuation release",
                "type": "ACTUATION",
                "owner": "synthetic ROS sidecar",
                "role": "control layer",
                "entryCriteria": ["approval granted"],
                "exitCriteria": ["no-op command complete"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "approval granted"}],
                    "exitConditions": [{"condition": "no-op command complete"}],
                },
                "requiredEvidenceRefs": ["ev-approval"],
                "producedEvidenceRefs": ["ev-actuation"],
                "recoveryActions": ["return to dock"],
                "assetLayer": "synthetic_robot",
                "commandSummary": "No-op supervised reroute release",
                "safeMode": True,
                "fallbackTrigger": "approval.rejected",
                "stopCondition": "receipt failed",
            },
            {
                "id": "robot-receipt",
                "label": "Seal receipt",
                "type": "RECEIPT_SEAL",
                "owner": "aegis-ledger",
                "role": "signature authority",
                "entryCriteria": ["actuation outcome available"],
                "exitCriteria": ["receipt sealed"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "actuation outcome available"}],
                    "exitConditions": [{"condition": "receipt sealed"}],
                },
                "requiredEvidenceRefs": ["ev-actuation", "ev-rule-result"],
                "producedEvidenceRefs": ["ev-receipt"],
                "recoveryActions": ["retry receipt sealing"],
                "receiptType": "synthetic_robot_decision_receipt",
                "eventSequenceRange": [1, 8],
                "previousHash": "sha256:genesis",
            },
        ],
        "transitions": [
            {"fromNodeId": "robot-request", "toNodeId": "robot-rule", "triggerEvent": "request.created"},
            {"fromNodeId": "robot-rule", "toNodeId": "robot-options", "triggerEvent": "rule.evaluated"},
            {"fromNodeId": "robot-options", "toNodeId": "robot-approval", "triggerEvent": "option.selected"},
            {"fromNodeId": "robot-approval", "toNodeId": "robot-actuation", "triggerEvent": "approval.granted"},
            {"fromNodeId": "robot-actuation", "toNodeId": "robot-receipt", "triggerEvent": "actuation.noop.completed"},
        ],
        "receiptPolicy": {"sealOnEvents": ["receipt.sealed"], "requiredFields": ["ruleVersionHash"]},
    }


def test_persisted_workflow_create_read_version_validate_and_compile():
    with _client():
        client = TestClient(app)
        create_response = client.post("/api/v1/aegis/workflows", json=_workflow_payload())

        assert create_response.status_code == 200
        created = create_response.json()
        assert created["workflow"]["id"] == "robot-action-firewall"
        assert created["workflow"]["isSynthetic"] is False
        assert created["validation"]["valid"] is True
        assert created["validation"]["ruleBindings"][0]["ruleName"] == "robot_safety_gate"
        assert created["validation"]["ruleBindings"][0]["ruleVersionHash"].startswith("sha256:")

        read_response = client.get("/api/v1/aegis/workflows/robot-action-firewall")
        versions_response = client.get("/api/v1/aegis/workflows/robot-action-firewall/versions")
        compile_response = client.post("/api/v1/aegis/workflows/robot-action-firewall/compile", json={})

        assert read_response.status_code == 200
        assert read_response.json()["currentVersionHash"].startswith("sha256:")
        assert versions_response.status_code == 200
        assert len(versions_response.json()["versions"]) == 1
        assert compile_response.status_code == 200
        compiled = compile_response.json()
        assert compiled["status"] == "compiled"
        assert compiled["activationReady"] is True
        assert compiled["compiledPolicyRefs"][0]["importTreeHash"].startswith("sha256:")
        assert compiled["evidenceContract"]["requiredEvidenceRefs"] == [
            "ev-actuation",
            "ev-approval",
            "ev-request",
            "ev-rule-result",
            "ev-selected-option",
        ]


def test_rule_workflow_usage_and_impact_test_block_target_breaking_save():
    with _client():
        client = TestClient(app)
        create_response = client.post("/api/v1/aegis/workflows", json=_workflow_payload())

        usage_response = client.get("/api/v1/aegis/rules/robot_safety_gate/workflow-usage")
        impact_response = client.post(
            "/api/v1/aegis/rules/robot_safety_gate/workflow-impact-test",
            json={
                "ruleText": """INPUT age AS NUMBER

different target
    AND age >= 18
""",
            },
        )
        save_response = client.post(
            "/api/v1/aegis/rules",
            json={
                "name": "robot_safety_gate",
                "category": "AEGIS Testing",
                "description": "Target-breaking edit",
                "ruleText": """INPUT age AS NUMBER

different target
    AND age >= 18
""",
                "requireWorkflowImpactPass": True,
            },
        )

        assert create_response.status_code == 200
        assert usage_response.status_code == 200
        usage = usage_response.json()
        assert usage["summary"]["directWorkflowDefinitions"] == 1
        assert usage["directWorkflowDefinitions"][0]["workflowId"] == "robot-action-firewall"
        assert usage["directWorkflowDefinitions"][0]["targetNodeNames"] == ["eligible"]
        assert impact_response.status_code == 200
        impact = impact_response.json()
        assert impact["passed"] is False
        assert impact["tests"][0]["status"] == "failed"
        assert any(
            diagnostic["code"] == "INVALID_RULE_TARGET"
            for diagnostic in impact["tests"][0]["diagnostics"]
        )
        assert save_response.status_code == 409
        assert save_response.json()["detail"]["impact"]["passed"] is False


def test_create_only_rule_blocks_duplicate_and_allows_new_rule():
    with _client():
        client = TestClient(app)
        duplicate_response = client.post(
            "/api/v1/aegis/rules",
            json={
                "name": "robot_safety_gate",
                "category": "AEGIS Testing",
                "description": "Duplicate create attempt",
                "ruleText": AEGIS_RULE_TEXT,
                "createOnly": True,
            },
        )
        create_response = client.post(
            "/api/v1/aegis/rules",
            json={
                "name": "new_robot_rule",
                "category": "AEGIS Testing",
                "description": "Fresh create",
                "ruleText": """INPUT score AS NUMBER

eligible
    AND score >= 1
""",
                "createOnly": True,
            },
        )
        text_response = client.get("/api/v1/aegis/rules/new_robot_rule/text")

        assert duplicate_response.status_code == 409
        assert duplicate_response.json()["detail"]["code"] == "DUPLICATE_RULE_NAME"
        assert create_response.status_code == 201
        assert create_response.json()["ruleName"] == "new_robot_rule"
        assert text_response.status_code == 200
        assert "INPUT score AS NUMBER" in text_response.json()["ruleText"]


def test_target_only_change_requires_workflow_impact_when_referenced():
    two_target_rule_text = """INPUT age AS NUMBER

eligible
    AND age >= 18

manual review required
    AND age < 18
"""
    with _client():
        client = TestClient(app)
        update_response = client.patch(
            "/api/v1/aegis/rules/robot_safety_gate",
            json={
                "name": "robot_safety_gate",
                "category": "AEGIS Testing",
                "description": "Two target policy gate.",
                "ruleText": two_target_rule_text,
                "targetNodeName": "eligible",
            },
        )
        create_response = client.post("/api/v1/aegis/workflows", json=_workflow_payload())
        blocked_response = client.patch(
            "/api/v1/aegis/rules/robot_safety_gate/target",
            json={"targetNodeName": "manual review required"},
        )
        impact_response = client.post(
            "/api/v1/aegis/rules/robot_safety_gate/workflow-impact-test",
            json={
                "ruleText": two_target_rule_text,
                "targetNodeName": "manual review required",
            },
        )
        save_response = client.patch(
            "/api/v1/aegis/rules/robot_safety_gate/target",
            json={
                "targetNodeName": "manual review required",
                "requireWorkflowImpactPass": True,
            },
        )
        detail_response = client.get("/api/v1/aegis/rules/robot_safety_gate")

        assert update_response.status_code == 200
        assert create_response.status_code == 200
        assert blocked_response.status_code == 409
        assert "impact testing" in blocked_response.json()["detail"]["message"]
        assert impact_response.status_code == 200
        assert impact_response.json()["passed"] is True
        assert save_response.status_code == 200
        assert save_response.json()["targetNodeName"] == "manual review required"
        assert detail_response.json()["targetNodeName"] == "manual review required"


def test_rule_rename_updates_workflow_rule_gate_references():
    with _client():
        client = TestClient(app)
        create_response = client.post("/api/v1/aegis/workflows", json=_workflow_payload())
        rename_response = client.patch(
            "/api/v1/aegis/rules/robot_safety_gate",
            json={
                "name": "robot_safety_gate_v2",
                "category": "AEGIS Testing",
                "description": "Renamed robot policy gate.",
                "ruleText": AEGIS_RULE_TEXT,
            },
        )
        versions_response = client.get("/api/v1/aegis/workflows/robot-action-firewall/versions")
        usage_response = client.get("/api/v1/aegis/rules/robot_safety_gate_v2/workflow-usage")

        assert create_response.status_code == 200
        assert rename_response.status_code == 200
        renamed = rename_response.json()
        assert renamed["ruleName"] == "robot_safety_gate_v2"
        assert renamed["previousRuleName"] == "robot_safety_gate"
        assert renamed["updatedWorkflowReferences"][0]["workflowId"] == "robot-action-firewall"
        assert renamed["updatedWorkflowReferences"][0]["nodeIds"] == ["robot-rule"]

        assert versions_response.status_code == 200
        versions = versions_response.json()["versions"]
        assert len(versions) == 2
        latest_definition = versions[-1]["definition"]
        rule_node = next(node for node in latest_definition["nodes"] if node["id"] == "robot-rule")
        assert rule_node["ruleName"] == "robot_safety_gate_v2"

        assert usage_response.status_code == 200
        usage = usage_response.json()
        assert usage["summary"]["directWorkflowDefinitions"] == 1
        assert usage["directWorkflowDefinitions"][0]["boundRuleNames"] == ["robot_safety_gate_v2"]


def test_persisted_workflow_update_uses_optimistic_concurrency():
    with _client():
        client = TestClient(app)
        create_response = client.post("/api/v1/aegis/workflows", json=_workflow_payload())
        original_hash = create_response.json()["workflow"]["currentVersionHash"]

        update_response = client.patch(
            "/api/v1/aegis/workflows/robot-action-firewall",
            json={
                "expectedVersionHash": original_hash,
                "title": "Robot Action Firewall v2",
                "metadata": {"changeReason": "tighten operator wording"},
            },
        )
        stale_response = client.patch(
            "/api/v1/aegis/workflows/robot-action-firewall",
            json={
                "expectedVersionHash": original_hash,
                "title": "Stale overwrite",
            },
        )

        assert update_response.status_code == 200
        assert update_response.json()["version"]["version"] == 2
        assert update_response.json()["workflow"]["title"] == "Robot Action Firewall v2"
        assert stale_response.status_code == 409
        assert "changed" in stale_response.json()["detail"]


def test_invalid_transition_returns_structured_diagnostics_and_blocks_compile():
    payload = _workflow_payload()
    payload["id"] = "invalid-robot-action-firewall"
    payload["transitions"] = [
        {"fromNodeId": "robot-request", "toNodeId": "robot-receipt", "triggerEvent": "bad.jump"},
    ]

    with _client():
        client = TestClient(app)
        create_response = client.post("/api/v1/aegis/workflows", json=payload)
        validate_response = client.post("/api/v1/aegis/workflows/invalid-robot-action-firewall/validate", json={})
        compile_response = client.post("/api/v1/aegis/workflows/invalid-robot-action-firewall/compile", json={})

        assert create_response.status_code == 200
        assert create_response.json()["validation"]["valid"] is False
        assert validate_response.status_code == 200
        diagnostics = validate_response.json()["diagnostics"]
        invalid_transition = next(item for item in diagnostics if item["code"] == "INVALID_TRANSITION")
        assert invalid_transition["severity"] == "error"
        assert invalid_transition["nodeId"] == "robot-request"
        assert invalid_transition["field"] == "transitions[0]"
        assert invalid_transition["blocksSaveVersion"] is True
        assert invalid_transition["blocksCompile"] is True
        assert compile_response.status_code == 200
        assert compile_response.json()["status"] == "compile_blocked"


def test_rule_binding_diagnostic_names_missing_rule_owner():
    payload = _workflow_payload()
    payload["id"] = "missing-import-workflow"

    with _client():
        client = TestClient(app)
        create_response = client.post("/api/v1/aegis/workflows", json=payload)
        created_hash = create_response.json()["workflow"]["currentVersionHash"]

        update_payload = deepcopy(payload)
        update_payload["nodes"][1]["ruleName"] = "missing_policy"
        update_payload["expectedVersionHash"] = created_hash
        update_response = client.patch("/api/v1/aegis/workflows/missing-import-workflow", json=update_payload)

        assert update_response.status_code == 200
        diagnostics = update_response.json()["validation"]["diagnostics"]
        rule_diagnostic = next(item for item in diagnostics if item["code"] == "RULE_NOT_FOUND")
        assert rule_diagnostic["nodeId"] == "robot-rule"
        assert rule_diagnostic["field"] == "ruleName"
        assert rule_diagnostic["ruleName"] == "missing_policy"


def test_phase4_generated_workflow_metadata_and_activation_approval_gate():
    with _client():
        client = TestClient(app)
        generate_response = client.post(
            "/api/v1/aegis/workflows/generate",
            json={
                "id": "phase4-generated-reroute",
                "title": "Generated Robot Reroute",
                "domain": "robotics",
                "ruleName": "robot_safety_gate",
                "targetNodeName": "eligible",
                "facts": {"age": 19, "obstacleConfidence": 0.72},
                "evidenceRefs": ["ev-generation-request"],
                "confidence": 0.84,
            },
        )

        assert generate_response.status_code == 200
        generated = generate_response.json()
        metadata = generated["workflow"]["metadata"]["generation"]
        assert generated["workflow"]["status"] == "generated_draft"
        assert generated["validation"]["valid"] is True
        assert metadata["source"] == "deterministic-template"
        assert metadata["generatedDraft"] is True
        assert metadata["basis"]["facts"] == ["age", "obstacleConfidence"]
        assert metadata["basis"]["ruleBasis"] == [
            {"ruleName": "robot_safety_gate", "targetNodeName": "eligible"}
        ]
        assert metadata["confidence"]["score"] == 0.84
        assert metadata["confidence"]["authorityBoundary"] == {
            "authoritativeFacts": "provenance-backed asserted or inferred facts only",
            "similarCases": "advisory-only Options Ledger memory",
        }
        assert "evidence-to-fact provenance required" in metadata["confidence"]["factors"]
        assert metadata["humanActivationApproval"]["status"] == "pending"
        assert metadata["validationResult"]["valid"] is True
        assert metadata["changeSet"]["addedNodeIds"]

        compile_response = client.post("/api/v1/aegis/workflows/phase4-generated-reroute/compile", json={})
        activate_before_approval = client.post(
            "/api/v1/aegis/workflows/phase4-generated-reroute/activate",
            json={"activatedBy": "workflow-owner"},
        )

        assert compile_response.status_code == 200
        compiled = compile_response.json()
        assert compiled["status"] == "compiled_activation_pending"
        assert compiled["activationReady"] is False
        assert compiled["factIngestionContract"]["contract"] == "aegis-evidence-fact-ledger-v1"
        assert compiled["factIngestionContract"]["authoritativeFactClasses"] == ["asserted", "inferred"]
        assert compiled["confidenceExplanation"]["authorityBoundary"]["similarCases"] == (
            "advisory-only Options Ledger memory"
        )
        assert activate_before_approval.status_code == 409
        assert "human activation approval" in activate_before_approval.json()["detail"]

        approval_response = client.post(
            "/api/v1/aegis/workflows/phase4-generated-reroute/activation-approval",
            json={
                "decision": "approved",
                "approvalId": "approval-phase4",
                "approvedBy": "workflow-owner",
                "rationale": "Synthetic fixture owner approves generated draft activation.",
            },
        )
        activate_response = client.post(
            "/api/v1/aegis/workflows/phase4-generated-reroute/activate",
            json={"activatedBy": "workflow-owner"},
        )

        assert approval_response.status_code == 200
        assert approval_response.json()["activationApproval"]["status"] == "approved"
        assert activate_response.status_code == 200
        assert activate_response.json()["status"] == "active"
        assert activate_response.json()["compileOutput"]["activationReady"] is True

        regenerate_response = client.post(
            "/api/v1/aegis/workflows/regenerate",
            json={
                "workflowId": "phase4-generated-reroute",
                "id": "phase4-regenerated-reroute",
                "title": "Regenerated Robot Reroute",
                "ruleName": "robot_safety_gate",
                "targetNodeName": "eligible",
                "facts": {"age": 20},
                "evidenceRefs": ["ev-regeneration-request"],
            },
        )

        assert regenerate_response.status_code == 200
        regenerated = regenerate_response.json()["generatedDraft"]
        assert regenerated["generationKind"] == "regenerate"
        assert regenerated["baseWorkflowId"] == "phase4-generated-reroute"
        assert regenerated["changeSet"]["addedNodeIds"]


def test_phase4_generated_workflow_with_unsafe_transition_cannot_activate():
    with _client():
        client = TestClient(app)
        generate_response = client.post(
            "/api/v1/aegis/workflows/generate",
            json={
                "id": "phase4-unsafe-generated",
                "title": "Unsafe Generated Workflow",
                "domain": "robotics",
                "ruleName": "robot_safety_gate",
                "targetNodeName": "eligible",
                "facts": {"age": 19},
                "evidenceRefs": ["ev-generation-request"],
            },
        )
        workflow = generate_response.json()["workflow"]
        nodes_by_type = {node["type"]: node for node in workflow["nodes"]}
        unsafe_payload = deepcopy(workflow)
        unsafe_payload["expectedVersionHash"] = workflow["currentVersionHash"]
        unsafe_payload["transitions"] = [
            {
                "fromNodeId": nodes_by_type["REQUEST"]["id"],
                "toNodeId": nodes_by_type["ACTUATION"]["id"],
                "triggerEvent": "unsafe.direct_actuation",
            }
        ]

        update_response = client.patch("/api/v1/aegis/workflows/phase4-unsafe-generated", json=unsafe_payload)
        approval_response = client.post(
            "/api/v1/aegis/workflows/phase4-unsafe-generated/activation-approval",
            json={"decision": "approved", "approvalId": "approval-unsafe"},
        )
        activate_response = client.post(
            "/api/v1/aegis/workflows/phase4-unsafe-generated/activate",
            json={"activatedBy": "workflow-owner"},
        )

        assert update_response.status_code == 200
        assert update_response.json()["validation"]["valid"] is False
        assert any(
            item["code"] == "INVALID_TRANSITION"
            for item in update_response.json()["validation"]["diagnostics"]
        )
        assert approval_response.status_code == 200
        assert activate_response.status_code == 409
        assert "validation" in activate_response.json()["detail"]


def test_phase4_policy_mesh_registry_exposes_required_metadata():
    with _client():
        client = TestClient(app)
        response = client.get("/api/v1/aegis/policy-modules")

        assert response.status_code == 200
        data = response.json()
        module = next(item for item in data["modules"] if item["ruleName"] == "robot_safety_gate")
        assert data["registryHash"].startswith("sha256:")
        assert module["owner"] == "AEGIS Testing"
        assert module["versionHash"].startswith("sha256:")
        assert module["importTreeHash"].startswith("sha256:")
        assert "expiry" in module
        assert module["dependencies"] == []
        assert module["compatibility"]["contract"] == "aegis-policy-module-v1"
        assert module["compatibility"]["compatible"] is True
        assert module["activationStatus"] == "active"
