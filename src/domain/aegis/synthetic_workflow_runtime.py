"""Synthetic AEGIS workflow runtime for the first executable robot slice."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.domain.aegis.rule_store import (
    AEGIS_PRODUCT,
    AEGIS_RULE_STORE,
    build_policy_integrity,
    rule_version_hash,
    validation_to_dict,
)
from src.domain.aegis.insurance_fraud_replay import (
    INSURANCE_WORKFLOW_ID,
    InsuranceFraudReplayRuntime,
)
from src.services.rule_validation_service import RuleValidationService, ValidationResult

if TYPE_CHECKING:
    from src.services.rule_service import RuleService


ROBOT_WORKFLOW_ID = "synthetic-robot-task-approval"
ROBOT_RUN_ID = "wf-robot-124"
ROBOT_RULE_NAME = "synthetic_robot_safety_gate"
ROBOT_RULE_VERSION = "synthetic-0.1"
IMPORT_TREE_HASH = "sha256:synthetic_site_maintenance_policy_v0"
CERTIFIED_OBSTACLE_CONFIDENCE_THRESHOLD = 0.85
MINIMUM_BATTERY_RESERVE_PERCENT = 30

ROBOT_RULE_TEXT = """FIXED certified obstacle confidence threshold IS 0.85
FIXED minimum battery reserve percent IS 30
INPUT obstacle classification confidence AS NUMBER
INPUT battery reserve percent AS NUMBER
INPUT emergency stop active AS BOOLEAN

mandatory safety boundary is satisfied
    AND battery reserve percent >= minimum battery reserve percent
    AND NOT emergency stop active
    AND obstacle classification confidence >= certified obstacle confidence threshold

operator escalation is required
    OR obstacle classification confidence < certified obstacle confidence threshold
"""


class EventSequenceError(ValueError):
    """Raised when a client attempts an out-of-order event append."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validation_to_dict(result: ValidationResult) -> dict[str, Any]:
    return {
        "valid": result.valid,
        "errors": [
            {
                "code": error.code,
                "message": error.message,
                "line": error.line,
                "nodeName": error.node_name,
                "waiverId": error.waiver_id,
            }
            for error in result.errors
        ],
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "line": warning.line,
                "nodeName": warning.node_name,
                "waiverId": warning.waiver_id,
            }
            for warning in result.warnings
        ],
    }


