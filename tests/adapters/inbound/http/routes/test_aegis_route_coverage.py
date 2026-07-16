from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from src.adapters.inbound.http.routes import aegis
from src.adapters.outbound.persistence.aegis_event_ledger_repository import (
    AegisEventSequenceError,
)
from src.adapters.outbound.persistence.aegis_workflow_repository import (
    AegisWorkflowConcurrencyError,
)
from src.domain.aegis.phase3_runtime import (
    AegisRuntimeAuthorizationError,
    AegisRuntimeStateError,
)
from src.domain.aegis.trigger_policy import (
    AegisTriggerAuthorizationError,
    AegisTriggerConflictError,
    AegisTriggerValidationError,
)
from src.domain.aegis.workflow_authoring import AegisWorkflowActivationError


class _ExplodingService:
    def __getattr__(self, _name):
        def fail(*_args, **_kwargs):
            raise LookupError("resource missing")

        return fail


def _request() -> Request:
    return Request({"type": "http", "headers": []})


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (HTTPException(status_code=418, detail="teapot"), 418),
        (AegisRuntimeAuthorizationError("denied"), 403),
        (AegisTriggerAuthorizationError("denied"), 403),
        (LookupError("missing"), 404),
        (AegisWorkflowConcurrencyError("stale"), 409),
        (AegisTriggerConflictError("conflict"), 409),
        (AegisWorkflowActivationError("inactive"), 409),
        (AegisEventSequenceError("sequence"), 409),
        (AegisRuntimeStateError("state"), 409),
        (AegisTriggerValidationError("invalid"), 400),
        (ValueError("invalid"), 400),
        (RuntimeError("internal"), 500),
    ],
)
def test_error_mapping_is_stable(error, status_code):
    mapped = aegis._map_error(error)

    assert mapped.status_code == status_code
    if status_code == 500:
        assert mapped.detail == "Unexpected AEGIS workflow runtime error"


def test_autonomy_payload_supports_direct_and_bulk_assignments(monkeypatch):
    direct = MagicMock(
        side_effect=lambda payload: {"assignment": {"agentId": payload.get("agentId")}}
    )
    monkeypatch.setattr(aegis, "assign_autonomy_level", direct)
    monkeypatch.setattr(
        aegis,
        "list_autonomy_levels",
        lambda: {"certifiedConfidenceThreshold": 0.9, "assignments": []},
    )

    assert aegis._assign_autonomy_payload({"agentId": "direct"})["assignment"]["agentId"] == "direct"
    bulk = aegis._assign_autonomy_payload(
        {
            "rules": [
                {"subjectType": "global", "level": "manual"},
                {
                    "subjectType": "workflow",
                    "subjectId": "claims",
                    "level": "supervised_autonomy",
                    "updatedBy": "operator",
                    "comment": "reviewed",
                },
                {"subjectType": "agent", "id": "agent-1", "level": "certified_autonomy"},
            ]
        }
    )
    assert bulk["assignment"]["agentId"] == "agent-1"
    assert direct.call_args_list[2].args[0]["agentId"] == "workflow:claims"
    with pytest.raises(ValueError, match="must be objects"):
        aegis._assign_autonomy_payload({"rules": ["invalid"]})
    with pytest.raises(ValueError, match="require subjectId"):
        aegis._autonomy_rule_assignment_payload({"subjectType": "workflow"})


def test_autonomy_contract_normalizes_subjects_thresholds_and_defaults(monkeypatch):
    monkeypatch.setattr(aegis, "_utc_now", lambda: "2026-07-16T00:00:00Z")
    data = {
        "certifiedConfidenceThreshold": 0.87,
        "assignments": [
            {
                "agentId": "global",
                "assignedLevel": "manual",
                "constraints": {"minConfidenceThreshold": "invalid"},
            },
            {
                "agentId": "workflow:claims",
                "assignedLevel": "supervised_autonomy",
                "assignedBy": "owner",
                "rationale": "controlled",
                "constraints": {"minConfidenceThreshold": "0.75", "requiresAuthority": False},
            },
            {"agentId": "agent-1", "assignedLevel": "certified_autonomy", "constraints": "invalid"},
            "ignored",
        ],
    }

    result = aegis._autonomy_levels_contract(data)

    assert result["generatedAt"] == "2026-07-16T00:00:00Z"
    assert result["source"] == "platform_live"
    assert len(result["rules"]) == 3
    global_rule, workflow_rule, agent_rule = result["rules"]
    assert "subjectId" not in global_rule
    assert global_rule["minConfidenceThreshold"] == 0.87
    assert workflow_rule["subjectId"] == "claims"
    assert workflow_rule["requiresAuthority"] is False
    assert agent_rule["subjectId"] == "agent-1"
    assert agent_rule["requiresEvidence"] is True
    assert all(rule["policyVersionHash"].startswith("sha256:") for rule in result["rules"])


