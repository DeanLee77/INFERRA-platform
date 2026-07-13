"""AEGIS autonomy level contracts and deterministic enforcement helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CERTIFIED_CONFIDENCE_THRESHOLD = 0.85

AUTONOMY_LEVELS = [
    {
        "level": "manual",
        "rank": 0,
        "label": "Manual",
        "description": "Human chooses and executes the action.",
        "autoApplyAllowed": False,
        "requiresHumanApproval": True,
    },
    {
        "level": "assisted",
        "rank": 1,
        "label": "Assisted",
        "description": "AI may recommend actions, but a human executes them.",
        "autoApplyAllowed": False,
        "requiresHumanApproval": True,
    },
    {
        "level": "supervised_autonomy",
        "rank": 2,
        "label": "Supervised Autonomy",
        "description": "Pre-approved low-risk transitions may execute under deterministic gates.",
        "autoApplyAllowed": True,
        "requiresHumanApproval": False,
    },
    {
        "level": "certified_autonomy",
        "rank": 3,
        "label": "Certified Autonomy",
        "description": "Certified templates may auto-apply only when all evidence, policy, fallback, and confidence gates pass.",
        "autoApplyAllowed": True,
        "requiresHumanApproval": False,
    },
]

_LEVEL_RANK = {entry["level"]: int(entry["rank"]) for entry in AUTONOMY_LEVELS}
_DEFAULT_ASSIGNMENTS = {
    "fleet-planner.alpha": {
        "agentId": "fleet-planner.alpha",
        "assignedLevel": "supervised_autonomy",
        "assignedBy": "ResearchInnovationLead",
        "rationale": "First governed agent default from INF-283.",
    },
    "fleet-planner.*": {
        "agentId": "fleet-planner.*",
        "assignedLevel": "supervised_autonomy",
        "assignedBy": "ResearchInnovationLead",
        "rationale": "Fleet planner proposals are governed before AMR actuation.",
    },
}
_ASSIGNMENTS = deepcopy(_DEFAULT_ASSIGNMENTS)


def list_autonomy_levels() -> dict[str, Any]:
    """Return the public autonomy scale and current agent assignments."""

    return {
        "scale": deepcopy(AUTONOMY_LEVELS),
        "certifiedConfidenceThreshold": CERTIFIED_CONFIDENCE_THRESHOLD,
        "approvalBoundary": {
            "manual": "Human executes or approves every action.",
            "assisted": "AI recommendations cannot execute without human approval.",
            "supervised_autonomy": (
                "Only pre-approved low-risk transitions execute; high-risk actions, actuation, "
                "material workflow changes, missing evidence, expired policy, failed receipt readiness, "
                "and override paths require human approval."
            ),
            "certified_autonomy": (
                "Auto-apply is limited to certified templates where deterministic gates, evidence hashes, "
                "policy hashes, fallback readiness, and confidence threshold all pass."
            ),
        },
        "assignments": sorted(deepcopy(list(_ASSIGNMENTS.values())), key=lambda item: item["agentId"]),
    }


def assign_autonomy_level(body: dict[str, Any]) -> dict[str, Any]:
    """Validate and record an in-process autonomy assignment for API/runtime use."""

    agent_id = str(body.get("agentId") or body.get("agent_id") or "").strip()
    level = normalise_autonomy_level(body.get("assignedLevel") or body.get("level"))
    if not agent_id:
        raise ValueError("agentId is required")
    assignment = {
        "agentId": agent_id,
        "assignedLevel": level,
        "assignedBy": str(body.get("assignedBy") or body.get("assigned_by") or "aegis-policy-admin"),
        "rationale": str(body.get("rationale") or "Autonomy assignment updated."),
        "constraints": deepcopy(body.get("constraints") if isinstance(body.get("constraints"), dict) else {}),
    }
    _ASSIGNMENTS[agent_id] = assignment
    return {"assignment": deepcopy(assignment), **list_autonomy_levels()}


def resolve_autonomy_assignment(actor: dict[str, Any], requested_level: str | None = None) -> dict[str, Any]:
    """Resolve an actor's assignment, including fleet-planner wildcard defaults."""

    explicit = actor.get("assignedAutonomyLevel") or actor.get("assigned_autonomy_level")
    actor_id = str(actor.get("id") or actor.get("agentId") or actor.get("agent_id") or "").strip()
    if explicit:
        level = normalise_autonomy_level(explicit)
        return {
            "agentId": actor_id or "inline-actor",
            "assignedLevel": level,
            "assignedBy": "inline-actor",
            "rationale": "Actor supplied an inline assigned autonomy level.",
        }
    if actor_id in _ASSIGNMENTS:
        return deepcopy(_ASSIGNMENTS[actor_id])
    for pattern, assignment in _ASSIGNMENTS.items():
        if pattern.endswith("*") and actor_id.startswith(pattern[:-1]):
            return deepcopy(assignment) | {"agentId": actor_id or pattern}
    default_level = requested_level if requested_level in _LEVEL_RANK else "supervised_autonomy"
    return {
        "agentId": actor_id or "unknown-agent",
        "assignedLevel": default_level,
        "assignedBy": "aegis-default",
        "rationale": "No explicit assignment matched; defaulting to the requested supervised envelope.",
    }


