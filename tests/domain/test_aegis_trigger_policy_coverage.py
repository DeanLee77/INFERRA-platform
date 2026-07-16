from unittest.mock import MagicMock

import pytest

import src.domain.aegis.trigger_policy as trigger_policy_module
from src.domain.aegis.trigger_policy import (
    AegisTriggerConflictError,
    AegisTriggerPolicyService,
    AegisTriggerValidationError,
    _fact_source_filter,
    _filter_facts,
    _has_path,
    _normalise_constraints,
    _normalise_mode,
    _normalise_outcome_value,
    _normalise_source,
    _normalise_target,
    _snapshot_matches_current,
    _source_event_audit_summary,
    _source_result_matches_policy,
)


@pytest.fixture
def service_parts():
    repository = MagicMock()
    rule_service = MagicMock()
    session_service = MagicMock()
    phase3_service = MagicMock()
    service = AegisTriggerPolicyService(
        repository,
        rule_service,
        session_service,
        phase3_service,
    )
    return service, repository, rule_service


def _policy(*, mode="automatic", source_type="rule_set", outcome=None):
    payload = {"when": {}}
    if outcome is not None:
        payload["when"]["outcome"] = outcome
    source = (
        {"type": "direct", "eventType": "direct_request"}
        if source_type == "direct"
        else {"type": "rule_set", "ruleName": "source-rule"}
    )
    return {
        "policyId": "policy-1",
        "version": "v1",
        "policyHash": "sha256:policy",
        "status": "active",
        "mode": mode,
        "source": source,
        "target": {
            "type": "action",
            "workflowId": "workflow",
            "action": {"kind": "notify", "target": "operator"},
        },
        "constraints": {
            "maxDepth": 4,
            "confidenceThreshold": 0.0,
            "requiredEvidenceRefs": [],
            "factSourceFilter": ["ASSERTED", "INFERRED"],
        },
        "payload": payload,
    }


def test_policy_creation_rejects_status_and_active_source_target_conflicts(service_parts):
    service, repository, _ = service_parts

    with pytest.raises(AegisTriggerValidationError, match="status must be"):
        service.create_policy({"status": "draft"})

    repository.find_active_conflict.return_value = {"policyId": "existing"}
    with pytest.raises(AegisTriggerConflictError, match="already governs"):
        service.create_policy(
            {
                "policyId": "conflicting",
                "source": {"type": "direct", "eventType": "manual"},
                "target": {
                    "type": "action",
                    "action": {"kind": "notify", "target": "operator"},
                },
            }
        )

    repository.list_policies.return_value = [{"policyId": "one"}]
    assert service.list_policies(status="inactive") == {
        "policies": [{"policyId": "one"}]
    }
    repository.list_policies.assert_called_once_with(status="inactive")


def test_trigger_entrypoints_validate_source_results_and_policy_source_type(service_parts):
    service, repository, _ = service_parts
    repository.get_policy.return_value = _policy()

    with pytest.raises(AegisTriggerValidationError, match="sourceResult is required"):
        service.trigger_from_outcome({"policyId": "policy-1"})

    with pytest.raises(AegisTriggerValidationError, match="does not match"):
        service.trigger_from_outcome(
            {
                "policyId": "policy-1",
                "sourceResult": {"ruleName": "different-rule"},
            }
        )

    with pytest.raises(AegisTriggerValidationError, match="direct-source policy"):
        service.trigger_direct({"policyId": "policy-1"})


def test_require_policy_reports_missing_unknown_and_inactive_policies(service_parts):
    service, repository, _ = service_parts

    with pytest.raises(AegisTriggerValidationError, match="policyId is required"):
        service._require_policy({})

    repository.get_policy.return_value = None
    with pytest.raises(LookupError, match="missing"):
        service._require_policy({"policyId": "missing"})

    repository.get_policy.return_value = {"policyId": "inactive", "status": "inactive"}
    with pytest.raises(AegisTriggerValidationError, match="not active"):
        service._require_policy({"policyId": "inactive"})


def test_rule_set_target_validation_requires_an_existing_target_node(service_parts):
    service, _, rule_service = service_parts
    parser = MagicMock()
    parser.get_node_set.return_value.get_node_dictionary.return_value = {"existing": object()}
    rule_service.build_rule_set_parser.return_value = parser
    source = {"type": "direct", "eventType": "manual"}

    with pytest.raises(AegisTriggerValidationError, match="targetNodeName"):
        service._validate_rule_targets(
            source,
            {"type": "rule_set", "ruleName": "target-rule", "targetNodeName": ""},
        )

    with pytest.raises(LookupError, match="does not exist"):
        service._validate_rule_targets(
            source,
            {
                "type": "rule_set",
                "ruleName": "target-rule",
                "targetNodeName": "missing",
            },
        )


