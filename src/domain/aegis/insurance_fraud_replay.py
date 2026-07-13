"""Synthetic insurance fraud replay scenario for AEGIS workflow contracts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from src.domain.aegis.rule_store import AEGIS_PRODUCT, rule_version_hash, stable_hash
from src.services.rule_validation_service import RuleValidationService, ValidationResult


INSURANCE_WORKFLOW_ID = "insurance-flood-claim-fraud-gate"
INSURANCE_DEFAULT_RUN_ID = "wf-insurance-fraud-flood-001"
INSURANCE_RULE_NAME = "synthetic_insurance_flood_claim_fraud_gate"
INSURANCE_RULE_VERSION = "synthetic-0.1"
FRAUD_APPROVAL_ID = "approval-fraud-lead-1"
STATE_SCHEMA_VERSION = 1


class InsuranceFraudAuthorizationError(PermissionError):
    """Raised when the synthetic fraud approval actor lacks authority."""


class InsuranceFraudEventSequenceError(ValueError):
    """Raised when an insurance replay event is appended out of order."""


class InsuranceFraudIdempotencyConflictError(ValueError):
    """Raised when an idempotency key is replayed with different content."""


def _default_state_path() -> Path:
    configured = os.environ.get("AEGIS_INSURANCE_REPLAY_STATE_PATH")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "inferra" / "aegis_insurance_fraud_replay_state.json"


INSURANCE_RULE_TEXT = """FIXED maximum payout without fraud lead approval IS 25000
INPUT claim form complete AS BOOLEAN
INPUT policy active on loss date AS BOOLEAN
INPUT flood damage covered AS BOOLEAN
INPUT exclusion applies AS BOOLEAN
INPUT public flood context matches postcode AS BOOLEAN
INPUT evidence pack complete AS BOOLEAN
INPUT duplicate bank account detected AS BOOLEAN
INPUT repair invoice anomaly detected AS BOOLEAN
INPUT staff conflict detected AS BOOLEAN
INPUT payment requested before inspection AS BOOLEAN
INPUT claim amount AS NUMBER

claim completeness gate satisfied
    AND claim form complete
    AND evidence pack complete

coverage exclusion gate satisfied
    AND policy active on loss date
    AND flood damage covered
    AND NOT exclusion applies
    AND public flood context matches postcode

fraud signal escalation required
    OR duplicate bank account detected
    OR repair invoice anomaly detected
    OR staff conflict detected

intervention gate requires payout freeze
    OR payment requested before inspection
    OR claim amount > maximum payout without fraud lead approval

claim payout may be allowed
    AND claim completeness gate satisfied
    AND coverage exclusion gate satisfied
    AND NOT fraud signal escalation required
    AND NOT intervention gate requires payout freeze

claim payout must be denied
    OR NOT coverage exclusion gate satisfied

claim evidence must be requested
    OR NOT claim completeness gate satisfied