@pytest.mark.asyncio
async def test_update_autonomy_maps_invalid_bulk_payload():
    with pytest.raises(HTTPException) as caught:
        await aegis.update_autonomy_level({"rules": ["invalid"]})
    assert caught.value.status_code == 400


@pytest.mark.parametrize(
    "invoke",
    [
        lambda: aegis.list_workflows(),
        lambda: aegis.create_workflow({"id": "custom"}),
        lambda: aegis.generate_workflow({}),
        lambda: aegis.regenerate_workflow({}),
        lambda: aegis.extend_workflow({}),
        lambda: aegis.get_workflow("custom"),
        lambda: aegis.update_workflow("custom", {}),
        lambda: aegis.approve_workflow_activation("custom", {}),
        lambda: aegis.activate_workflow("custom", {}),
        lambda: aegis.list_workflow_versions("custom"),
        lambda: aegis.create_workflow_version("custom", {}),
        lambda: aegis.get_workflow_version("custom", "v1"),
        lambda: aegis.validate_workflow("custom", {}),
        lambda: aegis.compile_workflow("custom", {}),
    ],
)
@pytest.mark.asyncio
async def test_authoring_route_failures_are_mapped(monkeypatch, invoke):
    def fail(_operation):
        raise RuntimeError("authoring failed")

    monkeypatch.setattr(aegis, "_with_authoring_service", fail)
    with pytest.raises(HTTPException) as caught:
        await invoke()
    assert caught.value.status_code == 500


@pytest.mark.asyncio
async def test_workflow_listing_merges_persisted_and_synthetic(monkeypatch):
    monkeypatch.setattr(aegis, "_with_authoring_service", lambda operation: [{"id": "persisted"}])
    runtime = MagicMock()
    runtime.list_workflows.return_value = {"workflows": [{"id": "synthetic"}]}
    monkeypatch.setattr(aegis, "_runtime", lambda: runtime)

    assert await aegis.list_workflows() == {
        "workflows": [{"id": "persisted"}, {"id": "synthetic"}]
    }


@pytest.mark.asyncio
async def test_synthetic_workflow_authoring_contracts(monkeypatch):
    runtime = MagicMock()
    runtime.get_workflow.return_value = {"id": "synthetic", "version": "v1"}
    monkeypatch.setattr(aegis, "_runtime", lambda: runtime)
    monkeypatch.setattr(aegis, "_is_synthetic_workflow", lambda _workflow_id: True)

    assert await aegis.create_workflow({"id": "synthetic"}) == {
        "id": "synthetic",
        "version": "v1",
    }
    assert await aegis.list_workflow_versions("synthetic") == {
        "workflowId": "synthetic",
        "versions": [{"id": "synthetic", "version": "v1"}],
    }
    assert await aegis.get_workflow_version("synthetic", "v1") == {
        "id": "synthetic",
        "version": "v1",
    }

    for operation in (
        lambda: aegis.update_workflow("synthetic", {}),
        lambda: aegis.approve_workflow_activation("synthetic", {}),
        lambda: aegis.activate_workflow("synthetic", {}),
        lambda: aegis.create_workflow_version("synthetic", {}),
    ):
        with pytest.raises(HTTPException) as caught:
            await operation()
        assert caught.value.status_code == 400

    with pytest.raises(HTTPException) as caught:
        await aegis.get_workflow_version("synthetic", "missing")
    assert caught.value.status_code == 404


@pytest.mark.parametrize(
    "invoke",
    [
        lambda: aegis.create_workflow_run({}),
        lambda: aegis.get_workflow_run("run"),
        lambda: aegis.append_workflow_event("run", {}),
        lambda: aegis.transition_workflow_run("run", {}),
        lambda: aegis.get_workflow_timeline("run"),
        lambda: aegis.get_workflow_options("run"),
        lambda: aegis.select_workflow_option("run", "option", {}),
        lambda: aegis.decide_workflow_approval("run", "approval", {}),
        lambda: aegis.get_workflow_receipt("run"),
        lambda: aegis.get_workflow_dossier("run"),
        lambda: aegis.evaluate_aegis_gate({}),
    ],
)
@pytest.mark.asyncio
async def test_synthetic_runtime_route_failures_are_mapped(monkeypatch, invoke):
    monkeypatch.setattr(aegis, "_runtime", lambda: _ExplodingService())
    with pytest.raises(HTTPException) as caught:
        await invoke()
    assert caught.value.status_code == 404