def _condition_metadata(
    condition: str,
    *,
    evidence_refs: list[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"condition": condition}
    if evidence_refs:
        metadata["evidenceRefs"] = evidence_refs
    if source:
        metadata["source"] = source
    return metadata


def _condition_set(
    conditions: list[str],
    evidence_refs: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        _condition_metadata(condition, evidence_refs=evidence_refs)
        for condition in conditions
        if condition.strip()
    ]


def _actor(kind: str, actor_id: str, role: str) -> dict[str, str]:
    return {"kind": kind, "id": actor_id, "role": role}


def _base_event(
    sequence: int,
    event_type: str,
    actor: dict[str, str],
    payload: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    rule_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
    idempotency_key: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    return {
        "eventId": f"evt_synth_robot_{sequence:04d}",
        "idempotencyKey": idempotency_key or f"{ROBOT_RUN_ID}:{event_type}:baseline:{sequence}",
        "type": event_type,
        "runId": ROBOT_RUN_ID,
        "definitionId": ROBOT_WORKFLOW_ID,
        "sequence": sequence,
        "actor": actor,
        "occurredAt": occurred_at or f"2026-06-01T00:{sequence:02d}:00Z",
        "preState": {},
        "payload": payload or {},
        "evidenceRefs": evidence_refs or [],
        "ruleRefs": rule_refs or [],
        "receiptRefs": receipt_refs or [],
        "correlationId": "synth-robot-124",
    }


def _synthetic_evidence_payload(
    evidence_id: str,
    label: str,
    source_layer: str,
    value: bool | int | float | str,
    value_type: str,
    source_label: str,
    source_uri: str,
    *,
    confidence: float = 1.0,
    trust_score: float = 0.9,
    collected_at: str = "2026-06-01T00:02:00Z",
    freshness_state: str = "fresh",
    supports: list[str] | None = None,
    opposes: list[str] | None = None,
    event_layer: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": evidence_id,
        "label": label,
        "sourceLayer": source_layer,
        "value": value,
        "valueType": value_type,
        "confidence": confidence,
        "trustScore": trust_score,
        "sourceLabel": source_label,
        "sourceUri": source_uri,
        "contentHash": _stable_hash(
            {
                "id": evidence_id,
                "value": value,
                "sourceUri": source_uri,
            }
        ),
        "collectedAt": collected_at,
        "freshnessState": freshness_state,
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
        "supports": supports or [],
        "opposes": opposes or [],
    }
    if event_layer:
        payload["eventLayer"] = event_layer
    return payload


EVIDENCE_PAYLOADS: list[dict[str, Any]] = [
    {
        "id": "ev-obstacle-confidence",
        "label": "Obstacle classification confidence",
        "sourceLayer": "ASSERTED",
        "value": 0.72,
        "valueType": "number",
        "unit": "ratio",
        "confidence": 0.72,
        "trustScore": 0.74,
        "sourceLabel": "synthetic_sensor:no_real_robot",
        "sourceUri": "synthetic://robot/amr-17/obstacle-confidence",
        "contentHash": "sha256:synthetic-obstacle-confidence-v0",
        "collectedAt": "2026-06-01T00:02:00Z",
        "freshnessState": "fresh",
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
        "supports": ["robot-escalate"],
        "opposes": ["robot-reroute", "robot-proceed"],
    },
    {
        "id": "ev-maintenance-import",
        "label": "Low-traffic corridor unavailable",
        "sourceLayer": "SEMANTIC",
        "value": "unavailable",
        "valueType": "string",
        "confidence": 1.0,
        "trustScore": 0.95,
        "sourceLabel": "synthetic_site_maintenance_policy",
        "sourceUri": "synthetic://site/policy/maintenance-window",
        "contentHash": IMPORT_TREE_HASH,
        "collectedAt": "2026-06-01T00:01:00Z",
        "freshnessState": "fresh",
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
        "supports": ["robot-reroute-blocked"],
        "opposes": ["robot-reroute"],
    },
    {
        "id": "ev-battery-reserve",
        "label": "Battery reserve percent",
        "sourceLayer": "ASSERTED",
        "value": 61,
        "valueType": "number",
        "unit": "percent",
        "confidence": 0.98,
        "trustScore": 0.9,
        "sourceLabel": "synthetic_fleet_telemetry:no_real_robot",
        "sourceUri": "synthetic://robot/amr-17/battery",
        "contentHash": "sha256:synthetic-battery-reserve-v0",
        "collectedAt": "2026-06-01T00:02:30Z",
        "freshnessState": "fresh",
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
        "supports": ["robot-wait", "robot-dock"],
        "opposes": [],
    },
    {
        "id": "ev-geofence-state",
        "label": "Geofence state",
        "sourceLayer": "ASSERTED",
        "value": "inside permitted zone",
        "valueType": "string",
        "confidence": 0.99,
        "trustScore": 0.92,
        "sourceLabel": "synthetic_geofence:no_real_robot",
        "sourceUri": "synthetic://robot/amr-17/geofence",
        "contentHash": "sha256:synthetic-geofence-state-v0",
        "collectedAt": "2026-06-01T00:02:45Z",
        "freshnessState": "fresh",
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
        "supports": ["robot-wait", "robot-dock"],
        "opposes": [],
    },
    {
        "id": "ev-emergency-stop",
        "label": "Emergency stop active",
        "sourceLayer": "ASSERTED",
        "value": False,
        "valueType": "boolean",
        "confidence": 1.0,
        "trustScore": 0.94,
        "sourceLabel": "synthetic_estop:no_real_robot",
        "sourceUri": "synthetic://robot/amr-17/estop",
        "contentHash": "sha256:synthetic-estop-v0",
        "collectedAt": "2026-06-01T00:02:45Z",
        "freshnessState": "fresh",
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
        "supports": ["robot-wait", "robot-dock"],
        "opposes": [],
    },
    _synthetic_evidence_payload(
        "ev-requested-route",
        "Requested route",
        "ASSERTED",
        "dock C reroute",
        "string",
        "fleet-planner.alpha",
        "synthetic://robot/amr-17/requested-route",
        confidence=0.96,
        trust_score=0.9,
        supports=["robot-task"],
    ),
    _synthetic_evidence_payload(
        "ev-payload-class",
        "Payload class",
        "ASSERTED",
        "standard pallet payload",
        "string",
        "fleet-planner.alpha",
        "synthetic://robot/amr-17/payload-class",
        confidence=0.97,
        trust_score=0.9,
        supports=["robot-task"],
    ),
    _synthetic_evidence_payload(
        "ev-dock-schedule",
        "Dock schedule",
        "SEMANTIC",
        "dock C dispatch slot active",
        "string",
        "synthetic_wms_schedule:no_real_order",
        "synthetic://site/dock-c/schedule",
        confidence=1.0,
        trust_score=0.88,
        supports=["robot-task", "robot-wait"],
    ),
    _synthetic_evidence_payload(
        "ev-selected-option",
        "Selected escalation option",
        "INFERRED",
        "robot-escalate",
        "string",
        "aegis-options-engine",
        "synthetic://workflow/wf-robot-124/options/robot-escalate",
        confidence=0.93,
        trust_score=0.91,
        supports=["robot-operator", "robot-receipt"],
    ),
    _synthetic_evidence_payload(
        "ev-approval-receipt",
        "Approval receipt state",
        "SEMANTIC",
        "approval requested",
        "string",
        "aegis-workflow-runtime",
        "synthetic://workflow/wf-robot-124/approvals/approval-robot-operator-1",
        confidence=1.0,
        trust_score=0.92,
        supports=["robot-actuate"],
        event_layer="APPROVAL",
    ),
    _synthetic_evidence_payload(
        "ev-safe-route",
        "Safe fallback route",
        "INFERRED",
        "return-to-dock route available",
        "string",
        "aegis-options-engine",
        "synthetic://workflow/wf-robot-124/routes/return-to-dock",
        confidence=0.86,
        trust_score=0.9,
        supports=["robot-actuate", "robot-dock"],
    ),
    _synthetic_evidence_payload(
        "ev-policy-hash",
        "Policy import hash",
        "SEMANTIC",
        IMPORT_TREE_HASH,
        "string",
        "synthetic_site_maintenance_policy",
        "synthetic://site/policy/maintenance-window#hash",
        confidence=1.0,
        trust_score=0.95,
        supports=["robot-actuate", "robot-receipt"],
    ),
    _synthetic_evidence_payload(
        "ev-rejected-options",
        "Rejected option set",
        "INFERRED",
        "robot-reroute",
        "string",
        "aegis-options-engine",
        "synthetic://workflow/wf-robot-124/options/rejected",
        confidence=0.93,
        trust_score=0.91,
        supports=["robot-receipt"],
    ),
    _synthetic_evidence_payload(
        "ev-rule-hash",
        "Rule version hash",
        "SEMANTIC",
        _stable_hash(ROBOT_RULE_TEXT),
        "string",
        "inferra-rule-validator",
        "synthetic://validation/wf-robot-124/v0#rule-hash",
        confidence=1.0,
        trust_score=0.96,
        supports=["robot-receipt"],
    ),
    _synthetic_evidence_payload(
        "ev-event-cursor",
        "Event cursor",
        "SEMANTIC",
        "evt_synth_robot_0008",
        "string",
        "aegis-workflow-runtime",
        "synthetic://workflow/wf-robot-124/events/cursor",
        confidence=1.0,
        trust_score=0.94,
        supports=["robot-receipt"],
    ),
]

BASE_NODES: list[dict[str, Any]] = [
    {
        "id": "robot-task",
        "label": "Task request",
        "type": "REQUEST",
        "status": "complete",
        "owner": "fleet-planner.alpha",
        "role": "AI planner",
        "startedAt": "09:41",
        "elapsedMinutes": 1,
        "slaMinutes": 3,
        "slaState": "met",
        "ruleRef": "autonomous task request is complete",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-requested-route", "ev-payload-class", "ev-dock-schedule"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["proposal received from supervised autonomy planner"],
        "exitCriteria": ["task request fields complete"],
        "blockedReason": None,
        "recoveryActions": [],
        "conditionMetadata": {
            "entryConditions": _condition_set(["proposal received from supervised autonomy planner"]),
            "exitConditions": _condition_set(["task request fields complete"], ["ev-requested-route"]),
        },
    },
    {
        "id": "robot-safety-gate",
        "label": "Safety gate",
        "type": "RULE_GATE",
        "status": "blocked",
        "owner": "INFERRA sidecar",
        "role": "policy gate",
        "startedAt": "09:42",
        "elapsedMinutes": 1,
        "slaMinutes": 1,
        "slaState": "breached",
        "ruleRef": "mandatory safety boundary is satisfied",
        "ruleSessionId": "synthetic-rule-session-robot-124",
        "requiredEvidenceRefs": [
            "ev-obstacle-confidence",
            "ev-battery-reserve",
            "ev-geofence-state",
            "ev-emergency-stop",
        ],
        "producedEvidenceRefs": ["ev-maintenance-import"],
        "entryCriteria": ["robot task request complete"],
        "exitCriteria": ["all mandatory safety predicates true"],
        "blockedReason": "Obstacle confidence 0.72 is below the certified 0.85 threshold.",
        "recoveryActions": ["select supervised option", "add evidence", "return to dock"],
        "conditionMetadata": {
            "entryConditions": _condition_set(
                ["robot task request complete"],
                ["ev-requested-route", "ev-payload-class", "ev-dock-schedule"],
            ),
            "exitConditions": _condition_set(
                ["all mandatory safety predicates true"],
                ["ev-obstacle-confidence", "ev-battery-reserve", "ev-geofence-state", "ev-emergency-stop"],
            ),
        },
    },
    {
        "id": "robot-option-set",
        "label": "Route options",
        "type": "OPTION_SET",
        "status": "active",
        "owner": "AEGIS",
        "role": "options engine",
        "startedAt": "09:43",
        "elapsedMinutes": 7,
        "slaMinutes": 10,
        "slaState": "warning",
        "ruleRef": "safe fallback route is available",
        "ruleSessionId": None,
        "requiredEvidenceRefs": [
            "ev-obstacle-confidence",
            "ev-battery-reserve",
            "ev-maintenance-import",
        ],
        "producedEvidenceRefs": [],
        "entryCriteria": ["safety gate failed or requires supervised recovery"],
        "exitCriteria": ["operator option selected or fallback selected"],
        "blockedReason": None,
        "recoveryActions": ["request override approval", "select return-to-dock fallback"],
        "conditionMetadata": {
            "entryConditions": _condition_set(
                ["safety gate failed or requires supervised recovery"],
                ["ev-obstacle-confidence", "ev-battery-reserve", "ev-maintenance-import"],
            ),
            "exitConditions": _condition_set(
                ["operator option selected or fallback selected"],
                ["ev-selected-option", "ev-obstacle-confidence", "ev-maintenance-import"],
            ),
        },
    },
    {
        "id": "robot-operator",
        "label": "Operator approval",
        "type": "HUMAN_APPROVAL",
        "status": "waiting",
        "owner": "Dock safety lead",
        "role": "override authority",
        "startedAt": "09:50",
        "elapsedMinutes": 0,
        "slaMinutes": 10,
        "slaState": "met",
        "ruleRef": "human override authority is present",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-selected-option", "ev-obstacle-confidence", "ev-maintenance-import"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["escalation option selected"],
        "exitCriteria": ["override authority grants or rejects the approval"],
        "blockedReason": None,
        "recoveryActions": ["reject approval and return to dock", "allow no-op actuation"],
        "conditionMetadata": {
            "entryConditions": _condition_set(
                ["escalation option selected"],
                ["ev-selected-option", "ev-obstacle-confidence", "ev-maintenance-import"],
            ),
            "exitConditions": _condition_set(
                ["override authority grants or rejects the approval"],
                ["ev-approval-receipt", "ev-obstacle-confidence", "ev-maintenance-import"],
            ),
        },
    },
    {
        "id": "robot-actuate",
        "label": "Actuation release",
        "type": "ACTUATION",
        "status": "scheduled",
        "owner": "synthetic ROS sidecar",
        "role": "control layer",
        "startedAt": "-",
        "elapsedMinutes": 0,
        "slaMinutes": 1,
        "slaState": "not_started",
        "ruleRef": "actuation is allowed",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-approval-receipt", "ev-safe-route", "ev-policy-hash"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["operator approval granted", "transition guard allowed"],
        "exitCriteria": ["synthetic no-op completion event appended"],
        "blockedReason": None,
        "recoveryActions": ["trigger return-to-dock fallback", "retry no-op event append"],
        "conditionMetadata": {
            "entryConditions": _condition_set(
                ["operator approval granted", "transition guard allowed"],
                ["ev-approval-receipt", "ev-safe-route", "ev-policy-hash"],
            ),
            "exitConditions": _condition_set(["synthetic no-op completion event appended"]),
        },
    },
    {
        "id": "robot-dock",
        "label": "Return to dock fallback",
        "type": "FALLBACK",
        "status": "scheduled",
        "owner": "fleet supervisor",
        "role": "safe fallback owner",
        "startedAt": "-",
        "elapsedMinutes": 0,
        "slaMinutes": 3,
        "slaState": "not_started",
        "ruleRef": "safe fallback route is available",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-battery-reserve", "ev-geofence-state"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["operator approval rejected or timed out"],
        "exitCriteria": ["fallback decision receipt sealed"],
        "blockedReason": None,
        "recoveryActions": ["seal fallback receipt", "page safety officer"],
        "conditionMetadata": {
            "entryConditions": _condition_set(
                ["operator approval rejected or timed out"],
                ["ev-selected-option", "ev-obstacle-confidence"],
            ),
            "exitConditions": _condition_set(["fallback decision receipt sealed"]),
        },
    },
    {
        "id": "robot-receipt",
        "label": "Decision receipt",
        "type": "RECEIPT_SEAL",
        "status": "scheduled",
        "owner": "AEGIS ledger",
        "role": "signature authority",
        "startedAt": "-",
        "elapsedMinutes": 0,
        "slaMinutes": 1,
        "slaState": "not_started",
        "ruleRef": "robot decision can be sealed",
        "ruleSessionId": None,
        "requiredEvidenceRefs": [
            "ev-selected-option",
            "ev-rejected-options",
            "ev-rule-hash",
            "ev-event-cursor",
        ],
        "producedEvidenceRefs": [],
        "entryCriteria": ["terminal decision event available"],
        "exitCriteria": ["receipt hash and previous hash written"],
        "blockedReason": None,
        "recoveryActions": ["retry receipt sealing"],
        "conditionMetadata": {
            "entryConditions": _condition_set(["terminal decision event available"]),
            "exitConditions": _condition_set(["receipt hash and previous hash written"]),
        },
    },
]

BASE_OPTIONS: list[dict[str, Any]] = [
    {
        "id": "robot-wait",
        "label": "Wait for path clearance",
        "status": "available",
        "confidence": 79,
        "risk": 22,
        "timeImpactMinutes": 14,
        "costImpact": "11 minute schedule drift",
        "requiredRole": "fleet supervisor",
        "supportingEvidenceRefs": ["ev-battery-reserve"],
        "opposingEvidenceRefs": ["dock SLA will degrade"],
        "constraints": ["does not release actuation while safety gate is blocked"],
        "rationale": "Safe, but operational delay is material.",
        "selectionReason": None,
        "rejectionReason": None,
        "requiresApproval": False,
        "wouldTriggerNodeId": "robot-option-set",
        "fallbackIfRejected": "robot-dock",
    },
    {
        "id": "robot-reroute",
        "label": "Reroute through low-traffic corridor",
        "status": "blocked",
        "confidence": 61,
        "risk": 74,
        "timeImpactMinutes": 5,
        "costImpact": "low",
        "requiredRole": "safety officer",
        "supportingEvidenceRefs": ["ev-maintenance-import"],
        "opposingEvidenceRefs": ["ev-obstacle-confidence", "ev-maintenance-import"],
        "constraints": ["imported maintenance policy marks corridor unavailable"],
        "rationale": "Blocked by imported site maintenance policy.",
        "selectionReason": None,
        "rejectionReason": "corridor unavailable",
        "requiresApproval": True,
        "wouldTriggerNodeId": "robot-actuate",
        "fallbackIfRejected": "robot-dock",
    },
    {
        "id": "robot-escalate",
        "label": "Escalate to human operator",
        "status": "selected",
        "confidence": 93,
        "risk": 18,
        "timeImpactMinutes": 8,
        "costImpact": "operator attention required",
        "requiredRole": "override authority",
        "supportingEvidenceRefs": ["ev-obstacle-confidence", "ev-maintenance-import"],
        "opposingEvidenceRefs": ["requires human availability"],
        "constraints": ["requires approval before actuation"],
        "rationale": "Best certified path because the robot cannot prove the obstacle state.",
        "selectionReason": "Obstacle confidence is below 0.85 and the route import blocks reroute.",
        "rejectionReason": None,
        "requiresApproval": True,
        "wouldTriggerNodeId": "robot-operator",
        "fallbackIfRejected": "robot-dock",
    },
    {
        "id": "robot-dock",
        "label": "Return to dock",
        "status": "available",
        "confidence": 86,
        "risk": 12,
        "timeImpactMinutes": 22,
        "costImpact": "missed dispatch slot",
        "requiredRole": "fleet supervisor",
        "supportingEvidenceRefs": ["ev-battery-reserve", "ev-geofence-state"],
        "opposingEvidenceRefs": ["highest schedule impact"],
        "constraints": ["safe fallback only; no delivery actuation"],
        "rationale": "Safe fallback if no operator responds before SLA expiry.",
        "selectionReason": None,
        "rejectionReason": None,
        "requiresApproval": False,
        "wouldTriggerNodeId": "robot-dock",
        "fallbackIfRejected": None,
    },
]

BASE_EVENTS: list[dict[str, Any]] = [
    _base_event(
        1,
        "workflow.created",
        _actor("system", "aegis-fixture-loader", "workflow loader"),
        {"workflowId": ROBOT_WORKFLOW_ID, "version": "1.0.0", "isSynthetic": True},
    ),
    _base_event(
        2,
        "workflow.validated",
        _actor("system", "inferra-rule-validator", "policy validation"),
        {"validationStatus": "valid", "ruleName": ROBOT_RULE_NAME},
        rule_refs=[ROBOT_RULE_NAME],
    ),
    _base_event(
        3,
        "run.started",
        _actor("system", "fleet-planner.alpha", "AI planner"),
        {"entity": "AMR-17 / dock C reroute", "autonomyLevel": "supervised_autonomy"},
    ),
    _base_event(
        4,
        "node.entered",
        _actor("system", "INFERRA sidecar", "policy gate"),
        {"nodeId": "robot-safety-gate"},
    ),
    _base_event(
        5,
        "rule.evaluation.completed",
        _actor("system", "inferra-rule-engine", "policy gate"),
        {
            "platformSessionId": "synthetic-rule-session-robot-124",
            "ruleName": ROBOT_RULE_NAME,
            "targetNodeName": "mandatory safety boundary is satisfied",
            "convergenceState": "GOAL_REACHED",
            "goalRuleName": "mandatory safety boundary is satisfied",
            "goalRuleValue": False,
            "goalRuleType": "BOOLEAN",
            "traceRef": "synthetic://trace/wf-robot-124/safety-gate",
            "validationRef": "synthetic://validation/wf-robot-124/v0",
            "summaryRefs": [
                "ev-obstacle-confidence",
                "ev-battery-reserve",
                "ev-geofence-state",
                "ev-emergency-stop",
            ],
        },
        evidence_refs=[
            "ev-obstacle-confidence",
            "ev-battery-reserve",
            "ev-geofence-state",
            "ev-emergency-stop",
        ],
        rule_refs=[ROBOT_RULE_NAME],
    ),
    _base_event(
        6,
        "options.generated",
        _actor("system", "aegis-options-engine", "options engine"),
        {
            "optionIds": ["robot-wait", "robot-reroute", "robot-escalate", "robot-dock"],
            "blockedOptionIds": ["robot-reroute"],
        },
        evidence_refs=["ev-obstacle-confidence", "ev-maintenance-import", "ev-battery-reserve"],
    ),
    _base_event(
        7,
        "option.selected",
        _actor("system", "aegis-options-engine", "options engine"),
        {
            "optionId": "robot-escalate",
            "selectedBy": _actor("system", "aegis-options-engine", "options engine"),
            "selectionReason": "Obstacle confidence below 0.85 and maintenance import blocks reroute.",
            "supportingEvidenceRefs": ["ev-obstacle-confidence", "ev-maintenance-import"],
            "opposingEvidenceRefs": ["requires human availability"],
            "rejectedOptionIds": [],
            "blockedOptionIds": ["robot-reroute"],
            "nextNodeId": "robot-operator",
            "requiresApproval": True,
        },
        evidence_refs=["ev-obstacle-confidence", "ev-maintenance-import"],
    ),
    _base_event(
        8,
        "approval.requested",
        _actor("system", "aegis-workflow-runtime", "approval coordinator"),
        {
            "approvalId": "approval-robot-operator-1",
            "requiredRole": "override authority",
            "nodeId": "robot-operator",
            "slaMinutes": 10,
        },
        evidence_refs=["ev-obstacle-confidence", "ev-maintenance-import"],
    ),
]


class SyntheticAegisWorkflowRuntime:
    """In-memory event-sourced runtime for the synthetic robot workflow."""

    def __init__(self) -> None:
        self._validation_service = RuleValidationService()
        self._insurance_runtime = InsuranceFraudReplayRuntime()
        self.reset()

    def reset(self) -> None:
        self._insurance_runtime.reset()
        self._run_events: dict[str, list[dict[str, Any]]] = {ROBOT_RUN_ID: deepcopy(BASE_EVENTS)}
        self._idempotency: dict[str, dict[str, dict[str, Any]]] = {
            ROBOT_RUN_ID: {
                event["idempotencyKey"]: event
                for event in BASE_EVENTS
                if event.get("idempotencyKey")
            }
        }

    def list_workflows(self) -> dict[str, Any]:
        return {
            "workflows": [
                self.get_workflow(ROBOT_WORKFLOW_ID),
                *self._insurance_runtime.list_workflows()["workflows"],
            ]
        }

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_workflow_id(workflow_id):
            return self._insurance_runtime.get_workflow(workflow_id)
        if workflow_id != ROBOT_WORKFLOW_ID:
            raise LookupError(f"Unknown AEGIS workflow '{workflow_id}'")

        return {
            "id": ROBOT_WORKFLOW_ID,
            "version": "1.0.0",
            "title": "Synthetic Robot Task Approval",
            "domain": "robotics",
            "isSynthetic": True,
            "status": "active",
            "autonomyPolicy": {
                "level": "supervised_autonomy",
                "certifiedObstacleConfidenceThreshold": CERTIFIED_OBSTACLE_CONFIDENCE_THRESHOLD,
                "humanApprovalRequired": True,
                "certifiedTemplate": False,
                "autoApplyEnabled": False,
            },
            "roles": [
                {"id": "ai-planner", "label": "AI planner", "authorityScopes": ["propose"]},
                {
                    "id": "override-authority",
                    "label": "override authority",
                    "authorityScopes": ["approve", "reject"],
                },
                {"id": "signature-authority", "label": "signature authority", "authorityScopes": ["seal"]},
            ],
            "nodes": deepcopy(BASE_NODES),
            "transitions": [
                {
                    "fromNodeId": "robot-safety-gate",
                    "toNodeId": "robot-option-set",
                    "triggerEvent": "rule.evaluation.completed",
                    "guard": "mandatory safety boundary is false",
                    "recoveryRoute": "robot-operator",
                },
                {
                    "fromNodeId": "robot-operator",
                    "toNodeId": "robot-actuate",
                    "triggerEvent": "approval.granted",
                    "guard": "override authority present",
                    "recoveryRoute": "robot-dock",
                },
                {
                    "fromNodeId": "robot-operator",
                    "toNodeId": "robot-dock",
                    "triggerEvent": "sla.breached",
                    "guard": "approval not granted before SLA",
                    "recoveryRoute": "robot-dock",
                },
            ],
            "compiledPolicyRefs": [
                {
                    "ruleName": ROBOT_RULE_NAME,
                    "ruleVersion": ROBOT_RULE_VERSION,
                    "ruleHash": _stable_hash(ROBOT_RULE_TEXT),
                    "importTreeHash": IMPORT_TREE_HASH,
                }
            ],
            "receiptPolicy": {
                "sealOnEvents": ["receipt.sealed", "fallback.triggered"],
                "requiredFields": [
                    "runId",
                    "eventSequenceRange",
                    "selectedOption",
                    "evidenceRefs",
                    "ruleVersionHash",
                ],
            },
            "dossierSchema": {
                "format": "json",
                "includes": ["eventLog", "evidence", "receipt", "traceMetadata"],
            },
        }

    def validate_workflow(self, workflow_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_workflow_id(workflow_id):
            return self._insurance_runtime.validate_workflow(workflow_id)
        self.get_workflow(workflow_id)
        validation = self._validate_rule()
        return {
            "workflowId": workflow_id,
            "valid": validation["valid"],
            "ruleGateValidation": validation,
            "invariants": [
                {"code": "ONE_ACTIVE_EXECUTABLE_NODE", "valid": True},
                {"code": "SYNTHETIC_NO_OP_ACTUATION_ONLY", "valid": True},
                {"code": "APPEND_ONLY_EVENTS", "valid": True},
                {"code": "AUTO_APPLY_DISABLED", "valid": True},
            ],
        }

    def compile_workflow(self, workflow_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_workflow_id(workflow_id):
            return self._insurance_runtime.compile_workflow(workflow_id)
        self.get_workflow(workflow_id)
        return {
            "workflowId": workflow_id,
            "compiledPolicyRefs": self.get_workflow(workflow_id)["compiledPolicyRefs"],
            "ruleText": ROBOT_RULE_TEXT,
            "grammarExtensionRequired": False,
        }

    def create_run(self, body: dict[str, Any]) -> dict[str, Any]:
        workflow_id = body.get("workflowId", ROBOT_WORKFLOW_ID)
        run_id = body.get("runId", ROBOT_RUN_ID)
        if workflow_id == INSURANCE_WORKFLOW_ID:
            return self._insurance_runtime.create_run(body)
        if workflow_id != ROBOT_WORKFLOW_ID:
            raise LookupError(f"Unknown AEGIS workflow '{workflow_id}'")
        if run_id != ROBOT_RUN_ID:
            raise ValueError("The first executable slice only supports synthetic run wf-robot-124")

        if body.get("reset", False):
            self.reset()

        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.get_run(run_id)
        events = self._events_for(run_id)
        return {"run": self._project_run(events)}

    def get_timeline(self, run_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.get_timeline(run_id)
        events = self._events_for(run_id)
        return {
            "runId": run_id,
            "eventCursor": self._event_cursor(events),
            "events": deepcopy(events),
            "timeline": self._timeline(events),
        }

    def get_options(self, run_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.get_options(run_id)
        events = self._events_for(run_id)
        run = self._project_run(events)
        return {
            "runId": run_id,
            "selectedOptionId": run["selectedOptionId"],
            "options": run["options"],
        }

    def append_event(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.append_event(run_id, body)
        events = self._events_for(run_id)
        event_type = str(body.get("type") or "").strip()
        idempotency_key = str(body.get("idempotencyKey") or "").strip()
        if not event_type:
            raise ValueError("Event type is required")
        if not idempotency_key:
            raise ValueError("idempotencyKey is required for AEGIS workflow writes")

        existing = self._idempotency[run_id].get(idempotency_key)
        if existing:
            return {
                "event": deepcopy(existing),
                "idempotentReplay": True,
                "run": self._project_run(events),
            }

        next_sequence = self._next_sequence(events)
        requested_sequence = body.get("sequence")
        if requested_sequence is not None and int(requested_sequence) != next_sequence:
            raise EventSequenceError(
                f"Event sequence {requested_sequence} is out of order; expected {next_sequence}"
            )

        event = _base_event(
            next_sequence,
            event_type,
            body.get("actor") or _actor("system", "aegis-workflow-runtime", "workflow runtime"),
            body.get("payload") or {},
            body.get("evidenceRefs") or [],
            body.get("ruleRefs") or [],
            body.get("receiptRefs") or [],
            idempotency_key,
            body.get("occurredAt") or _utc_now(),
        )
        event["preState"] = self._pre_state(events)
        events.append(event)
        self._idempotency[run_id][idempotency_key] = event

        return {
            "event": deepcopy(event),
            "idempotentReplay": False,
            "run": self._project_run(events),
        }

    def select_option(self, run_id: str, option_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.select_option(run_id, option_id, body)
        if option_id not in {option["id"] for option in BASE_OPTIONS}:
            raise LookupError(f"Unknown option '{option_id}'")

        option = next(option for option in BASE_OPTIONS if option["id"] == option_id)
        idempotency_key = body.get("idempotencyKey") or f"{run_id}:option.selected:{option_id}:{_utc_now()}"
        event_type = "transition.denied" if option["status"] == "blocked" else "option.selected"
        payload = {
            "optionId": option_id,
            "selectedBy": body.get("actor") or _actor("human", "synthetic-operator", option["requiredRole"]),
            "selectionReason": body.get("selectionReason") or option.get("rationale"),
            "supportingEvidenceRefs": option.get("supportingEvidenceRefs", []),
            "opposingEvidenceRefs": option.get("opposingEvidenceRefs", []),
            "blockedOptionIds": [candidate["id"] for candidate in BASE_OPTIONS if candidate["status"] == "blocked"],
            "nextNodeId": option.get("wouldTriggerNodeId"),
            "requiresApproval": option.get("requiresApproval", False),
        }
        if option["status"] == "blocked":
            payload["deniedReason"] = "Selected option is blocked by workflow constraints"

        return self.append_event(
            run_id,
            {
                "type": event_type,
                "idempotencyKey": idempotency_key,
                "actor": body.get("actor") or _actor("human", "synthetic-operator", option["requiredRole"]),
                "payload": payload,
                "evidenceRefs": option.get("supportingEvidenceRefs", []),
            },
        )

    def decide_approval(self, run_id: str, approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.decide_approval(run_id, approval_id, body)
        if approval_id != "approval-robot-operator-1":
            raise LookupError(f"Unknown approval '{approval_id}'")
        decision = str(body.get("decision") or "").lower()
        if decision not in {"granted", "rejected"}:
            raise ValueError("decision must be granted or rejected")

        event_type = "approval.granted" if decision == "granted" else "approval.rejected"
        return self.append_event(
            run_id,
            {
                "type": event_type,
                "idempotencyKey": body.get("idempotencyKey")
                or f"{run_id}:{event_type}:approval-robot-operator-1:{_utc_now()}",
                "actor": body.get("actor") or _actor("human", "dock-safety-lead", "override authority"),
                "payload": {
                    "approvalId": approval_id,
                    "decision": decision,
                    "rationale": body.get("rationale")
                    or (
                        "Synthetic override approved for no-op actuation"
                        if decision == "granted"
                        else "Synthetic override rejected; fallback required"
                    ),
                    "nodeId": "robot-operator",
                },
                "evidenceRefs": ["ev-obstacle-confidence", "ev-maintenance-import"],
            },
        )

    def transition(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.transition(run_id, body)
        events = self._events_for(run_id)
        base_key = body.get("idempotencyKey") or f"{run_id}:transition:{_utc_now()}"
        actor = body.get("actor") or _actor("system", "aegis-workflow-runtime", "workflow runtime")

        if body.get("triggerFallback", False):
            self.append_event(
                run_id,
                {
                    "type": "fallback.triggered",
                    "idempotencyKey": f"{base_key}:fallback.triggered",
                    "actor": actor,
                    "payload": {
                        "optionId": "robot-dock",
                        "reason": body.get("rationale") or "Approval SLA breached; return-to-dock fallback selected.",
                    },
                    "evidenceRefs": ["ev-battery-reserve", "ev-geofence-state"],
                },
            )
            self.append_event(
                run_id,
                {
                    "type": "receipt.sealed",
                    "idempotencyKey": f"{base_key}:receipt.sealed",
                    "actor": _actor("system", "aegis-ledger", "signature authority"),
                    "payload": {"receiptType": "fallback_decision_receipt"},
                },
            )
            return self.get_run(run_id)

        if not self._has_event(events, "approval.granted"):
            denial = self.append_event(
                run_id,
                {
                    "type": "transition.denied",
                    "idempotencyKey": f"{base_key}:transition.denied",
                    "actor": actor,
                    "payload": {
                        "targetNodeId": body.get("targetNodeId", "robot-actuate"),
                        "deniedReason": "operator approval has not been granted",
                    },
                    "evidenceRefs": ["ev-obstacle-confidence", "ev-maintenance-import"],
                },
            )
            raise EventSequenceError(
                "Transition denied because operator approval has not been granted. "
                f"Denied event sequence {denial['event']['sequence']} was appended."
            )

        self.append_event(
            run_id,
            {
                "type": "transition.allowed",
                "idempotencyKey": f"{base_key}:transition.allowed",
                "actor": actor,
                "payload": {"fromNodeId": "robot-operator", "toNodeId": "robot-actuate"},
                "evidenceRefs": ["ev-obstacle-confidence", "ev-maintenance-import"],
            },
        )
        self.append_event(
            run_id,
            {
                "type": "actuation.allowed",
                "idempotencyKey": f"{base_key}:actuation.allowed",
                "actor": _actor("system", "aegis-actuation-gate", "control layer"),
                "payload": {"adapter": "synthetic-noop", "externalCallMade": False},
            },
        )
        self.append_event(
            run_id,
            {
                "type": "actuation.noop.completed",
                "idempotencyKey": f"{base_key}:actuation.noop.completed",
                "actor": _actor("system", "synthetic-ros-sidecar", "control layer"),
                "payload": {
                    "adapter": "synthetic-noop",
                    "externalCallMade": False,
                    "result": "completed",
                },
            },
        )

        if body.get("simulateReceiptSealFailure", False):
            self.append_event(
                run_id,
                {
                    "type": "receipt.seal.failed",
                    "idempotencyKey": f"{base_key}:receipt.seal.failed",
                    "actor": _actor("system", "aegis-ledger", "signature authority"),
                    "payload": {"error": "synthetic receipt seal failure"},
                },
            )
        else:
            self.append_event(
                run_id,
                {
                    "type": "receipt.sealed",
                    "idempotencyKey": f"{base_key}:receipt.sealed",
                    "actor": _actor("system", "aegis-ledger", "signature authority"),
                    "payload": {"receiptType": "synthetic_robot_decision_receipt"},
                },
            )

        return self.get_run(run_id)

    def get_receipt(self, run_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.get_receipt(run_id)
        events = self._events_for(run_id)
        return {"receipt": self._receipt(events)}

    def get_dossier(self, run_id: str) -> dict[str, Any]:
        if self._insurance_runtime.owns_run_id(run_id):
            return self._insurance_runtime.get_dossier(run_id)
        run = self.get_run(run_id)["run"]
        return {
            "dossier": {
                "runId": run_id,
                "format": "synthetic-json",
                "sanitization": {
                    "synthetic": True,
                    "containsCustomerData": False,
                    "containsPhi": False,
                    "containsSecrets": False,
                },
                "run": run,
                "receipt": run["receipt"],
                "traceMetadata": {
                    "platformSessionId": "synthetic-rule-session-robot-124",
                    "traceRef": "synthetic://trace/wf-robot-124/safety-gate",
                    "ruleHash": _stable_hash(ROBOT_RULE_TEXT),
                    "importTreeHash": IMPORT_TREE_HASH,
                },
            }
        }

    def evaluate_gate(
        self,
        body: dict[str, Any] | None = None,
        rule_service: "RuleService | None" = None,
    ) -> dict[str, Any]:
        body = body or {}
        requested_rule_name = body.get("ruleName") or body.get("rule_name")
        if requested_rule_name:
            return self._evaluate_persisted_gate(str(requested_rule_name), body, rule_service)
        if self._is_insurance_gate_request(body):
            return self._insurance_runtime.evaluate_gate(body)

        facts = {
            "obstacleClassificationConfidence": body.get("obstacleClassificationConfidence", 0.72),
            "batteryReservePercent": body.get("batteryReservePercent", 61),
            "emergencyStopActive": body.get("emergencyStopActive", False),
            "lowTrafficCorridorStatus": body.get("lowTrafficCorridorStatus", "unavailable"),
            "geofenceState": body.get("geofenceState", "inside permitted zone"),
        }
        safety_boundary_satisfied = (
            facts["batteryReservePercent"] >= MINIMUM_BATTERY_RESERVE_PERCENT
            and facts["geofenceState"] == "inside permitted zone"
            and facts["emergencyStopActive"] is False
            and facts["obstacleClassificationConfidence"] >= CERTIFIED_OBSTACLE_CONFIDENCE_THRESHOLD
        )
        operator_escalation_required = (
            facts["obstacleClassificationConfidence"] < CERTIFIED_OBSTACLE_CONFIDENCE_THRESHOLD
            or facts["lowTrafficCorridorStatus"] == "unavailable"
        )

        return {
            "workflowId": ROBOT_WORKFLOW_ID,
            "runId": ROBOT_RUN_ID,
            "product": AEGIS_PRODUCT,
            "store": "synthetic-demo",
            "ruleName": ROBOT_RULE_NAME,
            "targetNodeName": "mandatory safety boundary is satisfied",
            "validation": self._validate_rule(),
            "latestFileId": None,
            "ruleVersionHash": rule_version_hash(ROBOT_RULE_TEXT),
            "importTreeHash": IMPORT_TREE_HASH,
            "validationStatus": "valid",
            "policyIntegrity": {
                "product": AEGIS_PRODUCT,
                "store": "synthetic-demo",
                "ruleName": ROBOT_RULE_NAME,
                "latestFileId": None,
                "ruleVersionHash": rule_version_hash(ROBOT_RULE_TEXT),
                "importTreeHash": IMPORT_TREE_HASH,
                "validationStatus": "valid",
                "missingImports": [],
                "hasImportCycles": False,
            },
            "facts": facts,
            "convergenceState": "GOAL_REACHED",
            "safetyBoundarySatisfied": safety_boundary_satisfied,
            "operatorEscalationRequired": operator_escalation_required,
            "autonomyEligibility": {
                "eligible": safety_boundary_satisfied and not operator_escalation_required,
                "reason": (
                    "certified threshold met"
                    if safety_boundary_satisfied and not operator_escalation_required
                    else "obstacle confidence below threshold or route import blocks autonomous actuation"
                ),
            },
            "ruleConfidence": 1.0,
            "evidenceTrustScore": 0.91,
            "traceRef": "synthetic://trace/wf-robot-124/safety-gate",
        }

    def _is_insurance_gate_request(self, body: dict[str, Any]) -> bool:
        workflow_id = str(body.get("workflowId") or body.get("workflow_id") or "")
        run_id = str(body.get("runId") or body.get("run_id") or "")
        scenario_domain = str(body.get("scenarioDomain") or body.get("domain") or "").strip().lower()
        return (
            workflow_id == INSURANCE_WORKFLOW_ID
            or bool(run_id and self._insurance_runtime.owns_run_id(run_id))
            or scenario_domain == "insurance"
            or "branchId" in body
            or "branch" in body
        )

    def _evaluate_persisted_gate(
        self,
        rule_name: str,
        body: dict[str, Any],
        rule_service: "RuleService | None",
    ) -> dict[str, Any]:
        if rule_service is None:
            raise ValueError("AEGIS rule service is required for persisted gate evaluation")

        latest_file = rule_service.get_latest_rule_file(rule_name)
        rule_text = rule_service.decode_rule_file(latest_file)
        validation = rule_service.validate_draft_rule(rule_text=rule_text, rule_name=rule_name)
        integrity = build_policy_integrity(rule_service, rule_name, rule_text, latest_file.file_id)
        requested_target = body.get("targetNodeName") or body.get("target_node_name")
        target_node_name = str(requested_target) if requested_target else rule_name

        target_nodes: list[str] = []
        if validation.valid:
            target_nodes = rule_service.get_target_node_names(rule_name)
            if not requested_target and target_nodes:
                target_node_name = target_nodes[0]

        missing_imports = integrity.get("missingImports", [])
        is_ready = validation.valid and not missing_imports and not integrity.get("hasImportCycles", False)
        return {
            "workflowId": body.get("workflowId", ROBOT_WORKFLOW_ID),
            "runId": body.get("runId", ROBOT_RUN_ID),
            "product": AEGIS_PRODUCT,
            "store": AEGIS_RULE_STORE,
            "ruleName": rule_name,
            "targetNodeName": target_node_name,
            "targetNodeNames": target_nodes,
            "validation": validation_to_dict(validation),
            "latestFileId": latest_file.file_id,
            "ruleVersionHash": integrity["ruleVersionHash"],
            "importTreeHash": integrity["importTreeHash"],
            "validationStatus": integrity["validationStatus"],
            "policyIntegrity": integrity,
            "facts": body.get("facts", {}),
            "convergenceState": "POLICY_READY" if is_ready else "POLICY_BLOCKED",
            "safetyBoundarySatisfied": None,
            "operatorEscalationRequired": None,
            "autonomyEligibility": {
                "eligible": is_ready,
                "reason": (
                    "AEGIS-persisted policy loaded from the AEGIS rule store"
                    if is_ready
                    else "AEGIS policy is blocked by validation or import-store errors"
                ),
            },
            "ruleConfidence": 1.0 if is_ready else 0.0,
            "evidenceTrustScore": body.get("evidenceTrustScore", 0.0),
            "errors": [
                {
                    "code": "UNRESOLVED_IMPORT",
                    "message": f"Imported rule '{missing}' is missing from the AEGIS rule store",
                    "ruleName": missing,
                    "store": AEGIS_RULE_STORE,
                }
                for missing in missing_imports
            ],
            "traceRef": f"aegis://rules/{rule_name}/gate-evaluation",
        }

    def _events_for(self, run_id: str) -> list[dict[str, Any]]:
        if run_id not in self._run_events:
            raise LookupError(f"Unknown AEGIS workflow run '{run_id}'")
        return self._run_events[run_id]

    def _project_run(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        nodes = deepcopy(BASE_NODES)
        options = deepcopy(BASE_OPTIONS)
        status = "escalated"
        current_node_id = "robot-option-set"
        selected_option_id = "robot-escalate"
        next_recommendation = (
            "Escalate to human operator because obstacle confidence is below certified threshold."
        )
        allowed_actions = [
            "approval.granted",
            "approval.rejected",
            "fallback.triggered",
            "dossier.exported",
        ]
        blocked_reason = (
            "Mandatory safety gate failed because obstacle confidence 0.72 is below 0.85 "
            "and the low-traffic corridor import is unavailable."
        )
        recovery_actions = ["operator approval", "return to dock fallback", "add fresher evidence"]
        sla_state = "warning"

        if self._has_event(events, "approval.granted"):
            status = "running"
            current_node_id = "robot-actuate"
            next_recommendation = "Operator approved the supervised path; synthetic no-op actuation is allowed."
            allowed_actions = ["transition.allowed", "actuation.noop.completed"]
            blocked_reason = None
            recovery_actions = ["trigger return-to-dock fallback"]
            self._set_node(nodes, "robot-option-set", status="complete", elapsedMinutes=8)
            self._set_node(nodes, "robot-operator", status="complete", elapsedMinutes=1)
            self._set_node(nodes, "robot-actuate", status="active", startedAt="09:51", slaState="met")

        if self._has_event(events, "approval.rejected"):
            status = "blocked"
            current_node_id = "robot-operator"
            next_recommendation = "Approval was rejected; select the return-to-dock fallback and seal the receipt."
            allowed_actions = ["fallback.triggered", "option.selected", "dossier.exported"]
            blocked_reason = "Override authority rejected the operator escalation option."
            recovery_actions = ["select return to dock", "seal rejection receipt"]
            self._set_node(nodes, "robot-operator", status="blocked", blockedReason=blocked_reason)

        if self._has_event(events, "sla.breached"):
            status = "escalated"
            current_node_id = "robot-dock"
            selected_option_id = "robot-dock"
            next_recommendation = "Approval SLA breached; return-to-dock fallback is the safe recovery path."
            allowed_actions = ["fallback.triggered", "dossier.exported"]
            blocked_reason = "Operator approval SLA expired before an override decision."
            recovery_actions = ["trigger return-to-dock fallback", "page safety officer"]
            sla_state = "breached"
            self._set_node(nodes, "robot-option-set", status="complete", elapsedMinutes=10, slaState="breached")
            self._set_node(nodes, "robot-operator", status="escalated", elapsedMinutes=10, slaState="breached")
            self._set_node(nodes, "robot-dock", status="active", startedAt="10:00", slaState="met")
            self._set_option(options, "robot-escalate", status="rejected")
            self._set_option(options, "robot-dock", status="selected")

        if self._has_event(events, "fallback.triggered"):
            status = "sealed" if self._has_event(events, "receipt.sealed") else "running"
            current_node_id = "robot-dock"
            selected_option_id = "robot-dock"
            next_recommendation = "Return-to-dock fallback selected and ready for receipt sealing."
            allowed_actions = ["dossier.exported"] if status == "sealed" else ["receipt.sealed"]
            blocked_reason = None
            recovery_actions = []
            self._set_node(nodes, "robot-dock", status="complete", startedAt="10:00", elapsedMinutes=1)
            self._set_node(nodes, "robot-receipt", status="complete" if status == "sealed" else "active")
            self._set_option(options, "robot-escalate", status="rejected")
            self._set_option(options, "robot-dock", status="selected")

        if self._has_event(events, "transition.allowed"):
            status = "running"
            current_node_id = "robot-actuate"
            allowed_actions = ["actuation.noop.completed"]
            self._set_node(nodes, "robot-actuate", status="active", startedAt="09:51", slaState="met")

        if self._has_event(events, "actuation.noop.completed"):
            status = "running"
            current_node_id = "robot-receipt"
            allowed_actions = ["receipt.sealed"]
            next_recommendation = "Synthetic no-op actuation completed; seal the decision receipt."
            self._set_node(nodes, "robot-actuate", status="complete", elapsedMinutes=1, slaState="met")
            self._set_node(nodes, "robot-receipt", status="active", startedAt="09:52", slaState="met")

        if self._has_event(events, "receipt.sealed"):
            status = "sealed"
            current_node_id = "robot-receipt"
            allowed_actions = ["dossier.exported"]
            blocked_reason = None
            recovery_actions = []
            next_recommendation = "Synthetic decision receipt sealed; dossier export is available."
            self._set_node(nodes, "robot-receipt", status="complete", elapsedMinutes=1, slaState="met")

        if self._has_event(events, "receipt.seal.failed"):
            status = "failed"
            current_node_id = "robot-receipt"
            allowed_actions = ["retry_receipt_seal", "dossier.exported"]
            blocked_reason = "Receipt seal failed after preserving event history."
            recovery_actions = ["retry receipt sealing", "export partial audit trail"]
            next_recommendation = "Retry receipt sealing; do not delete or rewrite prior events."
            self._set_node(
                nodes,
                "robot-receipt",
                status="failed",
                startedAt="09:52",
                blockedReason=blocked_reason,
            )

        return {
            "id": ROBOT_RUN_ID,
            "definitionId": ROBOT_WORKFLOW_ID,
            "definitionVersion": "1.0.0",
            "title": "Autonomous Robot Task Approval",
            "scenarioDomain": "robotics",
            "domain": "robotics",
            "entity": "AMR-17 / dock C reroute",
            "summary": (
                "AEGIS is holding a robot reroute while comparing wait, reroute, return-to-dock, "
                "and operator escalation."
            ),
            "isSynthetic": True,
            "status": status,
            "currentNodeId": current_node_id,
            "selectedOptionId": selected_option_id,
            "startedAt": "09:41",
            "updatedAt": events[-1]["occurredAt"],
            "closedAt": events[-1]["occurredAt"] if status in {"sealed", "cancelled"} else None,
            "autonomyLevel": "supervised_autonomy",
            "generationMode": "recommend",
            "confidence": 88,
            "riskScore": 67,
            "slaState": sla_state,
            "allowedActions": allowed_actions,
            "blockedReason": blocked_reason,
            "recoveryActions": recovery_actions,
            "nextRecommendation": next_recommendation,
            "eventCursor": self._event_cursor(events),
            "nodes": nodes,
            "options": options,
            "events": deepcopy(events),
            "timeline": self._timeline(events),
            "evidence": deepcopy(EVIDENCE_PAYLOADS),
            "confidenceSignals": {
                "ruleConfidence": 1.0,
                "evidenceTrustScore": 0.91,
                "optionConfidence": 0.93,
                "autonomyEligibility": {
                    "eligible": False,
                    "reason": "Obstacle confidence is below the certified 0.85 threshold.",
                },
                "convergenceState": "GOAL_REACHED",
                "policyIntegrity": {
                    "ruleVersionHash": _stable_hash(ROBOT_RULE_TEXT),
                    "importTreeHash": IMPORT_TREE_HASH,
                    "validationStatus": "valid",
                },
                "authorityState": "approval_granted"
                if self._has_event(events, "approval.granted")
                else "approval_requested",
                "residualRisk": [
                    "Obstacle classification remains below certified threshold.",
                    "Low-traffic corridor is unavailable by imported site policy.",
                ],
            },
            "ruleGate": self.evaluate_gate({}),
            "receipt": self._receipt(events),
        }

    def _timeline(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        labels = {
            "workflow.created": ("SIGNATURE", "Workflow created"),
            "workflow.validated": ("SIGNATURE", "Workflow validated"),
            "run.started": ("ASSERTED", "Run started"),
            "node.entered": ("ASSERTED", "Node entered"),
            "rule.evaluation.completed": ("INFERRED", "Safety gate evaluated"),
            "options.generated": ("INFERRED", "Options generated"),
            "option.selected": ("APPROVAL", "Option selected"),
            "approval.requested": ("APPROVAL", "Approval requested"),
            "approval.granted": ("APPROVAL", "Approval granted"),
            "approval.rejected": ("APPROVAL", "Approval rejected"),
            "transition.allowed": ("INFERRED", "Transition allowed"),
            "transition.denied": ("INFERRED", "Transition denied"),
            "actuation.allowed": ("SIGNATURE", "Actuation allowed"),
            "actuation.noop.completed": ("SIGNATURE", "No-op actuation completed"),
            "sla.breached": ("SLA", "SLA breached"),
            "fallback.triggered": ("SLA", "Fallback triggered"),
            "receipt.sealed": ("SIGNATURE", "Receipt sealed"),
            "receipt.seal.failed": ("SIGNATURE", "Receipt seal failed"),
        }
        timeline = []
        for event in events:
            layer, label = labels.get(event["type"], ("ASSERTED", event["type"]))
            timeline.append(
                {
                    "id": event["eventId"],
                    "time": event["occurredAt"],
                    "layer": layer,
                    "actor": event["actor"]["id"],
                    "event": label,
                    "detail": self._event_detail(event),
                    "sequence": event["sequence"],
                    "eventType": event["type"],
                    "evidenceRefs": event.get("evidenceRefs", []),
                }
            )
        return timeline

    def _event_detail(self, event: dict[str, Any]) -> str:
        if event["type"] == "rule.evaluation.completed":
            return "Safety boundary false: obstacle confidence below threshold."
        if event["type"] == "option.selected":
            return event["payload"].get("selectionReason", "Selected option recorded.")
        if event["type"] == "approval.granted":
            return event["payload"].get("rationale", "Operator approval granted.")
        if event["type"] == "approval.rejected":
            return event["payload"].get("rationale", "Operator approval rejected.")
        if event["type"] == "sla.breached":
            return event["payload"].get("reason", "Approval SLA breached.")
        if event["type"] == "receipt.seal.failed":
            return event["payload"].get("error", "Receipt seal failed.")
        return event["type"].replace(".", " ")

    def _receipt(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        sealed = self._has_event(events, "receipt.sealed")
        failed = self._has_event(events, "receipt.seal.failed")
        receipt_type = "synthetic_robot_decision_receipt"
        sequence_range = [events[0]["sequence"], events[-1]["sequence"]]
        payload = {
            "runId": ROBOT_RUN_ID,
            "sequenceRange": sequence_range,
            "selectedOptionId": "robot-dock" if self._has_event(events, "fallback.triggered") else "robot-escalate",
            "ruleVersionHash": _stable_hash(ROBOT_RULE_TEXT),
            "importTreeHash": IMPORT_TREE_HASH,
        }
        return {
            "receiptId": "receipt-wf-robot-124",
            "receiptType": receipt_type,
            "runId": ROBOT_RUN_ID,
            "nodeId": "robot-receipt",
            "transitionId": "transition-robot-operator-to-actuate",
            "eventSequenceRange": sequence_range,
            "actor": "aegis-ledger",
            "role": "signature authority",
            "timestamp": events[-1]["occurredAt"],
            "elapsedTime": "synthetic",
            "slaState": "breached" if self._has_event(events, "sla.breached") else "met",
            "selectedOption": payload["selectedOptionId"],
            "rejectedOptions": ["robot-reroute"],
            "evidenceRefs": [evidence["id"] for evidence in EVIDENCE_PAYLOADS],
            "ruleVersionHash": payload["ruleVersionHash"],
            "importTreeHash": IMPORT_TREE_HASH,
            "convergenceState": "GOAL_REACHED",
            "approvalStatus": "granted"
            if self._has_event(events, "approval.granted")
            else "rejected"
            if self._has_event(events, "approval.rejected")
            else "requested",
            "overrideRationale": "Synthetic no-op supervised actuation only",
            "fallbackTrigger": "sla.breached" if self._has_event(events, "fallback.triggered") else None,
            "previousReceiptHash": "sha256:synthetic-genesis",
            "receiptHash": _stable_hash(payload),
            "signatureState": "failed" if failed else "sealed" if sealed else "pending",
            "sanitization": {
                "synthetic": True,
                "containsCustomerData": False,
                "containsPhi": False,
                "containsSecrets": False,
            },
        }

    def _validate_rule(self) -> dict[str, Any]:
        return _validation_to_dict(self._validation_service.validate(ROBOT_RULE_TEXT, ROBOT_RULE_NAME))

    @staticmethod
    def _has_event(events: list[dict[str, Any]], event_type: str) -> bool:
        return any(event["type"] == event_type for event in events)

    @staticmethod
    def _next_sequence(events: list[dict[str, Any]]) -> int:
        return max(event["sequence"] for event in events) + 1

    @staticmethod
    def _event_cursor(events: list[dict[str, Any]]) -> dict[str, Any]:
        latest = events[-1]
        return {
            "latestSequence": latest["sequence"],
            "latestEventId": latest["eventId"],
            "latestHash": _stable_hash(latest),
        }

    def _pre_state(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        run = self._project_run(events)
        return {"runStatus": run["status"], "nodeId": run["currentNodeId"]}

    @staticmethod
    def _set_node(nodes: list[dict[str, Any]], node_id: str, **updates: Any) -> None:
        for node in nodes:
            if node["id"] == node_id:
                node.update(updates)
                return

    @staticmethod
    def _set_option(options: list[dict[str, Any]], option_id: str, **updates: Any) -> None:
        for option in options:
            if option["id"] == option_id:
                option.update(updates)
                return


_runtime = SyntheticAegisWorkflowRuntime()


def get_synthetic_aegis_runtime() -> SyntheticAegisWorkflowRuntime:
    return _runtime


def reset_synthetic_aegis_runtime() -> None:
    _runtime.reset()
