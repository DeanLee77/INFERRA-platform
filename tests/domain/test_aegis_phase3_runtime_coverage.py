from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.domain.aegis import phase3_runtime as runtime


def _service(monkeypatch):
    repository = MagicMock()
    repository.append_event.return_value = {"event": {"eventId": "event-1"}}
    service = runtime.AegisPhase3RuntimeService(repository)
    monkeypatch.setattr(service, "_require_action", MagicMock())
    monkeypatch.setattr(service, "_pre_state", lambda _run_id: {"runStatus": "before"})
    monkeypatch.setattr(
        service,
        "get_action_run",
        lambda _run_id: {
            "run": {"runId": _run_id, "status": "modified"},
            "events": [],
            "allowedActions": [],
        },
    )
    return service, repository


def _snapshot():
    payload = {
        "run": {"runId": "run-1", "status": "sealed"},
        "events": [],
        "receipt": {},
        "policy": {},
        "proposal": {},
        "sectionHashes": {},
        "snapshotHash": "snapshot-hash",
    }
    return {
        "snapshotId": "snapshot-1",
        "snapshotHash": "snapshot-hash",
        "eventSequenceRange": [1, 1],
        "snapshot": payload,
    }


def test_option_selection_evidence_request_and_invalid_decisions(monkeypatch):
    service, repository = _service(monkeypatch)

    selected = service.select_option(
        "run-1",
        "modify",
        {
            "requiresApproval": True,
            "selectionRationale": "safer",
            "rejectedOptionIds": ["allow"],
            "evidenceRefs": ["ev-1"],
        },
    )
    assert selected["optionSet"]["selectedOptionId"] == "modify"
    assert selected["optionSet"]["requiresApproval"] is True
    assert repository.append_event.call_args.kwargs["payload"]["runStatus"] == (
        "approval_required"
    )

    with pytest.raises(ValueError, match="granted or rejected"):
        service.decide_approval("run-1", "approval-1", {"decision": "maybe"})
    with pytest.raises(ValueError, match="granted or rejected"):
        service.decide_override("run-1", "override-1", {"decision": "maybe"})

    requested = service.request_evidence(
        "run-1",
        {
            "requestId": "request-1",
            "requiredEvidenceRefs": ["ev-1"],
            "reason": "needed",
        },
    )
    assert requested["evidenceRequest"]["status"] == "requested"
    assert requested["evidenceRequest"]["actor"]["role"] == "operator"


def test_create_proposal_accepts_top_level_autonomy_fields(monkeypatch):
    service, repository = _service(monkeypatch)
    repository.create_workflow_run.return_value = {"runId": "run-1"}

    result = service.create_action_proposal(
        {
            "proposalId": "proposal-1",
            "runId": "run-1",
            "autonomyLevel": "supervised_autonomy",
            "riskScore": 42,
            "confidence": 0.91,
        }
    )

    policy = result["actionProposal"]["autonomyPolicy"]
    assert policy == {
        "level": "supervised_autonomy",
        "riskScore": 42,
        "confidence": 0.91,
    }


def test_evidence_fact_ingestion_rejects_empty_and_unproven_authority(monkeypatch):
    service, _repository = _service(monkeypatch)
    monkeypatch.setattr(service, "_require_run", lambda _run_id: {"runId": _run_id})

    with pytest.raises(ValueError, match="at least one"):
        service.ingest_evidence_facts("run-1", {})
    with pytest.raises(ValueError, match="require source refs"):
        service.ingest_evidence_facts(
            "run-1",
            {"facts": [{"factName": "unsafe", "value": True}]},
        )