@pytest.mark.parametrize(
    "invoke",
    [
        lambda db: aegis.get_agent_risk_heatmap(db=db),
        lambda db: aegis.create_action_proposal({}, db=db),
        lambda db: aegis.get_action_run("run", db=db),
        lambda db: aegis.evaluate_action_preflight("run", {}, db=db),
        lambda db: aegis.evaluate_action_gate("run", {}, db=db),
        lambda db: aegis.get_action_options("run", db=db),
        lambda db: aegis.select_action_option("run", "option", {}, db=db),
        lambda db: aegis.decide_action_approval("run", "approval", {}, db=db),
        lambda db: aegis.request_action_evidence("run", {}, db=db),
        lambda db: aegis.ingest_action_evidence_facts("run", {}, db=db),
        lambda db: aegis.get_action_evidence_facts("run", db=db),
        lambda db: aegis.request_action_override("run", {}, db=db),
        lambda db: aegis.decide_action_override("run", "override", {}, db=db),
        lambda db: aegis.trigger_action_fallback("run", {}, db=db),
        lambda db: aegis.seal_action_receipt("run", {}, db=db),
        lambda db: aegis.get_action_receipt("run", db=db),
        lambda db: aegis.export_action_passport("run", db=db),
        lambda db: aegis.get_action_dossier("run", db=db),
        lambda db: aegis.evaluate_action_sla("run", {}, db=db),
        lambda db: aegis.get_action_counterfactuals("run", db=db),
        lambda db: aegis.get_action_proposal_counterfactuals("proposal", db=db),
        lambda db: aegis.replay_policy("policy", {}, db=db),
        lambda db: aegis.get_action_similar_cases("run", db=db),
    ],
)
@pytest.mark.asyncio
async def test_phase3_route_failures_are_mapped(monkeypatch, invoke):
    monkeypatch.setattr(aegis, "_phase3_service", lambda db: _ExplodingService())
    with pytest.raises(HTTPException) as caught:
        await invoke(object())
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_action_options_success_contract(monkeypatch):
    service = MagicMock()
    service.get_action_run.return_value = {"allowedActions": ["wait"]}
    service.export_passport.return_value = {
        "snapshot": {"snapshot": {"options": {"selected": "wait"}}}
    }
    monkeypatch.setattr(aegis, "_phase3_service", lambda db: service)

    assert await aegis.get_action_options("run", db=object()) == {
        "runId": "run",
        "options": {"selected": "wait"},
        "allowedActions": ["wait"],
    }


@pytest.mark.parametrize(
    "invoke",
    [
        lambda db, session: aegis.list_trigger_policies(db=db, session_service=session),
        lambda db, session: aegis.create_trigger_policy({}, _request(), db=db, session_service=session),
        lambda db, session: aegis.trigger_from_outcome(
            {}, _request(), db=db, platform_db=object(), session_service=session
        ),
        lambda db, session: aegis.trigger_direct(
            {}, _request(), db=db, platform_db=object(), session_service=session
        ),
    ],
)
@pytest.mark.asyncio
async def test_trigger_policy_route_failures_are_mapped(monkeypatch, invoke):
    monkeypatch.setattr(
        aegis,
        "_trigger_policy_service",
        lambda *args, **kwargs: _ExplodingService(),
    )
    with pytest.raises(HTTPException) as caught:
        await invoke(object(), object())
    assert caught.value.status_code == 404


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"missing_evidence": 1}, "Missing evidence"),
        ({"receipt_failures": 1}, "Receipt signer failures"),
        ({"replay_drift": 1}, "Replay drift"),
        ({"blocks": 1}, "Policy blocks"),
        ({"escalations": 1}, "Escalations"),
        ({"overrides": 1}, "Operator overrides"),
        ({"risk_score": 70}, "High residual risk"),
        ({}, "No review driver"),
    ],
)
def test_risk_heatmap_top_driver_precedence(kwargs, expected):
    values = dict(
        blocks=0,
        escalations=0,
        overrides=0,
        missing_evidence=0,
        receipt_failures=0,
        replay_drift=0,
        risk_score=0,
    )
    values.update(kwargs)
    assert aegis._risk_heatmap_top_driver(**values) == expected


@pytest.mark.parametrize(
    ("row", "action"),
    [
        ({"missingEvidence": 1, "receiptFailures": 0, "replayDrift": 0, "blocks": 0}, "repair_evidence"),
        ({"missingEvidence": 0, "receiptFailures": 1, "replayDrift": 0, "blocks": 0}, "retry_signer"),
        ({"missingEvidence": 0, "receiptFailures": 0, "replayDrift": 1, "blocks": 0}, "route_regulator_review"),
        ({"missingEvidence": 0, "receiptFailures": 0, "replayDrift": 0, "blocks": 0}, "inspect_hash"),
    ],
)
def test_risk_heatmap_review_actions(row, action):
    assert aegis._risk_heatmap_review_action(row)["actionType"] == action