def test_evaluate_trigger_covers_non_execution_modes_and_execution_failure(
    service_parts,
    monkeypatch,
):
    service, repository, _ = service_parts
    repository.get_receipt_by_idempotency.return_value = None
    record = MagicMock(side_effect=lambda **kwargs: kwargs)
    monkeypatch.setattr(service, "_record_receipt", record)
    actor = {"kind": "system", "id": "runtime", "role": "workflow runtime"}

    with pytest.raises(AegisTriggerValidationError, match="idempotencyKey is required"):
        service._evaluate_trigger(
            policy=_policy(),
            body={},
            actor=actor,
            event_type="trigger.outcome.completed",
            source_event={},
            owner_id=None,
        )

    not_applicable = service._evaluate_trigger(
        policy=_policy(outcome=True),
        body={"idempotencyKey": "condition-miss"},
        actor=actor,
        event_type="trigger.outcome.completed",
        source_event={"outcome": False},
        owner_id=None,
    )
    assert not_applicable["decision"] == "not_applicable"

    recommended = service._evaluate_trigger(
        policy=_policy(mode="recommend_only"),
        body={"idempotencyKey": "recommend"},
        actor=actor,
        event_type="trigger.direct.requested",
        source_event={},
        owner_id=None,
    )
    assert recommended["decision"] == "recommended"

    approval = service._evaluate_trigger(
        policy=_policy(mode="human_approval_required"),
        body={"idempotencyKey": "approval"},
        actor=actor,
        event_type="trigger.direct.requested",
        source_event={},
        owner_id=None,
    )
    assert approval["status"] == "waiting_for_approval"
    assert approval["approval_state"] == {
        "state": "required",
        "requiredRole": "override authority",
        "reason": "Trigger policy requires human approval before downstream execution.",
    }

    monkeypatch.setattr(
        service,
        "_execute_target",
        MagicMock(side_effect=RuntimeError("downstream unavailable")),
    )
    failed = service._evaluate_trigger(
        policy=_policy(),
        body={"idempotencyKey": "failure"},
        actor=actor,
        event_type="trigger.direct.requested",
        source_event={},
        owner_id=None,
    )
    assert failed["decision"] == "execution_failed"
    assert failed["execution"] == {
        "status": "failed",
        "error": "downstream unavailable",
    }


def test_guardrails_cover_confidence_evidence_and_snapshot_mismatch(
    service_parts,
    monkeypatch,
):
    service, _, _ = service_parts

    confidence_policy = _policy()
    confidence_policy["constraints"]["confidenceThreshold"] = 0.8
    assert service._guardrail_decision(
        confidence_policy,
        {"confidence": 0.4},
        {},
    )["reason"] == "confidence_below_threshold"

    evidence_policy = _policy()
    evidence_policy["constraints"]["requiredEvidenceRefs"] = ["ev-required"]
    evidence = service._guardrail_decision(evidence_policy, {}, {})
    assert evidence == {
        "state": "blocked",
        "reason": "missing_required_evidence",
        "missingEvidenceRefs": ["ev-required"],
    }

    monkeypatch.setattr(trigger_policy_module, "_snapshot_matches_current", lambda _: False)
    snapshot = service._guardrail_decision(
        _policy(),
        {"featureFlagSnapshot": {"auth_enabled": False}},
        {},
    )
    assert snapshot == {
        "state": "blocked",
        "reason": "feature_flag_snapshot_mismatch",
        "snapshotKeys": ["auth_enabled"],
    }


def test_normalizers_reject_invalid_shapes_and_preserve_optional_contract_fields():
    with pytest.raises(AegisTriggerValidationError, match="mode must be"):
        _normalise_mode("unbounded")
    with pytest.raises(AegisTriggerValidationError, match="source.type"):
        _normalise_source({"source": {"type": "queue"}})
    with pytest.raises(AegisTriggerValidationError, match="sources require ruleName"):
        _normalise_source({"source": {"type": "rule_set"}})
    with pytest.raises(AegisTriggerValidationError, match="target.type"):
        _normalise_target({"target": {"type": "queue"}})
    with pytest.raises(AegisTriggerValidationError, match="targets require ruleName"):
        _normalise_target({"target": {"type": "rule_set"}})
    with pytest.raises(AegisTriggerValidationError, match="action.kind"):
        _normalise_target({"target": {"type": "action", "action": {"kind": "notify"}}})

    target = _normalise_target(
        {
            "target": {
                "type": "rule_set",
                "ruleName": "target-rule",
                "targetNodeName": "eligible",
                "ontologyProfile": "clinical",
                "ontologyFlags": {"enabled": True},
            }
        }
    )
    assert target["ontologyProfile"] == "clinical"
    assert target["ontologyFlags"] == {"enabled": True}

    constraints = _normalise_constraints(
        {"constraints": {"approvalRole": "safety officer"}}
    )
    assert constraints["approvalRole"] == "safety officer"


def test_graph_outcome_audit_and_fact_helpers_cover_scalar_fallbacks(monkeypatch):
    assert _has_path(
        [("a", "b"), ("a", "c"), ("c", "b")],
        "a",
        "missing",
    ) is False
    assert _source_result_matches_policy(
        {"source": {"type": "direct"}},
        {"ruleName": "source-rule"},
    ) is False
    assert _normalise_outcome_value(" YES ") == "yes"

    summary = _source_event_audit_summary(
        {
            "ruleName": "source-rule",
            "evidenceRefs": ["ev-1"],
            "featureFlagSnapshot": {"auth_enabled": False},
            "facts": {
                "plain": 1,
                "semantic": {"value": "context", "source": "semantic"},
            },
        }
    )
    assert summary["evidenceRefs"] == ["ev-1"]
    assert summary["featureFlagSnapshot"]["keys"] == ["auth_enabled"]
    assert summary["factSummary"] == {
        "count": 2,
        "sourceCounts": {"ASSERTED": 1, "SEMANTIC": 1},
    }

    facts = _filter_facts(
        {
            "": "ignored",
            "plain": 2,
            "learned": {"value": 3, "source": "LEARNED"},
        },
        ["ASSERTED"],
    )
    assert facts == {
        "plain": {"value": 2, "source": "ASSERTED", "valueType": "INTEGER"}
    }
    assert _fact_source_filter({"factSourceFilter": "ASSERTED"}) == [
        "ASSERTED",
        "INFERRED",
    ]

    flags = MagicMock()
    flags.snapshot.return_value = {"auth_enabled": True, "layered_memory": True}
    monkeypatch.setattr(trigger_policy_module, "get_feature_flags", MagicMock(return_value=flags))
    assert _snapshot_matches_current({"auth_enabled": True}) is True
    assert _snapshot_matches_current({"auth_enabled": False}) is False