def test_dossier_invalid_format_and_sla_states(monkeypatch):
    service, repository = _service(monkeypatch)
    monkeypatch.setattr(service, "_materialized_snapshot", lambda _run_id: _snapshot())
    with pytest.raises(ValueError, match="format must"):
        service.get_dossier("run-1", "xml")

    repository.get_latest_action_proposal.return_value = {}
    repository.list_events.return_value = []
    monkeypatch.setattr(service, "_require_run", lambda _run_id: {"status": "proposed"})
    with pytest.raises(ValueError, match="requires deadline"):
        service.evaluate_sla("run-1", {})

    cases = [
        ("2026-01-01T00:00:00Z", "2025-12-31T23:50:00Z", "met"),
        ("2026-01-01T00:00:00Z", "2025-12-31T23:59:00Z", "warning"),
        ("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "breached"),
        ("2026-01-01T00:00:00Z", "2026-01-01T00:06:00Z", "escalated"),
    ]
    for deadline, now, expected in cases:
        result = service.evaluate_sla(
            "run-1",
            {"deadline": deadline, "now": now, "warningMinutes": 2, "escalationMinutes": 5},
        )
        assert result["sla"]["state"] == expected


def test_heatmap_skips_deleted_runs_and_replay_skips_invalid_snapshots(monkeypatch):
    service, repository = _service(monkeypatch)
    repository.list_workflow_runs.return_value = [{"runId": "missing"}]
    repository.get_latest_action_proposal.side_effect = LookupError("gone")
    assert service.get_agent_risk_heatmap()["rows"] == []

    replay = service.replay_policy(
        "policy-1",
        {
            "snapshots": [
                "invalid",
                {
                    "snapshotId": "one",
                    "previousDecision": "allowed",
                    "facts": {"obstacleClassificationConfidence": 0.95},
                    "evidenceRefs": ["ev-dock-clearance"],
                    "overrideAuthorityPresent": True,
                },
            ]
        },
    )
    assert replay["summary"]["unchanged"] == 1


def test_counterfactual_lookup_and_all_blocker_categories(monkeypatch):
    service, repository = _service(monkeypatch)
    repository.get_run_id_for_proposal.return_value = None
    with pytest.raises(LookupError, match="was not found"):
        service.get_counterfactuals_for_proposal("missing")

    run = {
        "runId": "run-1",
        "workflowId": "robot-action-firewall",
        "status": "approval_required",
        "facts": {},
        "policyHashes": {"ruleVersionHash": "old"},
    }
    proposal = {
        "facts": {"advisory": "value"},
        "evidenceRefs": ["ev-present"],
        "evidenceHashes": {},
        "policyHashes": {},
        "gateDecision": {
            "requiredFacts": ["missing", "advisory"],
            "requiredEvidenceRefs": ["ev-missing", "ev-present"],
            "requiredPolicyVersions": {"ruleVersionHash": "new"},
            "thresholds": [
                {"id": "confidence", "currentValue": 0.5, "requiredValue": 0.9}
            ],
            "requiredApprovals": [],
            "fallbackRequired": True,
            "authorityRequired": "override authority",
        },
        "approval": {},
        "fallback": {},
    }
    events = [
        {
            "type": "authorization.denied",
            "actor": {"role": "operator"},
            "payload": {},
            "evidenceRefs": [],
        }
    ]
    monkeypatch.setattr(service, "_require_run", lambda _run_id: run)
    repository.get_latest_action_proposal.return_value = proposal
    repository.list_events.return_value = events

    result = service.get_counterfactuals("run-1")
    categories = set(result["summary"]["categories"])
    assert categories == {
        "approval",
        "authority",
        "evidence_hash",
        "fact_provenance",
        "fallback_availability",
        "missing_evidence",
        "missing_fact",
        "policy_version",
        "threshold",
    }


def test_similar_case_scope_require_run_and_action_denials(monkeypatch):
    repository = MagicMock()
    service = runtime.AegisPhase3RuntimeService(repository)
    monkeypatch.setattr(
        service,
        "_require_run",
        lambda _run_id: {"runId": _run_id, "workflowId": "different"},
    )
    with pytest.raises(ValueError, match="scoped"):
        service.find_similar_cases("run-1")

    repository.get_workflow_run.return_value = None
    service = runtime.AegisPhase3RuntimeService(repository)
    with pytest.raises(LookupError, match="was not found"):
        service._require_run("missing")

    append_denial = MagicMock()
    monkeypatch.setattr(service, "_append_denial", append_denial)
    monkeypatch.setattr(
        service,
        "get_action_run",
        lambda _run_id: {"run": {"status": "sealed"}, "allowedActions": []},
    )
    with pytest.raises(runtime.AegisRuntimeStateError):
        service._require_action(
            "run-1",
            "gate.evaluate",
            {"role": "policy gate"},
            {},
        )
    assert append_denial.call_args.kwargs["event_type"] == "runtime.action.denied"

    monkeypatch.setattr(
        service,
        "get_action_run",
        lambda _run_id: {
            "run": {"status": "proposed"},
            "allowedActions": ["gate.evaluate"],
        },
    )
    with pytest.raises(runtime.AegisRuntimeAuthorizationError):
        service._require_action(
            "run-1",
            "gate.evaluate",
            {"role": "operator"},
            {},
        )
    assert append_denial.call_args.kwargs["event_type"] == "authorization.denied"


def test_authoritative_gate_failure_reasons(monkeypatch):
    repository = MagicMock()
    service = runtime.AegisPhase3RuntimeService(repository)
    monkeypatch.setattr(service, "_require_run", lambda _run_id: {"facts": {}})
    repository.get_latest_action_proposal.return_value = {
        "facts": {"advisory": "value"},
        "evidenceRefs": [],
        "evidenceHashes": {},
    }
    repository.list_events.return_value = []

    failures = service._authoritative_gate_failures(
        "run-1", {"requiredFacts": ["missing", "advisory"]}
    )
    assert failures == [
        {"factName": "missing", "reason": "missing"},
        {
            "factName": "advisory",
            "reason": "non_authoritative",
            "authorityClass": "asserted",
        },
    ]


def test_actor_numeric_time_risk_replay_and_value_helpers():
    assert runtime._actor_for_enforcement({}, {"actor": {"role": "operator"}}) == {
        "role": "operator"
    }
    assert runtime._actor_for_enforcement(
        {"actor": {"role": "planner"}}, {}
    ) == {"role": "planner"}
    assert runtime._actor_for_enforcement(
        {}, {"requestingActor": {"role": "requester"}}
    ) == {"role": "requester"}

    assert runtime._sla_contract({}, [{"type": "sla.escalated", "payload": {}}])["state"] == "escalated"
    assert runtime._sla_contract({}, [{"type": "sla.breached", "payload": {}}])["state"] == "breached"
    assert runtime._sla_contract({}, [{"type": "sla.warning", "payload": {}}])["state"] == "warning"
    assert runtime._sla_contract({"sla": {"deadline": "later"}}, [])["state"] == "met"

    naive = runtime._parse_instant(datetime(2026, 1, 1))
    assert naive.tzinfo == timezone.utc
    assert runtime._parse_instant("2026-01-01T00:00:00") .tzinfo == timezone.utc

    assert runtime._risk_score(explicit=200, facts={}, status="allowed", confidence=1.0) == 100
    assert runtime._risk_score(
        explicit="bad",
        facts={"obstacleConfidence": "bad"},
        status="receipt_failed",
        confidence=0.1,
    ) == 60
    assert runtime._risk_score(
        explicit=None,
        facts={"obstacleConfidence": 0.5},
        status="sealed",
        confidence=1.0,
    ) == 40
    assert runtime._risk_band(70) == "high"
    assert runtime._risk_band(40) == "medium"
    assert runtime._risk_band(39) == "low"
    assert runtime._evidence_completeness(
        {"evidenceRefs": ["a", "b"], "evidenceHashes": {"a": "hash"}}
    ) == {"requiredRefs": 2, "hashedRefs": 1, "complete": False}

    with pytest.raises(ValueError, match="policyId"):
        runtime._replay_policy("", {})
    active_dock = runtime._replay_snapshot(
        {
            "facts": {"activeDock": True, "obstacleClassificationConfidence": 1.0},
            "evidenceRefs": ["ev-dock-clearance"],
            "overrideAuthorityPresent": True,
        },
        runtime._replay_policy("policy", {}),
    )
    assert active_dock["decision"] == "denied"
    assert runtime._replay_group("unknown", "other") == "unchanged"

    assert runtime._value_type(True) == "boolean"
    assert runtime._value_type(2) == "number"
    assert runtime._value_type({}) == "json"
    assert runtime._value_type("text") == "string"
    assert runtime._unique_strings("not-a-list") == []
    with pytest.raises(ValueError, match="outcome must"):
        runtime._outcome("invalid", default="allow")
    assert runtime._event_cursor([]) == {
        "latestSequence": 0,
        "latestEventId": None,
        "latestHash": None,
    }


def test_fact_extraction_normalization_and_threshold_operators():
    records, refs, hashes = runtime._extract_fact_records(
        {
            "evidence": [
                {
                    "id": "ev-1",
                    "contentHash": "hash-1",
                    "facts": {"from evidence": True},
                }
            ],
            "evidenceHashes": {"ev-2": "hash-2", "": "ignored"},
            "facts": [
                {
                    "factName": "body fact",
                    "value": 2,
                    "sourceRefs": ["ev-2"],
                    "sourceHashes": [],
                }
            ],
        }
    )
    assert {record["factName"] for record in records} == {
        "from evidence",
        "body fact",
    }
    assert refs == ["ev-1", "ev-2"]
    assert hashes == {"ev-1": "hash-1", "ev-2": "hash-2"}
    assert runtime._normalise_fact_items({"a": 1}) == [{"factName": "a", "value": 1}]
    with pytest.raises(ValueError, match="name is required"):
        runtime._fact_record_from_payload(
            {},
            default_authority="asserted",
            default_extraction_method="test",
            source={},
        )

    cases = [
        ({"currentValue": "a", "requiredValue": "a", "operator": "equals"}, True),
        ({"currentValue": 2, "requiredValue": 1, "operator": ">"}, True),
        ({"currentValue": 1, "requiredValue": 1, "operator": ">="}, True),
        ({"currentValue": 1, "requiredValue": 2, "operator": "<"}, True),
        ({"currentValue": 1, "requiredValue": 1, "operator": "<="}, True),
        ({"currentValue": 1, "requiredValue": 1, "operator": "=="}, True),
        ({"currentValue": 1, "requiredValue": 1, "operator": "unsupported"}, False),
        ({"currentValue": "a", "requiredValue": "b", "operator": ">="}, False),
    ]
    for threshold, expected in cases:
        assert runtime._threshold_satisfied(threshold) is expected


def test_similarity_empty_and_option_outcome_branches():
    assert runtime._fact_overlap({}, {}) == 0.0
    assert runtime._policy_overlap({}, {}) == 0.0
    assert runtime._evidence_completeness_ratio({}) == 0.0
    assert runtime._option_outcome_similarity(
        {"selectedOptionId": "allow"},
        {"selectedOptionId": "allow"},
    ) == 0.6
    assert runtime._option_outcome_similarity(
        {"rejectedOptionIds": ["deny", "modify"]},
        {"rejectedOptionIds": ["modify"]},
    ) == 0.2
    assert runtime._option_outcome_similarity({}, {}) == 0.4