def test_risk_heatmap_row_maps_live_signals():
    row = aegis._risk_heatmap_contract_row(
        {
            "agentId": "agent",
            "runId": "run",
            "status": "approval_required",
            "latestEventType": "override.granted",
            "riskBand": "high",
            "riskScore": 80,
            "slaState": "escalated",
            "evidenceCompleteness": {"requiredRefs": 3, "hashedRefs": 1},
        }
    )

    assert row["blocks"] == 1
    assert row["escalations"] == 1
    assert row["overrides"] == 1
    assert row["missingEvidence"] == 2
    assert row["replayDrift"] == 1


@pytest.mark.parametrize(
    ("group", "missing", "expected"),
    [
        ("newly_denied", [], "route_regulator_review"),
        ("newly_escalated", [], "route_insurer_review"),
        ("unchanged", [], "inspect_hash"),
        ("unchanged", ["evidence"], "repair_evidence"),
    ],
)
def test_policy_replay_recovery_actions(group, missing, expected):
    assert aegis._policy_replay_recovery_action(group, missing)["actionType"] == expected


def test_policy_replay_contract_maps_groups_and_defaults(monkeypatch):
    monkeypatch.setattr(aegis, "_utc_now", lambda: "2026-07-16T00:00:00Z")
    result = aegis._policy_replay_contract(
        {
            "source": "ledger",
            "policy": {},
            "groups": {
                "newlyAllowed": [{"snapshotId": "snapshot-one", "decision": "allow"}],
                "newlyDenied": [{"snapshotId": "snapshot-two", "decision": "deny"}],
                "newlyEscalated": [{"snapshotId": "snapshot-three", "decision": "escalate"}],
                "evidenceInsufficient": [
                    {"snapshotId": "snapshot-four", "decision": "evidence_insufficient"}
                ],
                "ignored": ["not a mapping"],
            },
        }
    )

    assert result["policyGraphSource"] == "ledger"
    assert result["policyVersionHash"].startswith("sha256:")
    assert [row["group"] for row in result["rows"]] == [
        "newly_allowed",
        "newly_denied",
        "newly_escalated",
        "evidence_insufficient",
    ]
    assert result["rows"][-1]["replayedOutcome"] == "EVIDENCE_INSUFFICIENT"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("allowed", "ALLOW"),
        ("denied", "DENY"),
        ("modified", "MODIFY"),
        ("escalated", "ESCALATE"),
        ("fallback", "FALLBACK"),
        ("approval-required", "REQUIRE_APPROVAL"),
        ("evidence_required", "REQUIRE_EVIDENCE"),
        ("unknown", "REQUIRE_APPROVAL"),
    ],
)
def test_gate_decision_contract(value, expected):
    assert aegis._gate_decision_contract(value) == expected


def test_identifier_title_and_policy_registry_hash():
    assert aegis._title_from_identifier("sample_item") == "Sample Item"
    assert aegis._title_from_identifier("---") == "Policy Replay Snapshot"
    assert aegis._policy_registry_hash(
        [
            {
                "moduleId": "module",
                "versionHash": "version",
                "importTreeHash": "imports",
                "activationStatus": "active",
            }
        ]
    ).startswith("sha256:")


class _DbContext:
    def __init__(self):
        self.db = object()
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        return self.db

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_policy_modules_skip_unnamed_rules_and_report_missing_files(monkeypatch):
    context = _DbContext()
    service = MagicMock()
    service.list_rules.return_value = [
        {},
        {"name": "policy-one", "category": "owner", "description": "description"},
    ]
    service.get_latest_rule_file.side_effect = LookupError("missing file")
    monkeypatch.setattr(aegis, "get_aegis_db", lambda: context)
    monkeypatch.setattr(aegis, "_rule_service", lambda db: service)

    result = await aegis.list_policy_modules()

    assert len(result["modules"]) == 1
    assert result["modules"][0]["activationStatus"] == "blocked"
    assert result["modules"][0]["compatibility"]["validationStatus"] == "missing_rule_file"
    assert context.closed is True


@pytest.mark.asyncio
async def test_policy_module_failures_are_mapped_and_context_is_closed(monkeypatch):
    context = _DbContext()
    service = MagicMock()
    service.list_rules.side_effect = RuntimeError("database failed")
    monkeypatch.setattr(aegis, "get_aegis_db", lambda: context)
    monkeypatch.setattr(aegis, "_rule_service", lambda db: service)

    with pytest.raises(HTTPException) as caught:
        await aegis.list_policy_modules()

    assert caught.value.status_code == 500
    assert context.closed is True