def normalise_autonomy_level(value: Any, *, default: str | None = None) -> str:
    level = str(value or default or "").strip().lower().replace("-", "_")
    if level not in _LEVEL_RANK:
        raise ValueError("autonomy level must be one of manual, assisted, supervised_autonomy, certified_autonomy")
    return level


def extract_requested_autonomy_level(*values: Any, default: str = "supervised_autonomy") -> str:
    for value in values:
        if not isinstance(value, dict):
            continue
        candidate = (
            value.get("requestedAutonomyLevel")
            or value.get("requested_autonomy_level")
            or value.get("autonomyLevel")
            or value.get("autonomy_level")
            or value.get("level")
        )
        if candidate:
            return normalise_autonomy_level(candidate)
    return default


def autonomy_rank(level: str) -> int:
    return _LEVEL_RANK[normalise_autonomy_level(level)]


def evaluate_autonomy_enforcement(
    *,
    actor: dict[str, Any],
    action: dict[str, Any],
    autonomy_policy: dict[str, Any],
    gate_decision: dict[str, Any],
    requested_level: str,
    outcome: str,
) -> dict[str, Any]:
    """Return deterministic enforcement metadata for a proposed gate outcome."""

    requested_level = normalise_autonomy_level(requested_level)
    assignment = resolve_autonomy_assignment(actor, requested_level)
    assigned_level = normalise_autonomy_level(assignment["assignedLevel"])
    confidence = _float_value(
        gate_decision.get("confidence"),
        autonomy_policy.get("confidence"),
        action.get("confidence"),
        default=1.0,
    )
    risk_score = _float_value(
        autonomy_policy.get("riskScore"),
        autonomy_policy.get("risk_score"),
        action.get("riskScore"),
        action.get("risk_score"),
        default=0.0,
    )
    certified_template = bool(autonomy_policy.get("certifiedTemplate") or action.get("certifiedTemplate"))
    fallback_ready = bool(autonomy_policy.get("fallbackReady", True))
    evidence_complete = bool(autonomy_policy.get("evidenceComplete", True))
    policy_valid = str(autonomy_policy.get("policyValidationStatus") or "valid").lower() in {
        "valid",
        "synthetic_validated",
    }
    receipt_ready = bool(autonomy_policy.get("receiptReady", True))
    material_change = bool(autonomy_policy.get("materialWorkflowChange") or action.get("materialWorkflowChange"))

    reasons: list[str] = []
    effective_outcome = outcome
    required_action = "allow"

    if autonomy_rank(requested_level) > autonomy_rank(assigned_level):
        reasons.append(
            f"Requested autonomy '{requested_level}' exceeds assigned level '{assigned_level}'."
        )
        effective_outcome = _approval_or_preserve_blocking_outcome(outcome)
        required_action = "approval_gate"

    if requested_level == "certified_autonomy":
        certified_failures = []
        if confidence < CERTIFIED_CONFIDENCE_THRESHOLD:
            certified_failures.append("confidence below certified threshold")
        if not certified_template:
            certified_failures.append("certified template missing")
        if not fallback_ready:
            certified_failures.append("fallback readiness missing")
        if not evidence_complete:
            certified_failures.append("evidence completeness missing")
        if not policy_valid:
            certified_failures.append("policy validation is not valid")
        if not receipt_ready:
            certified_failures.append("receipt readiness missing")
        if certified_failures:
            reasons.extend(certified_failures)
            effective_outcome = _approval_or_preserve_blocking_outcome(outcome)
            required_action = "approval_gate"

    if requested_level == "supervised_autonomy" and outcome == "allow":
        if risk_score >= 70 or material_change:
            reasons.append("Supervised autonomy high-risk or material-change action requires approval.")
            effective_outcome = "require_approval"
            required_action = "approval_gate"

    return {
        "requestedLevel": requested_level,
        "assignedLevel": assigned_level,
        "assignment": assignment,
        "confidence": confidence,
        "certifiedConfidenceThreshold": CERTIFIED_CONFIDENCE_THRESHOLD,
        "riskScore": risk_score,
        "certifiedTemplate": certified_template,
        "fallbackReady": fallback_ready,
        "evidenceComplete": evidence_complete,
        "policyValid": policy_valid,
        "receiptReady": receipt_ready,
        "originalOutcome": outcome,
        "effectiveOutcome": effective_outcome,
        "requiresApproval": effective_outcome == "require_approval" or required_action == "approval_gate",
        "requiredAction": required_action,
        "reasons": reasons,
        "allowedWithoutApproval": not reasons and outcome == "allow",
    }


def _approval_or_preserve_blocking_outcome(outcome: str) -> str:
    if outcome in {"deny", "fallback", "require_evidence"}:
        return outcome
    return "require_approval"


def _float_value(*values: Any, default: float) -> float:
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default