"""

INSURANCE_RULE_HASH = rule_version_hash(INSURANCE_RULE_TEXT)

PUBLIC_CONTEXT_FIXTURE = {
    "contextId": "public-flood-context-ipswich-4305-202603",
    "status": "cached_fallback",
    "source": "cached_public_replay_fixture",
    "sourceBoundary": "approved_public_context_or_cached_fixture",
    "liveFetchAttempted": False,
    "failureMode": "live_public_feed_disabled_for_deterministic_replay",
    "postcode": "4305",
    "eventWindow": {
        "from": "2026-03-04T00:00:00Z",
        "to": "2026-03-06T23:59:59Z",
    },
    "rainfallMm72h": 221.4,
    "floodWatch": True,
    "riverGaugeState": "major_flood",
    "freshness": "fixture_snapshot_2026-06-14",
    "sanitization": {
        "synthetic": True,
        "containsCustomerData": False,
        "containsPhi": False,
        "containsSecrets": False,
    },
}
PUBLIC_CONTEXT_HASH = stable_hash(PUBLIC_CONTEXT_FIXTURE)

TRIGGER_POLICY_HASH = stable_hash(
    {
        "contract": "insurance-fraud-trigger-policy-v1",
        "actions": {
            "allow_payout": "payout.allow",
            "request_evidence": "evidence.request",
            "escalate_fraud_review": "fraud.escalate",
            "freeze_payout": "payout.freeze",
            "deny_reject": "claim.deny",
        },
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _actor(kind: str, actor_id: str, role: str) -> dict[str, str]:
    return {"kind": kind, "id": actor_id, "role": role}


def _condition_set(conditions: list[str], evidence_refs: list[str] | None = None) -> list[dict[str, Any]]:
    return [
        {"condition": condition, "evidenceRefs": evidence_refs or []}
        for condition in conditions
        if condition.strip()
    ]


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


def _content_hash(payload: Any) -> str:
    return stable_hash(payload)


def _base_evidence(
    evidence_id: str,
    label: str,
    source_layer: str,
    value: Any,
    value_type: str,
    source_label: str,
    source_uri: str,
    *,
    available: bool = True,
    supports: list[str] | None = None,
    opposes: list[str] | None = None,
) -> dict[str, Any]:
    evidence = {
        "id": evidence_id,
        "label": label,
        "sourceLayer": source_layer,
        "value": value,
        "valueType": value_type,
        "sourceLabel": source_label,
        "sourceUri": source_uri,
        "status": "available" if available else "missing",
        "collectedAt": "2026-03-07T04:15:00Z" if available else None,
        "freshnessState": "fresh" if available else "missing",
        "supports": supports or [],
        "opposes": opposes or [],
        "sanitization": {
            "synthetic": True,
            "containsCustomerData": False,
            "containsPhi": False,
            "containsSecrets": False,
        },
    }
    if available:
        evidence["contentHash"] = _content_hash(
            {"id": evidence_id, "value": value, "sourceUri": source_uri}
        )
    return evidence


BASE_CLAIM_CONTEXT = {
    "claim": {
        "claimId": "synthetic-claim-flood-4305-001",
        "lossType": "warehouse_flood_damage",
        "lossPostcode": "4305",
        "lodgedAt": "2026-03-07T01:40:00Z",
        "amountAud": 18450,
        "items": ["stock spoilage", "floor remediation", "temporary storage"],
    },
    "customer": {
        "customerId": "synthetic-customer-industrial-017",
        "segment": "small_business",
        "tenureMonths": 42,
        "priorClaimCount24m": 0,
    },
    "policy": {
        "policyId": "synthetic-commercial-property-warehouse",
        "activeOnLossDate": True,
        "coverage": ["storm", "flood", "stock_spoilage"],
        "exclusions": ["gradual_seepage", "pre_existing_damage"],
        "claimLimitAud": 50000,
    },
    "payment": {
        "paymentInstructionId": "synthetic-payment-clean-001",
        "method": "eft",
        "accountFingerprint": "sha256:synthetic-account-clean",
        "requestedBeforeInspection": False,
    },
    "staff": {
        "adjusterId": "synthetic-adjuster-11",
        "fraudLeadId": "synthetic-fraud-lead-02",
        "staffConflictDetected": False,
    },
}


def _case(
    branch_id: str,
    run_id: str,
    expected_outcome: str,
    expected_option_id: str,
    facts: dict[str, Any],
    *,
    claim_overrides: dict[str, Any] | None = None,
    payment_overrides: dict[str, Any] | None = None,
    staff_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = deepcopy(BASE_CLAIM_CONTEXT)
    context["claim"].update(claim_overrides or {})
    context["payment"].update(payment_overrides or {})
    context["staff"].update(staff_overrides or {})
    context["publicContext"] = deepcopy(PUBLIC_CONTEXT_FIXTURE)
    return {
        "branchId": branch_id,
        "runId": run_id,
        "caseId": f"synthetic-{branch_id}",
        "expectedOutcome": expected_outcome,
        "expectedOptionId": expected_option_id,
        "facts": facts,
        "context": context,
        "inputHash": stable_hash(
            {
                "branchId": branch_id,
                "facts": facts,
                "context": context,
                "publicContextHash": PUBLIC_CONTEXT_HASH,
            }
        ),
    }


BASE_FACTS = {
    "claim form complete": True,
    "policy active on loss date": True,
    "flood damage covered": True,
    "exclusion applies": False,
    "public flood context matches postcode": True,
    "evidence pack complete": True,
    "duplicate bank account detected": False,
    "repair invoice anomaly detected": False,
    "staff conflict detected": False,
    "payment requested before inspection": False,
    "claim amount": 18450,
}

REPLAY_CASES: dict[str, dict[str, Any]] = {
    "allow_payout": _case(
        "allow_payout",
        "wf-insurance-fraud-allow",
        "allow_payout",
        "allow_payout",
        deepcopy(BASE_FACTS),
    ),
    "request_evidence": _case(
        "request_evidence",
        "wf-insurance-fraud-request-evidence",
        "request_evidence",
        "request_evidence",
        {**BASE_FACTS, "evidence pack complete": False},
    ),
    "escalate_fraud_review": _case(
        "escalate_fraud_review",
        INSURANCE_DEFAULT_RUN_ID,
        "escalate_fraud_review",
        "escalate_fraud_review",
        {
            **BASE_FACTS,
            "duplicate bank account detected": True,
            "repair invoice anomaly detected": True,
        },
        payment_overrides={"accountFingerprint": "sha256:synthetic-account-shared"},
    ),
    "freeze_payout": _case(
        "freeze_payout",
        "wf-insurance-fraud-freeze",
        "freeze_payout",
        "freeze_payout",
        {
            **BASE_FACTS,
            "payment requested before inspection": True,
            "claim amount": 33600,
        },
        claim_overrides={"amountAud": 33600},
        payment_overrides={"requestedBeforeInspection": True},
    ),
    "deny_reject": _case(
        "deny_reject",
        "wf-insurance-fraud-deny",
        "deny_reject",
        "deny_reject",
        {
            **BASE_FACTS,
            "public flood context matches postcode": False,
            "exclusion applies": True,
        },
    ),
}

CASE_BY_RUN_ID = {case["runId"]: case for case in REPLAY_CASES.values()}

INSURANCE_OPTIONS = [
    {
        "id": "allow_payout",
        "label": "Allow payout",
        "status": "available",
        "action": "payout.allow",
        "confidence": 94,
        "risk": 14,
        "requiredRole": "claims automation",
        "requiresApproval": False,
        "supportingEvidenceRefs": ["ev-claim-form", "ev-policy", "ev-public-flood-context"],
        "opposingEvidenceRefs": [],
        "constraints": ["completeness, coverage, fraud, and intervention gates are satisfied"],
        "rationale": "Synthetic claim passes completeness, coverage, and fraud gates.",
    },
    {
        "id": "request_evidence",
        "label": "Request evidence",
        "status": "available",
        "action": "evidence.request",
        "confidence": 91,
        "risk": 28,
        "requiredRole": "claims handler",
        "requiresApproval": False,
        "supportingEvidenceRefs": ["ev-claim-form", "ev-public-flood-context"],
        "opposingEvidenceRefs": ["ev-inspection-report"],
        "constraints": ["missing required inspection evidence blocks payout release"],
        "rationale": "The evidence pack is incomplete, so the workflow must ask for inspection proof.",
    },
    {
        "id": "escalate_fraud_review",
        "label": "Escalate fraud review",
        "status": "available",
        "action": "fraud.escalate",
        "confidence": 88,
        "risk": 79,
        "requiredRole": "fraud lead",
        "requiresApproval": True,
        "supportingEvidenceRefs": ["ev-payment-instruction", "ev-repair-invoice"],
        "opposingEvidenceRefs": [],
        "constraints": ["fraud lead approval required before payout movement"],
        "rationale": "Duplicate bank and invoice anomaly signals require fraud review.",
    },
    {
        "id": "freeze_payout",
        "label": "Freeze payout",
        "status": "available",
        "action": "payout.freeze",
        "confidence": 93,
        "risk": 71,
        "requiredRole": "fraud lead",
        "requiresApproval": True,
        "supportingEvidenceRefs": ["ev-payment-instruction", "ev-public-flood-context"],
        "opposingEvidenceRefs": [],
        "constraints": ["payment requested before inspection or high value requires fraud lead approval"],
        "rationale": "Intervention gate requires a temporary payout freeze.",
    },
    {
        "id": "deny_reject",
        "label": "Deny or reject claim",
        "status": "available",
        "action": "claim.deny",
        "confidence": 86,
        "risk": 64,
        "requiredRole": "fraud lead",
        "requiresApproval": True,
        "supportingEvidenceRefs": ["ev-policy", "ev-public-flood-context"],
        "opposingEvidenceRefs": [],
        "constraints": ["coverage or exclusion gate failed"],
        "rationale": "Coverage context or exclusion facts contradict the flood claim.",
    },
]


def _evidence_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    facts = case["facts"]
    context = case["context"]
    return [
        _base_evidence(
            "ev-claim-form",
            "Synthetic claim form",
            "ASSERTED",
            context["claim"],
            "json",
            "synthetic_claim_intake:no_real_customer",
            f"synthetic://insurance/claims/{case['caseId']}/claim-form",
            supports=["claim completeness gate satisfied"],
        ),
        _base_evidence(
            "ev-policy",
            "Synthetic policy snapshot",
            "ASSERTED",
            context["policy"],
            "json",
            "synthetic_policy_admin:no_real_policy",
            f"synthetic://insurance/policies/{context['policy']['policyId']}",
            supports=["coverage exclusion gate satisfied"],
        ),
        _base_evidence(
            "ev-payment-instruction",
            "Synthetic payment instruction",
            "ASSERTED",
            context["payment"],
            "json",
            "synthetic_payment_system:no_real_bank_account",
            f"synthetic://insurance/payments/{context['payment']['paymentInstructionId']}",
            supports=["fraud signal escalation required", "intervention gate requires payout freeze"],
        ),
        _base_evidence(
            "ev-public-flood-context",
            "Cached public flood context",
            "SEMANTIC",
            context["publicContext"],
            "json",
            "cached_public_context_fixture",
            "synthetic://public-context/flood/postcode/4305/2026-03",
            supports=["coverage exclusion gate satisfied"],
            opposes=[] if facts["public flood context matches postcode"] else ["coverage exclusion gate satisfied"],
        )
        | {"contentHash": PUBLIC_CONTEXT_HASH},
        _base_evidence(
            "ev-warehouse-photos",
            "Synthetic warehouse photo set",
            "ASSERTED",
            {"photoCount": 4, "visibleWaterLine": True, "metadataSynthetic": True},
            "json",
            "synthetic_evidence_bucket:no_real_photos",
            f"synthetic://insurance/claims/{case['caseId']}/photos",
            supports=["claim completeness gate satisfied", "coverage exclusion gate satisfied"],
        ),
        _base_evidence(
            "ev-repair-invoice",
            "Synthetic repair invoice",
            "ASSERTED",
            {
                "invoiceId": f"synthetic-invoice-{case['branchId']}",
                "amountAud": context["claim"]["amountAud"],
                "anomalyDetected": facts["repair invoice anomaly detected"],
            },
            "json",
            "synthetic_vendor_invoice:no_real_vendor",
            f"synthetic://insurance/claims/{case['caseId']}/repair-invoice",
            supports=["fraud signal escalation required"] if facts["repair invoice anomaly detected"] else [],
        ),
        _base_evidence(
            "ev-staff-assignment",
            "Synthetic staff assignment",
            "ASSERTED",
            context["staff"],
            "json",
            "synthetic_claim_ops:no_real_staff",
            f"synthetic://insurance/claims/{case['caseId']}/staff",
            supports=["fraud signal escalation required"] if facts["staff conflict detected"] else [],
        ),
        _base_evidence(
            "ev-inspection-report",
            "Synthetic inspection report",
            "ASSERTED",
            {"inspectionId": f"synthetic-inspection-{case['branchId']}", "floodDamageConfirmed": True},
            "json",
            "synthetic_loss_adjuster:no_real_inspection",
            f"synthetic://insurance/claims/{case['caseId']}/inspection",
            available=bool(facts["evidence pack complete"]),
            supports=["claim completeness gate satisfied"],
        ),
    ]


BASE_NODES = [
    {
        "id": "claim-intake",
        "label": "Claim intake",
        "type": "REQUEST",
        "status": "complete",
        "owner": "claims ingestion",
        "role": "claims automation",
        "startedAt": "08:30",
        "elapsedMinutes": 2,
        "slaMinutes": 5,
        "slaState": "met",
        "ruleRef": "claim completeness gate satisfied",
        "ruleSessionId": "synthetic-rule-session-insurance-fraud",
        "requiredEvidenceRefs": ["ev-claim-form", "ev-policy"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["synthetic claim replay input loaded"],
        "exitCriteria": ["claim, customer, policy, payment, evidence, and staff fields present"],
        "blockedReason": None,
        "recoveryActions": [],
        "conditionMetadata": {
            "entryConditions": _condition_set(["synthetic claim replay input loaded"]),
            "exitConditions": _condition_set(
                ["claim, customer, policy, payment, evidence, and staff fields present"],
                ["ev-claim-form", "ev-policy"],
            ),
        },
    },
    {
        "id": "public-context",
        "label": "Flood context",
        "type": "CONTEXT",
        "status": "complete",
        "owner": "public context cache",
        "role": "context provider",
        "startedAt": "08:32",
        "elapsedMinutes": 1,
        "slaMinutes": 2,
        "slaState": "met",
        "ruleRef": "public flood context matches postcode",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-public-flood-context"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["approved public context boundary available"],
        "exitCriteria": ["cached context hash attached when live feed unavailable"],
        "blockedReason": None,
        "recoveryActions": ["use cached public context replay fixture"],
        "conditionMetadata": {
            "entryConditions": _condition_set(["approved public context boundary available"]),
            "exitConditions": _condition_set(
                ["cached context hash attached when live feed unavailable"],
                ["ev-public-flood-context"],
            ),
        },
    },
    {
        "id": "fraud-gate",
        "label": "Fraud gate",
        "type": "RULE_GATE",
        "status": "complete",
        "owner": "INFERRA AEGIS",
        "role": "policy gate",
        "startedAt": "08:33",
        "elapsedMinutes": 1,
        "slaMinutes": 1,
        "slaState": "met",
        "ruleRef": INSURANCE_RULE_NAME,
        "ruleSessionId": "synthetic-rule-session-insurance-fraud",
        "requiredEvidenceRefs": [
            "ev-claim-form",
            "ev-policy",
            "ev-payment-instruction",
            "ev-public-flood-context",
        ],
        "producedEvidenceRefs": [],
        "entryCriteria": ["claim and public context facts grounded"],
        "exitCriteria": ["completeness, coverage, fraud signal, and intervention gates evaluated"],
        "blockedReason": None,
        "recoveryActions": [],
        "conditionMetadata": {
            "entryConditions": _condition_set(
                ["claim and public context facts grounded"],
                ["ev-claim-form", "ev-public-flood-context"],
            ),
            "exitConditions": _condition_set(
                ["completeness, coverage, fraud signal, and intervention gates evaluated"],
                ["ev-claim-form", "ev-policy", "ev-payment-instruction", "ev-public-flood-context"],
            ),
        },
    },
    {
        "id": "intervention-options",
        "label": "Intervention options",
        "type": "OPTION_SET",
        "status": "active",
        "owner": "AEGIS",
        "role": "options engine",
        "startedAt": "08:34",
        "elapsedMinutes": 0,
        "slaMinutes": 3,
        "slaState": "met",
        "ruleRef": "trigger policy maps rule outcome to governed action",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-claim-form", "ev-policy", "ev-public-flood-context"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["fraud gate outcome available"],
        "exitCriteria": ["governed option selected with idempotency key"],
        "blockedReason": None,
        "recoveryActions": ["request evidence", "route fraud lead approval", "freeze payout"],
        "conditionMetadata": {
            "entryConditions": _condition_set(["fraud gate outcome available"]),
            "exitConditions": _condition_set(["governed option selected with idempotency key"]),
        },
    },
    {
        "id": "fraud-lead-approval",
        "label": "Fraud lead approval",
        "type": "HUMAN_APPROVAL",
        "status": "scheduled",
        "owner": "synthetic fraud lead",
        "role": "fraud lead",
        "startedAt": "-",
        "elapsedMinutes": 0,
        "slaMinutes": 15,
        "slaState": "not_started",
        "ruleRef": "fraud lead approval required",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-payment-instruction", "ev-repair-invoice"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["selected action requires fraud lead approval"],
        "exitCriteria": ["fraud lead grants or rejects selected intervention"],
        "blockedReason": None,
        "recoveryActions": ["reject intervention", "freeze payout", "request evidence"],
        "conditionMetadata": {
            "entryConditions": _condition_set(["selected action requires fraud lead approval"]),
            "exitConditions": _condition_set(["fraud lead grants or rejects selected intervention"]),
        },
    },
    {
        "id": "receipt-dossier",
        "label": "Receipt and dossier",
        "type": "RECEIPT_SEAL",
        "status": "scheduled",
        "owner": "AEGIS ledger",
        "role": "signature authority",
        "startedAt": "-",
        "elapsedMinutes": 0,
        "slaMinutes": 1,
        "slaState": "not_started",
        "ruleRef": "insurance fraud replay receipt can be sealed",
        "ruleSessionId": None,
        "requiredEvidenceRefs": ["ev-claim-form", "ev-policy", "ev-public-flood-context"],
        "producedEvidenceRefs": [],
        "entryCriteria": ["terminal action event available"],
        "exitCriteria": ["receipt hash and event hashes sealed"],
        "blockedReason": None,
        "recoveryActions": ["retry receipt sealing", "export partial dossier"],
        "conditionMetadata": {
            "entryConditions": _condition_set(["terminal action event available"]),
            "exitConditions": _condition_set(["receipt hash and event hashes sealed"]),
        },
    },
]


class InsuranceFraudReplayRuntime:
    """Replay runtime for the flood-damaged warehouse fraud gate.

    The runtime keeps an in-process cache for TestClient speed, but persists the
    synthetic replay state to a small JSON snapshot so Uvicorn workers in the
    same deployed API container observe the same approval and transition events.
    """

    def __init__(self, state_path: str | Path | None = None) -> None:
        self._validation_service = RuleValidationService()
        self._state_path = Path(state_path) if state_path is not None else _default_state_path()
        self._state_lock = RLock()
        self._run_events: dict[str, list[dict[str, Any]]] = {}
        self._idempotency: dict[str, dict[str, dict[str, Any]]] = {}
        self._run_cases: dict[str, dict[str, Any]] = {}
        if not self._load_state():
            self.reset()

    def reset(self) -> None:
        with self._state_lock:
            self._run_events = {}
            self._idempotency = {}
            self._run_cases = {}
            self._seed_case(REPLAY_CASES["escalate_fraud_review"])
            self._save_state()

    def _load_state(self) -> bool:
        with self._state_lock:
            if not self._state_path.exists():
                return False
            try:
                snapshot = json.loads(self._state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return False
            if snapshot.get("schemaVersion") != STATE_SCHEMA_VERSION:
                return False
            run_events = snapshot.get("runEvents")
            run_cases = snapshot.get("runCases")
            if not isinstance(run_events, dict) or not isinstance(run_cases, dict):
                return False
            self._run_events = deepcopy(run_events)
            self._run_cases = deepcopy(run_cases)
            self._rebuild_idempotency()
            return bool(self._run_events)

    def _sync_from_state(self) -> None:
        self._load_state()

    def _save_state(self) -> None:
        with self._state_lock:
            snapshot = {
                "schemaVersion": STATE_SCHEMA_VERSION,
                "runEvents": self._run_events,
                "runCases": self._run_cases,
            }
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._state_path.with_name(f"{self._state_path.name}.{os.getpid()}.tmp")
            tmp_path.write_text(json.dumps(snapshot, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp_path, self._state_path)

    def _rebuild_idempotency(self) -> None:
        self._idempotency = {
            run_id: {
                event["idempotencyKey"]: event
                for event in events
                if isinstance(event, dict) and event.get("idempotencyKey")
            }
            for run_id, events in self._run_events.items()
        }

    def owns_workflow_id(self, workflow_id: str) -> bool:
        return workflow_id == INSURANCE_WORKFLOW_ID

    def owns_run_id(self, run_id: str) -> bool:
        self._sync_from_state()
        return run_id in self._run_events or run_id in CASE_BY_RUN_ID or run_id.startswith("wf-insurance-fraud")

    def list_workflows(self) -> dict[str, Any]:
        return {"workflows": [self.get_workflow(INSURANCE_WORKFLOW_ID)]}

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        if workflow_id != INSURANCE_WORKFLOW_ID:
            raise LookupError(f"Unknown AEGIS workflow '{workflow_id}'")
        return {
            "id": INSURANCE_WORKFLOW_ID,
            "version": "1.0.0",
            "title": "Flood-Damaged Warehouse Claim Fraud Gate",
            "domain": "insurance",
            "scenarioDomain": "insurance",
            "isSynthetic": True,
            "status": "active",
            "autonomyPolicy": {
                "level": "supervised_autonomy",
                "humanApprovalRequiredForFraudActions": True,
                "certifiedTemplate": False,
                "autoApplyEnabled": False,
            },
            "roles": [
                {"id": "claims-automation", "label": "claims automation", "authorityScopes": ["propose"]},
                {"id": "claims-handler", "label": "claims handler", "authorityScopes": ["request_evidence"]},
                {"id": "fraud-lead", "label": "fraud lead", "authorityScopes": ["approve", "reject"]},
                {"id": "signature-authority", "label": "signature authority", "authorityScopes": ["seal"]},
            ],
            "nodes": deepcopy(BASE_NODES),
            "transitions": [
                {
                    "fromNodeId": "fraud-gate",
                    "toNodeId": "intervention-options",
                    "triggerEvent": "rule.evaluation.completed",
                    "guard": "claim fraud gate outcome available",
                },
                {
                    "fromNodeId": "intervention-options",
                    "toNodeId": "fraud-lead-approval",
                    "triggerEvent": "option.selected",
                    "guard": "selected action requires fraud lead approval",
                    "recoveryRoute": "receipt-dossier",
                },
                {
                    "fromNodeId": "fraud-lead-approval",
                    "toNodeId": "receipt-dossier",
                    "triggerEvent": "approval.granted OR approval.rejected",
                    "guard": "fraud lead authority present",
                },
            ],
            "compiledPolicyRefs": self._compiled_policy_refs(),
            "triggerPolicies": self._trigger_policy_map(),
            "replayInputs": self.replay_inputs(),
            "receiptPolicy": {
                "sealOnEvents": ["receipt.sealed"],
                "requiredFields": [
                    "ruleOutcome",
                    "selectedOption",
                    "approvalActor",
                    "evidenceRefs",
                    "policyHashes",
                    "eventHashes",
                ],
            },
            "dossierSchema": {
                "format": "json",
                "includes": ["replayInputs", "eventLog", "evidence", "receipt", "publicContext"],
            },
        }

    def replay_inputs(self) -> dict[str, Any]:
        return {
            "workflowId": INSURANCE_WORKFLOW_ID,
            "defaultRunId": INSURANCE_DEFAULT_RUN_ID,
            "publicContext": deepcopy(PUBLIC_CONTEXT_FIXTURE),
            "publicContextHash": PUBLIC_CONTEXT_HASH,
            "branches": [
                {
                    "branchId": case["branchId"],
                    "runId": case["runId"],
                    "expectedOutcome": case["expectedOutcome"],
                    "expectedOptionId": case["expectedOptionId"],
                    "inputHash": case["inputHash"],
                    "idempotencySeed": f"{case['runId']}:replay",
                }
                for case in REPLAY_CASES.values()
            ],
        }

    def validate_workflow(self, workflow_id: str) -> dict[str, Any]:
        self.get_workflow(workflow_id)
        validation = self._validate_rule()
        return {
            "workflowId": workflow_id,
            "valid": validation["valid"],
            "ruleGateValidation": validation,
            "invariants": [
                {"code": "SYNTHETIC_ONLY", "valid": True},
                {"code": "PUBLIC_CONTEXT_CACHE_FALLBACK", "valid": True},
                {"code": "APPEND_ONLY_EVENTS", "valid": True},
                {"code": "FRAUD_LEAD_ROLE_ENFORCED", "valid": True},
            ],
        }

    def compile_workflow(self, workflow_id: str) -> dict[str, Any]:
        self.get_workflow(workflow_id)
        return {
            "workflowId": workflow_id,
            "compiledPolicyRefs": self._compiled_policy_refs(),
            "triggerPolicies": self._trigger_policy_map(),
            "ruleText": INSURANCE_RULE_TEXT,
            "replayInputs": self.replay_inputs(),
            "grammarExtensionRequired": False,
        }

    def create_run(self, body: dict[str, Any]) -> dict[str, Any]:
        self._sync_from_state()
        workflow_id = str(body.get("workflowId") or INSURANCE_WORKFLOW_ID)
        if workflow_id != INSURANCE_WORKFLOW_ID:
            raise LookupError(f"Unknown AEGIS workflow '{workflow_id}'")
        case = self._case_from_request(body)
        run_id = str(body.get("runId") or case["runId"])
        if body.get("reset", False) or run_id not in self._run_events:
            seeded = deepcopy(case)
            seeded["runId"] = run_id
            self._seed_case(seeded)
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        events = self._events_for(run_id)
        return {"run": self._project_run(run_id, events)}

    def get_timeline(self, run_id: str) -> dict[str, Any]:
        events = self._events_for(run_id)
        return {
            "runId": run_id,
            "eventCursor": self._event_cursor(events),
            "events": deepcopy(events),
            "timeline": self._timeline(events),
        }

    def get_options(self, run_id: str) -> dict[str, Any]:
        events = self._events_for(run_id)
        run = self._project_run(run_id, events)
        return {
            "runId": run_id,
            "selectedOptionId": run["selectedOptionId"],
            "recommendedOptionId": run["recommendedOptionId"],
            "options": run["options"],
        }

    def append_event(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        events = self._events_for(run_id)
        event_type = str(body.get("type") or "").strip()
        idempotency_key = str(body.get("idempotencyKey") or "").strip()
        if not event_type:
            raise ValueError("Event type is required")
        if not idempotency_key:
            raise ValueError("idempotencyKey is required for AEGIS workflow writes")

        actor = body.get("actor") or _actor("system", "aegis-insurance-replay", "workflow runtime")
        payload = body.get("payload") or {}
        evidence_refs = _string_list(body.get("evidenceRefs"))
        rule_refs = _string_list(body.get("ruleRefs"))
        receipt_refs = _string_list(body.get("receiptRefs"))
        fingerprint = stable_hash(
            {
                "eventType": event_type,
                "actor": actor,
                "payload": payload,
                "evidenceRefs": evidence_refs,
                "ruleRefs": rule_refs,
                "receiptRefs": receipt_refs,
            }
        )
        existing = self._idempotency[run_id].get(idempotency_key)
        if existing:
            if existing.get("contentHash") != fingerprint:
                raise InsuranceFraudIdempotencyConflictError(
                    f"Insurance replay idempotency key '{idempotency_key}' was reused with different content"
                )
            return {
                "event": deepcopy(existing),
                "idempotentReplay": True,
                "run": self._project_run(run_id, events),
            }

        next_sequence = self._next_sequence(events)
        requested_sequence = body.get("sequence")
        if requested_sequence is not None and int(requested_sequence) != next_sequence:
            raise InsuranceFraudEventSequenceError(
                f"Insurance replay event sequence for run '{run_id}' expected {next_sequence}, got {requested_sequence}"
            )
        event = self._make_event(
            run_id=run_id,
            sequence=next_sequence,
            event_type=event_type,
            actor=actor,
            payload=payload,
            evidence_refs=evidence_refs,
            rule_refs=rule_refs,
            receipt_refs=receipt_refs,
            idempotency_key=idempotency_key,
            occurred_at=body.get("occurredAt") or _utc_now(),
            previous_hash=events[-1]["eventHash"],
            content_hash=fingerprint,
        )
        event["preState"] = self._pre_state(run_id, events)
        events.append(event)
        self._idempotency[run_id][idempotency_key] = event
        self._save_state()
        return {
            "event": deepcopy(event),
            "idempotentReplay": False,
            "run": self._project_run(run_id, events),
        }

    def select_option(self, run_id: str, option_id: str, body: dict[str, Any]) -> dict[str, Any]:
        option = self._option(option_id)
        result = self.append_event(
            run_id,
            {
                "type": "option.selected",
                "idempotencyKey": body.get("idempotencyKey") or f"{run_id}:option.selected:{option_id}",
                "actor": body.get("actor") or _actor("human", "synthetic-claims-handler", option["requiredRole"]),
                "payload": {
                    "optionId": option_id,
                    "action": option["action"],
                    "selectedBy": body.get("actor")
                    or _actor("human", "synthetic-claims-handler", option["requiredRole"]),
                    "selectionReason": body.get("selectionReason") or option["rationale"],
                    "supportingEvidenceRefs": option["supportingEvidenceRefs"],
                    "opposingEvidenceRefs": option["opposingEvidenceRefs"],
                    "nextNodeId": "fraud-lead-approval" if option["requiresApproval"] else "receipt-dossier",
                    "requiresApproval": option["requiresApproval"],
                },
                "evidenceRefs": option["supportingEvidenceRefs"],
                "ruleRefs": [INSURANCE_RULE_NAME],
            },
        )
        if option["requiresApproval"]:
            approval_event = self.append_event(
                run_id,
                {
                    "type": "approval.requested",
                    "idempotencyKey": f"{body.get('idempotencyKey') or f'{run_id}:option.selected:{option_id}'}:"
                    "approval.requested",
                    "actor": _actor("system", "aegis-insurance-replay", "approval coordinator"),
                    "payload": {
                        "approvalId": FRAUD_APPROVAL_ID,
                        "requiredRole": "fraud lead",
                        "nodeId": "fraud-lead-approval",
                        "selectedOptionId": option_id,
                    },
                    "evidenceRefs": option["supportingEvidenceRefs"],
                    "ruleRefs": [INSURANCE_RULE_NAME],
                },
            )
            result["approvalEvent"] = approval_event["event"]
            result["run"] = approval_event["run"]
        return result

    def decide_approval(self, run_id: str, approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
        if approval_id != FRAUD_APPROVAL_ID:
            raise LookupError(f"Unknown approval '{approval_id}'")
        decision = str(body.get("decision") or "").strip().lower()
        if decision not in {"granted", "rejected"}:
            raise ValueError("decision must be granted or rejected")
        actor = body.get("actor") or _actor("human", "synthetic-fraud-lead", "fraud lead")
        if _normalized_role(actor) != "fraud lead":
            self.append_event(
                run_id,
                {
                    "type": "authorization.denied",
                    "idempotencyKey": body.get("idempotencyKey") or f"{run_id}:approval.denied:{approval_id}",
                    "actor": actor,
                    "payload": {
                        "approvalId": approval_id,
                        "attemptedDecision": decision,
                        "requiredRole": "fraud lead",
                        "reason": f"Role '{actor.get('role')}' is not authorized for insurance fraud approval",
                    },
                },
            )
            raise InsuranceFraudAuthorizationError(
                f"Role '{actor.get('role')}' is not authorized for insurance fraud approval"
            )
        return self.append_event(
            run_id,
            {
                "type": f"approval.{decision}",
                "idempotencyKey": body.get("idempotencyKey")
                or f"{run_id}:approval.{decision}:{approval_id}",
                "actor": actor,
                "payload": {
                    "approvalId": approval_id,
                    "decision": decision,
                    "rationale": body.get("rationale") or f"Fraud lead {decision} selected action.",
                    "nodeId": "fraud-lead-approval",
                },
                "evidenceRefs": ["ev-payment-instruction", "ev-repair-invoice", "ev-staff-assignment"],
                "ruleRefs": [INSURANCE_RULE_NAME],
            },
        )

    def transition(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        events = self._events_for(run_id)
        selected_option = self._selected_option_id(events)
        if not selected_option:
            self.append_event(
                run_id,
                {
                    "type": "transition.denied",
                    "idempotencyKey": f"{body.get('idempotencyKey') or f'{run_id}:transition'}:denied",
                    "actor": body.get("actor")
                    or _actor("system", "aegis-insurance-replay", "workflow runtime"),
                    "payload": {"deniedReason": "no insurance fraud option has been selected"},
                },
            )
            raise InsuranceFraudEventSequenceError(
                "Transition denied because no insurance fraud option has been selected"
            )

        option = self._option(selected_option)
        if option["requiresApproval"] and not (
            self._has_event(events, "approval.granted") or self._has_event(events, "approval.rejected")
        ):
            self.append_event(
                run_id,
                {
                    "type": "transition.denied",
                    "idempotencyKey": f"{body.get('idempotencyKey') or f'{run_id}:transition'}:approval-missing",
                    "actor": body.get("actor")
                    or _actor("system", "aegis-insurance-replay", "workflow runtime"),
                    "payload": {"deniedReason": "fraud lead approval decision is missing"},
                },
            )
            raise InsuranceFraudEventSequenceError(
                "Transition denied because fraud lead approval decision is missing"
            )

        base_key = str(body.get("idempotencyKey") or f"{run_id}:transition")
        actor = body.get("actor") or _actor("system", "aegis-insurance-replay", "workflow runtime")
        terminal_event = self._terminal_event_type(selected_option, events)
        self.append_event(
            run_id,
            {
                "type": terminal_event,
                "idempotencyKey": f"{base_key}:{terminal_event}",
                "actor": actor,
                "payload": {
                    "selectedOptionId": selected_option,
                    "action": option["action"],
                    "externalCallMade": False,
                    "result": self._terminal_result(selected_option, events),
                },
                "evidenceRefs": option["supportingEvidenceRefs"],
                "ruleRefs": [INSURANCE_RULE_NAME],
            },
        )
        receipt = self._receipt(self._events_for(run_id))
        self.append_event(
            run_id,
            {
                "type": "receipt.sealed",
                "idempotencyKey": f"{base_key}:receipt.sealed",
                "actor": _actor("system", "aegis-ledger", "signature authority"),
                "payload": {
                    "receiptType": "synthetic_insurance_fraud_replay_receipt",
                    "receiptId": receipt["receiptId"],
                    "receiptHash": receipt["receiptHash"],
                },
                "receiptRefs": [receipt["receiptId"]],
            },
        )
        return self.get_run(run_id)

    def get_receipt(self, run_id: str) -> dict[str, Any]:
        return {"receipt": self._receipt(self._events_for(run_id))}

    def get_dossier(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)["run"]
        case = self._case_for_run(run_id)
        return {
            "dossier": {
                "runId": run_id,
                "format": "synthetic-insurance-json",
                "scenario": "Flood-damaged warehouse claim fraud gate",
                "replayInput": self._replay_input_contract(case),
                "publicContext": deepcopy(case["context"]["publicContext"]),
                "run": run,
                "receipt": run["receipt"],
                "evidence": run["evidence"],
                "traceMetadata": {
                    "platformSessionId": "synthetic-rule-session-insurance-fraud",
                    "traceRef": f"synthetic://trace/{run_id}/insurance-fraud-gate",
                    "ruleHash": INSURANCE_RULE_HASH,
                    "publicContextHash": PUBLIC_CONTEXT_HASH,
                    "triggerPolicyHash": TRIGGER_POLICY_HASH,
                },
                "sanitization": {
                    "synthetic": True,
                    "containsCustomerData": False,
                    "containsPhi": False,
                    "containsSecrets": False,
                },
            }
        }

    def evaluate_gate(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        case = self._case_from_request(body)
        facts = {**case["facts"], **_dict_value(body.get("facts"))}
        outcome = _evaluate_fraud_outcome(facts)
        evidence = _evidence_for_case(case)
        return {
            "workflowId": INSURANCE_WORKFLOW_ID,
            "runId": str(body.get("runId") or case["runId"]),
            "product": AEGIS_PRODUCT,
            "store": "synthetic-demo",
            "ruleName": INSURANCE_RULE_NAME,
            "targetNodeName": _target_node_for_outcome(outcome),
            "validation": self._validate_rule(),
            "latestFileId": None,
            "ruleVersionHash": INSURANCE_RULE_HASH,
            "importTreeHash": PUBLIC_CONTEXT_HASH,
            "triggerPolicyHash": TRIGGER_POLICY_HASH,
            "validationStatus": "valid",
            "policyIntegrity": {
                "product": AEGIS_PRODUCT,
                "store": "synthetic-demo",
                "ruleName": INSURANCE_RULE_NAME,
                "latestFileId": None,
                "ruleVersionHash": INSURANCE_RULE_HASH,
                "importTreeHash": PUBLIC_CONTEXT_HASH,
                "validationStatus": "valid",
                "missingImports": [],
                "hasImportCycles": False,
            },
            "facts": facts,
            "ruleOutcomes": _rule_outcomes(facts),
            "decision": {
                "outcome": outcome,
                "selectedOptionId": _option_for_outcome(outcome),
                "action": self._option(_option_for_outcome(outcome))["action"],
                "reason": _reason_for_outcome(outcome),
            },
            "triggerPolicyAction": self._option(_option_for_outcome(outcome))["action"],
            "convergenceState": "GOAL_REACHED",
            "autonomyEligibility": {
                "eligible": outcome == "allow_payout",
                "reason": _reason_for_outcome(outcome),
            },
            "ruleConfidence": 1.0,
            "evidenceTrustScore": _evidence_trust_score(evidence),
            "publicContext": deepcopy(case["context"]["publicContext"]),
            "publicContextHash": PUBLIC_CONTEXT_HASH,
            "traceRef": f"synthetic://trace/{case['runId']}/insurance-fraud-gate",
        }

    def _seed_case(self, case: dict[str, Any]) -> None:
        run_id = case["runId"]
        events: list[dict[str, Any]] = []
        self._run_cases[run_id] = deepcopy(case)
        self._run_events[run_id] = events
        self._idempotency[run_id] = {}

        def add(event_type: str, actor: dict[str, str], payload: dict[str, Any], **extra: Any) -> None:
            previous_hash = events[-1]["eventHash"] if events else "sha256:aegis-insurance-genesis"
            idempotency_key = extra.get("idempotency_key") or f"{run_id}:{event_type}:seed:{len(events) + 1}"
            content_hash = stable_hash(
                {
                    "eventType": event_type,
                    "actor": actor,
                    "payload": payload,
                    "evidenceRefs": extra.get("evidence_refs", []),
                    "ruleRefs": extra.get("rule_refs", []),
                    "receiptRefs": extra.get("receipt_refs", []),
                }
            )
            event = self._make_event(
                run_id=run_id,
                sequence=len(events) + 1,
                event_type=event_type,
                actor=actor,
                payload=payload,
                evidence_refs=extra.get("evidence_refs", []),
                rule_refs=extra.get("rule_refs", []),
                receipt_refs=extra.get("receipt_refs", []),
                idempotency_key=idempotency_key,
                occurred_at=f"2026-03-07T08:{30 + len(events):02d}:00Z",
                previous_hash=previous_hash,
                content_hash=content_hash,
            )
            events.append(event)
            self._idempotency[run_id][idempotency_key] = event

        gate = self.evaluate_gate({"branchId": case["branchId"], "runId": run_id})
        add(
            "workflow.created",
            _actor("system", "aegis-fixture-loader", "workflow loader"),
            {"workflowId": INSURANCE_WORKFLOW_ID, "version": "1.0.0", "isSynthetic": True},
        )
        add(
            "replay.context.loaded",
            _actor("system", "aegis-fixture-loader", "replay loader"),
            self._replay_input_contract(case),
        )
        add(
            "run.started",
            _actor("system", "claims-automation.synthetic", "claims automation"),
            {
                "branchId": case["branchId"],
                "caseId": case["caseId"],
                "entity": case["context"]["claim"]["claimId"],
                "autonomyLevel": "supervised_autonomy",
            },
        )
        add(
            "claim.ingested",
            _actor("system", "claims-ingestion.synthetic", "claims automation"),
            {
                "claim": case["context"]["claim"],
                "customer": case["context"]["customer"],
                "policy": case["context"]["policy"],
                "payment": case["context"]["payment"],
                "staff": case["context"]["staff"],
            },
            evidence_refs=["ev-claim-form", "ev-policy", "ev-payment-instruction", "ev-staff-assignment"],
        )
        add(
            "context.cached_fallback.used",
            _actor("system", "public-context-cache", "context provider"),
            case["context"]["publicContext"],
            evidence_refs=["ev-public-flood-context"],
        )
        add(
            "rule.evaluation.completed",
            _actor("system", "inferra-rule-engine", "policy gate"),
            {
                "platformSessionId": "synthetic-rule-session-insurance-fraud",
                "ruleName": INSURANCE_RULE_NAME,
                "targetNodeName": gate["targetNodeName"],
                "goalRuleName": gate["targetNodeName"],
                "goalRuleValue": True,
                "goalRuleType": "BOOLEAN",
                "outcome": gate["decision"]["outcome"],
                "ruleOutcomes": gate["ruleOutcomes"],
                "facts": case["facts"],
                "traceRef": gate["traceRef"],
            },
            evidence_refs=["ev-claim-form", "ev-policy", "ev-payment-instruction", "ev-public-flood-context"],
            rule_refs=[INSURANCE_RULE_NAME],
        )
        add(
            "options.generated",
            _actor("system", "aegis-options-engine", "options engine"),
            {
                "optionIds": [option["id"] for option in INSURANCE_OPTIONS],
                "recommendedOptionId": case["expectedOptionId"],
                "triggerPolicyHash": TRIGGER_POLICY_HASH,
            },
            evidence_refs=["ev-claim-form", "ev-policy", "ev-public-flood-context"],
            rule_refs=[INSURANCE_RULE_NAME],
        )
        self._save_state()

    def _make_event(
        self,
        *,
        run_id: str,
        sequence: int,
        event_type: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
        evidence_refs: list[str],
        rule_refs: list[str],
        receipt_refs: list[str],
        idempotency_key: str,
        occurred_at: str,
        previous_hash: str,
        content_hash: str,
    ) -> dict[str, Any]:
        event = {
            "eventId": f"evt_insurance_fraud_{run_id.replace('-', '_')}_{sequence:04d}",
            "idempotencyKey": idempotency_key,
            "type": event_type,
            "runId": run_id,
            "definitionId": INSURANCE_WORKFLOW_ID,
            "sequence": sequence,
            "actor": deepcopy(actor),
            "occurredAt": occurred_at,
            "preState": {},
            "payload": deepcopy(payload),
            "evidenceRefs": deepcopy(evidence_refs),
            "ruleRefs": deepcopy(rule_refs),
            "receiptRefs": deepcopy(receipt_refs),
            "correlationId": f"insurance-fraud:{run_id}",
            "previousHash": previous_hash,
            "payloadHash": stable_hash(payload),
            "contentHash": content_hash,
        }
        event["eventHash"] = stable_hash(
            {
                "eventId": event["eventId"],
                "idempotencyKey": event["idempotencyKey"],
                "type": event["type"],
                "runId": event["runId"],
                "sequence": event["sequence"],
                "actor": event["actor"],
                "occurredAt": event["occurredAt"],
                "payloadHash": event["payloadHash"],
                "previousHash": event["previousHash"],
            }
        )
        return event

    def _project_run(self, run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        case = self._case_for_run(run_id, sync=False)
        gate = self.evaluate_gate({"branchId": case["branchId"], "runId": run_id})
        nodes = deepcopy(BASE_NODES)
        options = self._options_for_run(case, events)
        selected_option_id = self._selected_option_id(events)
        terminal_event = self._latest_terminal_event(events)
        status = "gate_evaluated"
        current_node_id = "intervention-options"
        blocked_reason = None
        recovery_actions = ["select governed intervention option"]
        allowed_actions = ["option.selected"]
        next_recommendation = f"Select {case['expectedOptionId']} for the deterministic replay branch."
        sla_state = "met"

        if selected_option_id:
            option = self._option(selected_option_id)
            status = "approval_required" if option["requiresApproval"] else "ready_to_transition"
            current_node_id = "fraud-lead-approval" if option["requiresApproval"] else "receipt-dossier"
            allowed_actions = ["approval.granted", "approval.rejected"] if option["requiresApproval"] else ["transition.allowed"]
            recovery_actions = ["fraud lead approval", "reject selected intervention"] if option["requiresApproval"] else []
            next_recommendation = (
                "Record fraud lead decision before terminal action."
                if option["requiresApproval"]
                else "Transition to terminal action and seal receipt."
            )
            self._set_node(nodes, "intervention-options", status="complete")
            if option["requiresApproval"]:
                self._set_node(nodes, "fraud-lead-approval", status="waiting", startedAt="08:35", slaState="met")

        if self._has_event(events, "approval.granted"):
            status = "approval_granted"
            allowed_actions = ["transition.allowed"]
            next_recommendation = "Fraud lead approved; transition can execute terminal action."
            self._set_node(nodes, "fraud-lead-approval", status="complete", elapsedMinutes=3)
        if self._has_event(events, "approval.rejected"):
            status = "approval_rejected"
            allowed_actions = ["transition.allowed"]
            blocked_reason = "Fraud lead rejected the selected intervention; terminal denial/rework action is required."
            recovery_actions = ["transition to rejection receipt", "request additional evidence"]
            next_recommendation = "Seal the rejection path for audit."
            self._set_node(nodes, "fraud-lead-approval", status="blocked", blockedReason=blocked_reason)

        if terminal_event:
            status = self._status_for_terminal_event(terminal_event["type"])
            current_node_id = "receipt-dossier"
            allowed_actions = ["receipt.sealed"]
            next_recommendation = "Terminal action recorded; seal the replay receipt."
            blocked_reason = None
            recovery_actions = ["seal replay receipt"]
            self._set_node(nodes, "fraud-lead-approval", status="complete")
            self._set_node(nodes, "receipt-dossier", status="active", startedAt="08:39", slaState="met")

        if self._has_event(events, "receipt.sealed"):
            status = "sealed"
            current_node_id = "receipt-dossier"
            allowed_actions = ["dossier.exported"]
            next_recommendation = "Insurance fraud replay receipt sealed; dossier export is available."
            recovery_actions = []
            self._set_node(nodes, "receipt-dossier", status="complete", elapsedMinutes=1, slaState="met")

        receipt = self._receipt(events)
        return {
            "id": run_id,
            "definitionId": INSURANCE_WORKFLOW_ID,
            "definitionVersion": "1.0.0",
            "title": "Flood-Damaged Warehouse Claim Fraud Gate",
            "scenarioDomain": "insurance",
            "domain": "insurance",
            "entity": case["context"]["claim"]["claimId"],
            "summary": "Synthetic warehouse flood claim replay through AEGIS fraud and intervention gates.",
            "isSynthetic": True,
            "status": status,
            "currentNodeId": current_node_id,
            "selectedOptionId": selected_option_id,
            "recommendedOptionId": case["expectedOptionId"],
            "startedAt": "08:30",
            "updatedAt": events[-1]["occurredAt"],
            "closedAt": events[-1]["occurredAt"] if status == "sealed" else None,
            "autonomyLevel": "supervised_autonomy",
            "generationMode": "replay",
            "confidence": int(gate["ruleConfidence"] * 100),
            "riskScore": _risk_score(gate["decision"]["outcome"]),
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
            "evidence": _evidence_for_case(case),
            "confidenceSignals": {
                "ruleConfidence": gate["ruleConfidence"],
                "evidenceTrustScore": gate["evidenceTrustScore"],
                "optionConfidence": self._option(case["expectedOptionId"])["confidence"] / 100,
                "autonomyEligibility": gate["autonomyEligibility"],
                "convergenceState": "GOAL_REACHED",
                "policyIntegrity": gate["policyIntegrity"],
                "authorityState": "fraud_lead_approved"
                if self._has_event(events, "approval.granted")
                else "fraud_lead_rejected"
                if self._has_event(events, "approval.rejected")
                else "approval_pending"
                if selected_option_id and self._option(selected_option_id)["requiresApproval"]
                else "approval_not_required",
                "residualRisk": _residual_risk(gate["decision"]["outcome"]),
            },
            "ruleGate": gate,
            "receipt": receipt,
            "replayInputHash": case["inputHash"],
            "publicContextHash": PUBLIC_CONTEXT_HASH,
        }

    def _receipt(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        run_id = events[0]["runId"]
        case = self._case_for_run(run_id, sync=False)
        selected_option_id = self._selected_option_id(events) or case["expectedOptionId"]
        approval_event = self._latest_event(events, {"approval.granted", "approval.rejected"})
        terminal_event = self._latest_terminal_event(events)
        event_hashes = [event["eventHash"] for event in events]
        evidence_refs = sorted({ref for event in events for ref in event.get("evidenceRefs", [])})
        policy_hashes = {
            "ruleVersionHash": INSURANCE_RULE_HASH,
            "publicContextHash": PUBLIC_CONTEXT_HASH,
            "triggerPolicyHash": TRIGGER_POLICY_HASH,
        }
        payload = {
            "runId": run_id,
            "ruleOutcome": case["expectedOutcome"],
            "selectedOption": selected_option_id,
            "approvalActor": approval_event.get("actor") if approval_event else None,
            "evidenceRefs": evidence_refs,
            "policyHashes": policy_hashes,
            "eventHashes": event_hashes,
        }
        sealed = self._has_event(events, "receipt.sealed")
        return {
            "receiptId": f"receipt-{run_id}",
            "receiptType": "synthetic_insurance_fraud_replay_receipt",
            "runId": run_id,
            "ruleOutcome": case["expectedOutcome"],
            "selectedOption": selected_option_id,
            "approvalActor": approval_event.get("actor") if approval_event else None,
            "approvalStatus": approval_event["type"].split(".")[-1] if approval_event else "not_required",
            "terminalAction": terminal_event["type"] if terminal_event else None,
            "evidenceRefs": evidence_refs,
            "policyHashes": policy_hashes,
            "eventHashes": event_hashes,
            "eventSequenceRange": [events[0]["sequence"], events[-1]["sequence"]],
            "previousReceiptHash": "sha256:synthetic-insurance-genesis",
            "receiptHash": stable_hash(payload),
            "signatureState": "sealed" if sealed else "pending",
            "timestamp": events[-1]["occurredAt"],
            "sanitization": {
                "synthetic": True,
                "containsCustomerData": False,
                "containsPhi": False,
                "containsSecrets": False,
            },
        }

    def _validate_rule(self) -> dict[str, Any]:
        return _validation_to_dict(self._validation_service.validate(INSURANCE_RULE_TEXT, INSURANCE_RULE_NAME))

    def _events_for(self, run_id: str) -> list[dict[str, Any]]:
        self._sync_from_state()
        if run_id not in self._run_events and run_id in CASE_BY_RUN_ID:
            self._seed_case(CASE_BY_RUN_ID[run_id])
        if run_id not in self._run_events:
            raise LookupError(f"Unknown AEGIS workflow run '{run_id}'")
        return self._run_events[run_id]

    def _case_for_run(self, run_id: str, *, sync: bool = True) -> dict[str, Any]:
        if sync:
            self._sync_from_state()
        if run_id not in self._run_cases and run_id in CASE_BY_RUN_ID:
            if sync:
                self._seed_case(CASE_BY_RUN_ID[run_id])
            else:
                self._run_cases[run_id] = deepcopy(CASE_BY_RUN_ID[run_id])
        if run_id not in self._run_cases:
            raise LookupError(f"Unknown insurance replay run '{run_id}'")
        return self._run_cases[run_id]

    def _case_from_request(self, body: dict[str, Any]) -> dict[str, Any]:
        branch_id = str(body.get("branchId") or body.get("branch") or "").strip()
        run_id = str(body.get("runId") or "").strip()
        if branch_id:
            if branch_id not in REPLAY_CASES:
                raise LookupError(f"Unknown insurance replay branch '{branch_id}'")
            return REPLAY_CASES[branch_id]
        if run_id and run_id in CASE_BY_RUN_ID:
            return CASE_BY_RUN_ID[run_id]
        return REPLAY_CASES["escalate_fraud_review"]

    def _compiled_policy_refs(self) -> list[dict[str, Any]]:
        return [
            {
                "ruleName": INSURANCE_RULE_NAME,
                "targetNodeName": target,
                "ruleVersion": INSURANCE_RULE_VERSION,
                "ruleHash": INSURANCE_RULE_HASH,
                "publicContextHash": PUBLIC_CONTEXT_HASH,
                "triggerPolicyHash": TRIGGER_POLICY_HASH,
            }
            for target in [
                "claim completeness gate satisfied",
                "coverage exclusion gate satisfied",
                "fraud signal escalation required",
                "intervention gate requires payout freeze",
            ]
        ]

    def _trigger_policy_map(self) -> dict[str, Any]:
        return {
            "policyId": "trigger-insurance-flood-fraud-actions",
            "policyHash": TRIGGER_POLICY_HASH,
            "mode": "human_approval_required_for_fraud_actions",
            "outcomeActions": {
                option["id"]: {
                    "action": option["action"],
                    "requiresApproval": option["requiresApproval"],
                    "requiredRole": option["requiredRole"],
                }
                for option in INSURANCE_OPTIONS
            },
        }

    def _replay_input_contract(self, case: dict[str, Any]) -> dict[str, Any]:
        return {
            "caseId": case["caseId"],
            "branchId": case["branchId"],
            "expectedOutcome": case["expectedOutcome"],
            "expectedOptionId": case["expectedOptionId"],
            "inputHash": case["inputHash"],
            "idempotencyKey": f"{case['runId']}:replay:seed",
            "claim": deepcopy(case["context"]["claim"]),
            "customer": deepcopy(case["context"]["customer"]),
            "policy": deepcopy(case["context"]["policy"]),
            "payment": deepcopy(case["context"]["payment"]),
            "staff": deepcopy(case["context"]["staff"]),
            "facts": deepcopy(case["facts"]),
            "publicContextHash": PUBLIC_CONTEXT_HASH,
        }

    def _pre_state(self, run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        run = self._project_run(run_id, events)
        return {"runStatus": run["status"], "nodeId": run["currentNodeId"]}

    @staticmethod
    def _next_sequence(events: list[dict[str, Any]]) -> int:
        return max(event["sequence"] for event in events) + 1

    @staticmethod
    def _has_event(events: list[dict[str, Any]], event_type: str) -> bool:
        return any(event["type"] == event_type for event in events)

    @staticmethod
    def _latest_event(events: list[dict[str, Any]], event_types: set[str]) -> dict[str, Any] | None:
        for event in reversed(events):
            if event["type"] in event_types:
                return event
        return None

    @staticmethod
    def _selected_option_id(events: list[dict[str, Any]]) -> str | None:
        event = InsuranceFraudReplayRuntime._latest_event(events, {"option.selected"})
        if not event:
            return None
        return str(event.get("payload", {}).get("optionId") or "")

    @staticmethod
    def _latest_terminal_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
        return InsuranceFraudReplayRuntime._latest_event(
            events,
            {
                "payout.allowed",
                "evidence.requested",
                "fraud.escalated",
                "payout.frozen",
                "claim.denied",
            },
        )

    @staticmethod
    def _event_cursor(events: list[dict[str, Any]]) -> dict[str, Any]:
        latest = events[-1]
        return {
            "latestSequence": latest["sequence"],
            "latestEventId": latest["eventId"],
            "latestHash": latest["eventHash"],
        }

    @staticmethod
    def _timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        labels = {
            "workflow.created": ("SIGNATURE", "Workflow created"),
            "replay.context.loaded": ("ASSERTED", "Replay context loaded"),
            "run.started": ("ASSERTED", "Run started"),
            "claim.ingested": ("ASSERTED", "Claim ingested"),
            "context.cached_fallback.used": ("SEMANTIC", "Cached public context used"),
            "rule.evaluation.completed": ("INFERRED", "Fraud gate evaluated"),
            "options.generated": ("INFERRED", "Options generated"),
            "option.selected": ("APPROVAL", "Option selected"),
            "approval.requested": ("APPROVAL", "Fraud lead approval requested"),
            "approval.granted": ("APPROVAL", "Fraud lead approved"),
            "approval.rejected": ("APPROVAL", "Fraud lead rejected"),
            "authorization.denied": ("APPROVAL", "Unauthorized approval rejected"),
            "payout.allowed": ("SIGNATURE", "Payout allowed"),
            "evidence.requested": ("SIGNATURE", "Evidence requested"),
            "fraud.escalated": ("SIGNATURE", "Fraud review escalated"),
            "payout.frozen": ("SIGNATURE", "Payout frozen"),
            "claim.denied": ("SIGNATURE", "Claim denied"),
            "receipt.sealed": ("SIGNATURE", "Receipt sealed"),
        }
        return [
            {
                "id": event["eventId"],
                "time": event["occurredAt"],
                "layer": labels.get(event["type"], ("ASSERTED", event["type"]))[0],
                "actor": event["actor"]["id"],
                "event": labels.get(event["type"], ("ASSERTED", event["type"]))[1],
                "detail": event["payload"].get("reason")
                or event["payload"].get("rationale")
                or event["type"].replace(".", " "),
                "sequence": event["sequence"],
                "eventType": event["type"],
                "evidenceRefs": event.get("evidenceRefs", []),
                "eventHash": event["eventHash"],
            }
            for event in events
        ]

    def _options_for_run(self, case: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected = self._selected_option_id(events)
        options = deepcopy(INSURANCE_OPTIONS)
        for option in options:
            if option["id"] == selected:
                option["status"] = "selected"
            elif option["id"] == case["expectedOptionId"]:
                option["status"] = "recommended"
            else:
                option["status"] = "available"
        return options

    @staticmethod
    def _option(option_id: str) -> dict[str, Any]:
        for option in INSURANCE_OPTIONS:
            if option["id"] == option_id:
                return deepcopy(option)
        raise LookupError(f"Unknown option '{option_id}'")

    @staticmethod
    def _set_node(nodes: list[dict[str, Any]], node_id: str, **updates: Any) -> None:
        for node in nodes:
            if node["id"] == node_id:
                node.update(updates)
                return

    @staticmethod
    def _terminal_event_type(selected_option_id: str, events: list[dict[str, Any]]) -> str:
        if selected_option_id == "allow_payout":
            return "payout.allowed"
        if selected_option_id == "request_evidence":
            return "evidence.requested"
        if selected_option_id == "escalate_fraud_review":
            return "claim.denied" if InsuranceFraudReplayRuntime._has_event(events, "approval.rejected") else "fraud.escalated"
        if selected_option_id == "freeze_payout":
            return "claim.denied" if InsuranceFraudReplayRuntime._has_event(events, "approval.rejected") else "payout.frozen"
        if selected_option_id == "deny_reject":
            return "claim.denied"
        raise LookupError(f"Unknown selected insurance option '{selected_option_id}'")

    @staticmethod
    def _terminal_result(selected_option_id: str, events: list[dict[str, Any]]) -> str:
        if InsuranceFraudReplayRuntime._has_event(events, "approval.rejected"):
            return "fraud_lead_rejected_selected_intervention"
        return {
            "allow_payout": "payout_allowed",
            "request_evidence": "evidence_requested",
            "escalate_fraud_review": "fraud_review_escalated",
            "freeze_payout": "payout_frozen",
            "deny_reject": "claim_denied",
        }[selected_option_id]

    @staticmethod
    def _status_for_terminal_event(event_type: str) -> str:
        return {
            "payout.allowed": "allowed",
            "evidence.requested": "evidence_required",
            "fraud.escalated": "fraud_review",
            "payout.frozen": "payout_frozen",
            "claim.denied": "denied",
        }[event_type]


def _rule_outcomes(facts: dict[str, Any]) -> dict[str, bool]:
    completeness = bool(facts["claim form complete"] and facts["evidence pack complete"])
    coverage = bool(
        facts["policy active on loss date"]
        and facts["flood damage covered"]
        and not facts["exclusion applies"]
        and facts["public flood context matches postcode"]
    )
    fraud = bool(
        facts["duplicate bank account detected"]
        or facts["repair invoice anomaly detected"]
        or facts["staff conflict detected"]
    )
    freeze = bool(facts["payment requested before inspection"] or float(facts["claim amount"]) > 25000)
    return {
        "claimCompletenessGateSatisfied": completeness,
        "coverageExclusionGateSatisfied": coverage,
        "fraudSignalEscalationRequired": fraud,
        "interventionGateRequiresPayoutFreeze": freeze,
        "claimPayoutMayBeAllowed": completeness and coverage and not fraud and not freeze,
        "claimPayoutMustBeDenied": not coverage,
        "claimEvidenceMustBeRequested": not completeness,
    }


def _evaluate_fraud_outcome(facts: dict[str, Any]) -> str:
    outcomes = _rule_outcomes(facts)
    if outcomes["claimPayoutMustBeDenied"]:
        return "deny_reject"
    if outcomes["claimEvidenceMustBeRequested"]:
        return "request_evidence"
    if outcomes["fraudSignalEscalationRequired"]:
        return "escalate_fraud_review"
    if outcomes["interventionGateRequiresPayoutFreeze"]:
        return "freeze_payout"
    return "allow_payout"


def _option_for_outcome(outcome: str) -> str:
    return outcome


def _target_node_for_outcome(outcome: str) -> str:
    return {
        "allow_payout": "claim payout may be allowed",
        "request_evidence": "claim evidence must be requested",
        "escalate_fraud_review": "fraud signal escalation required",
        "freeze_payout": "intervention gate requires payout freeze",
        "deny_reject": "claim payout must be denied",
    }[outcome]


def _reason_for_outcome(outcome: str) -> str:
    return {
        "allow_payout": "Completeness, coverage, fraud, and intervention gates are satisfied.",
        "request_evidence": "Required inspection or claim evidence is missing.",
        "escalate_fraud_review": "Fraud signal rules detected bank or invoice anomalies.",
        "freeze_payout": "Payment timing or amount requires a payout freeze pending fraud lead review.",
        "deny_reject": "Coverage or exclusion context blocks the claim.",
    }[outcome]


def _risk_score(outcome: str) -> int:
    return {
        "allow_payout": 18,
        "request_evidence": 41,
        "escalate_fraud_review": 82,
        "freeze_payout": 76,
        "deny_reject": 68,
    }[outcome]


def _residual_risk(outcome: str) -> list[str]:
    return {
        "allow_payout": ["Low residual fraud risk in synthetic branch."],
        "request_evidence": ["Evidence completeness remains unresolved."],
        "escalate_fraud_review": ["Duplicate payment and invoice anomaly signals require fraud lead review."],
        "freeze_payout": ["Payout movement is frozen until inspection/payment timing concerns clear."],
        "deny_reject": ["Coverage/exclusion contradiction must be retained in the dossier."],
    }[outcome]


def _evidence_trust_score(evidence: list[dict[str, Any]]) -> float:
    available = [item for item in evidence if item.get("contentHash")]
    return round(len(available) / len(evidence), 2) if evidence else 0.0


def _normalized_role(actor: dict[str, Any]) -> str:
    return str(actor.get("role") or "").strip().lower().replace("_", " ").replace("-", " ")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _dict_value(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}
