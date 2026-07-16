"""Persistent AEGIS Phase 3 ActionProposal runtime contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from src.ports.aegis_repository_ports import AegisEventLedgerPort
from src.domain.aegis.autonomy import (
    CERTIFIED_CONFIDENCE_THRESHOLD,
    evaluate_autonomy_enforcement,
    extract_requested_autonomy_level,
)
from src.domain.aegis.rule_store import stable_hash


class AegisRuntimeAuthorizationError(PermissionError):
    """Raised when an actor lacks authority for a runtime mutation."""


class AegisRuntimeStateError(ValueError):
    """Raised when an action is not allowed by the persisted runtime state."""


OUTCOME_TO_STATUS = {
    "allow": "allowed",
    "deny": "denied",
    "modify": "modified",
    "escalate": "escalated",
    "require_approval": "approval_required",
    "require_evidence": "evidence_required",
    "fallback": "fallback_ready",
}

STATUS_ALLOWED_ACTIONS = {
    "proposed": ["preflight.evaluate", "gate.evaluate"],
    "preflight_passed": ["gate.evaluate"],
    "allowed": ["receipt.seal", "passport.export", "dossier.export"],
    "denied": ["receipt.seal", "passport.export", "dossier.export"],
    "modified": ["option.select", "approval.grant", "approval.reject", "receipt.seal"],
    "escalated": [
        "approval.grant",
        "approval.reject",
        "evidence.request",
        "override.request",
        "fallback.trigger",
        "passport.export",
        "dossier.export",
    ],
    "approval_required": [
        "approval.grant",
        "approval.reject",
        "evidence.request",
        "override.request",
        "fallback.trigger",
        "passport.export",
        "dossier.export",
    ],
    "evidence_required": ["evidence.request", "fallback.trigger", "passport.export", "dossier.export"],
    "fallback_ready": ["fallback.trigger", "passport.export", "dossier.export"],
    "approval_granted": ["override.request", "receipt.seal", "passport.export", "dossier.export"],
    "approval_rejected": ["fallback.trigger", "receipt.seal", "passport.export", "dossier.export"],
    "override_requested": ["override.decide", "fallback.trigger", "passport.export", "dossier.export"],
    "override_granted": ["receipt.seal", "passport.export", "dossier.export"],
    "override_rejected": ["fallback.trigger", "receipt.seal", "passport.export", "dossier.export"],
    "fallback_triggered": ["receipt.seal", "passport.export", "dossier.export"],
    "sealed": ["passport.export", "dossier.export"],
    "receipt_failed": ["receipt.seal", "passport.export", "dossier.export"],
}

ACTION_ROLES = {
    "preflight.evaluate": {"ai planner", "policy gate", "workflow runtime", "aegis runtime"},
    "gate.evaluate": {"policy gate", "workflow runtime", "aegis runtime"},
    "option.select": {"operator", "override authority", "ai planner"},
    "approval.grant": {"override authority"},
    "approval.reject": {"override authority"},
    "evidence.request": {"operator", "override authority", "policy gate", "workflow runtime"},
    "override.request": {"operator", "ai planner", "workflow runtime"},
    "override.decide": {"override authority"},
    "fallback.trigger": {"operator", "override authority", "workflow runtime", "aegis runtime"},
    "receipt.seal": {"signature authority", "workflow runtime", "aegis runtime"},
}

DEFAULT_OPTION_SET = {
    "considered": [
        {
            "id": "allow",
            "label": "Allow supervised action",
            "status": "available",
            "requiresApproval": False,
        },
        {
            "id": "modify",
            "label": "Modify action before release",
            "status": "available",
            "requiresApproval": True,
        },
        {
            "id": "fallback",
            "label": "Use safe fallback",
            "status": "available",
            "requiresApproval": False,
        },
    ],
    "selectedOptionId": None,
    "rejectedOptionIds": [],
}

ROBOT_ACTION_FIREWALL_WORKFLOW_ID = "robot-action-firewall"
AUTHORITATIVE_FACT_CLASSES = {"asserted", "inferred"}


class AegisPhase3RuntimeService:
    """State-aware facade over the persistent AEGIS event ledger."""

    def __init__(self, repository: AegisEventLedgerPort):
        self._repository = repository

    def create_action_proposal(self, body: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(body.get("proposalId") or body.get("proposal_id") or f"aegis_proposal_{uuid4().hex}")
        run_id = str(body.get("runId") or body.get("run_id") or f"aegis_run_{uuid4().hex}")
        workflow_id = str(body.get("workflowId") or body.get("workflow_id") or "aegis-action-firewall")
        workflow_version_id = body.get("workflowVersionId") or body.get("workflow_version_id")
        actor = _actor(body.get("actor"), role="AI planner", actor_id="aegis-planner")
        action = _dict_value(body.get("action")) or {
            "kind": str(body.get("actionKind") or "robot.action"),
            "target": str(body.get("target") or "synthetic-target"),
        }
        facts = _dict_value(body.get("facts"))
        evidence_refs = _string_list(body.get("evidenceRefs") or body.get("evidence_refs"))
        evidence_hashes = _dict_value(body.get("evidenceHashes") or body.get("evidence_hashes"))
        policy_hashes = _dict_value(body.get("policyHashes") or body.get("policy_hashes")) or {
            "ruleVersionHash": stable_hash({"workflowId": workflow_id, "action": action}),
            "importTreeHash": stable_hash({"imports": evidence_refs}),
            "validationStatus": "synthetic_validated",
        }
        autonomy_policy = _dict_value(body.get("autonomyPolicy") or body.get("autonomy_policy"))
        if body.get("autonomyLevel") or body.get("autonomy_level"):
            autonomy_policy.setdefault("level", body.get("autonomyLevel") or body.get("autonomy_level"))
        if body.get("riskScore") is not None or body.get("risk_score") is not None:
            autonomy_policy.setdefault("riskScore", body.get("riskScore", body.get("risk_score")))
        if body.get("confidence") is not None:
            autonomy_policy.setdefault("confidence", body.get("confidence"))
        option_set = _dict_value(body.get("optionSet") or body.get("option_set")) or deepcopy(DEFAULT_OPTION_SET)
        gate_decision = _dict_value(body.get("gateDecision") or body.get("gate_decision"))
        proposal_payload = {
            "proposalId": proposal_id,
            "runId": run_id,
            "workflowId": workflow_id,
            "action": action,
            "facts": facts,
            "evidenceRefs": evidence_refs,
            "evidenceHashes": evidence_hashes,
            "policyHashes": policy_hashes,
            "autonomyPolicy": autonomy_policy,
            "optionSet": option_set,
            "gateDecision": gate_decision,
            "approval": _dict_value(body.get("approval")),
            "approverChain": body.get("approverChain") if isinstance(body.get("approverChain"), list) else [],
            "fallback": _dict_value(body.get("fallback")),
            "sla": _dict_value(body.get("sla")),
            "receipt": _dict_value(body.get("receipt")),
            "sanitization": {
                "synthetic": True,
                "containsCustomerData": False,
                "containsPhi": False,
                "containsSecrets": False,
            },
        }
        run = self._repository.create_workflow_run(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_version_id=str(workflow_version_id) if workflow_version_id else None,
            proposal_id=proposal_id,
            proposal_payload=proposal_payload,
            actor=actor,
            facts=facts,
            policy_hashes=policy_hashes,
            status="proposed",
        )
        event = self._repository.append_event(
            run_id=run_id,
            event_type="action.proposed",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:action.proposed"),
            actor=actor,
            payload={
                "proposalId": proposal_id,
                "runStatus": "proposed",
                "action": action,
                "evidenceRefs": evidence_refs,
                "policyHashes": policy_hashes,
            },
            evidence_refs=evidence_refs,
            policy_hashes=policy_hashes,
            option_set=option_set,
            pre_state={"runStatus": "new"},
        )
        state = self.get_action_run(run_id)
        return {
            "actionProposal": proposal_payload,
            "run": run | state["run"],
            "event": event["event"],
            "allowedActions": state["allowedActions"],
        }

    def get_action_run(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        proposal = self._repository.get_latest_action_proposal(run_id)
        events = self._repository.list_events(run_id)
        sla = _sla_contract(proposal, events)
        return {
            "run": {
                **run,
                "eventCursor": _event_cursor(events),
                "latestEventType": events[-1]["type"] if events else None,
                "slaState": sla.get("state"),
                "sla": sla,
                "autonomyPolicy": deepcopy(proposal.get("proposal", {}).get("autonomyPolicy") or {}),
            },
            "events": events,
            "allowedActions": _allowed_actions(run.get("status")),
        }

    def evaluate_preflight(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="policy gate", actor_id="aegis-preflight")
        self._require_action(run_id, "preflight.evaluate", actor, body)
        outcome = _outcome(body.get("outcome"), default="allow")
        status = "preflight_passed" if outcome == "allow" else OUTCOME_TO_STATUS[outcome]
        decision = _decision_payload(body, outcome, status)
        event = self._repository.append_event(
            run_id=run_id,
            event_type="preflight.evaluated",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:preflight:{outcome}"),
            actor=actor,
            payload={
                "runStatus": status,
                "preflightDecision": decision,
                "evidenceRefs": _string_list(body.get("evidenceRefs")),
            },
            evidence_refs=_string_list(body.get("evidenceRefs")),
            policy_hashes=_dict_value(body.get("policyHashes")),
            pre_state=self._pre_state(run_id),
        )
        return {"preflightDecision": decision, "event": event["event"], **self.get_action_run(run_id)}

    def evaluate_gate(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="policy gate", actor_id="aegis-gate")
        self._require_action(run_id, "gate.evaluate", actor, body)
        proposal = self._repository.get_latest_action_proposal(run_id)
        proposal_payload = _dict_value(proposal.get("proposal"))
        action = _dict_value(proposal_payload.get("action"))
        action.update(_dict_value(body.get("action")))
        autonomy_policy = _dict_value(proposal_payload.get("autonomyPolicy"))
        autonomy_policy.update(_dict_value(body.get("autonomyPolicy") or body.get("autonomy_policy")))
        outcome = _outcome(body.get("outcome"), default="require_approval")
        if outcome == "allow":
            authority_failures = self._authoritative_gate_failures(run_id, body)
            if authority_failures:
                failed_names = ", ".join(failure["factName"] for failure in authority_failures)
                raise ValueError(
                    "Authoritative gate allow requires provenance-backed facts; "
                    f"these facts are missing or advisory only: {failed_names}"
                )
        status = OUTCOME_TO_STATUS[outcome]
        decision = _decision_payload(body, outcome, status)
        decision["factAuthority"] = {
            "requiredFacts": _string_list(body.get("requiredFacts")),
            "checked": bool(_string_list(body.get("requiredFacts"))),
            "source": "aegis-evidence-fact-ledger",
        }
        requested_level = extract_requested_autonomy_level(
            body,
            autonomy_policy,
            action,
            default="supervised_autonomy",
        )
        enforcement = evaluate_autonomy_enforcement(
            actor=_dict_value(proposal.get("actor")) or _actor_for_enforcement(proposal_payload, body),
            action=action,
            autonomy_policy=autonomy_policy,
            gate_decision=decision,
            requested_level=requested_level,
            outcome=outcome,
        )
        if enforcement["effectiveOutcome"] != outcome:
            outcome = enforcement["effectiveOutcome"]
            status = OUTCOME_TO_STATUS[outcome]
            decision["outcome"] = outcome
            decision["status"] = status
            if enforcement["reasons"]:
                decision["reason"] = " ".join(enforcement["reasons"])
                decision["rationale"] = decision["reason"]
        decision["autonomyEnforcement"] = enforcement
        option_set = _option_set_for_outcome(outcome, body)
        event = self._repository.append_event(
            run_id=run_id,
            event_type="gate.evaluated",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:gate:{outcome}"),
            actor=actor,
            payload={
                "runStatus": status,
                "gateDecision": decision,
                "optionSet": option_set,
                "approval": _approval_requirement(outcome, body),
                "fallback": _fallback_requirement(outcome, body),
            },
            evidence_refs=_string_list(body.get("evidenceRefs")),
            policy_hashes=_dict_value(body.get("policyHashes")),
            option_set=option_set,
            approval_state=_approval_requirement(outcome, body),
            fallback_state=_fallback_requirement(outcome, body),
            pre_state=self._pre_state(run_id),
        )
        return {"gateDecision": decision, "event": event["event"], **self.get_action_run(run_id)}

    def select_option(self, run_id: str, option_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="operator", actor_id="aegis-operator")
        self._require_action(run_id, "option.select", actor, body)
        requires_approval = bool(body.get("requiresApproval", option_id in {"modify", "escalate"}))
        status = "approval_required" if requires_approval else "modified"
        option_set = {
            "selectedOptionId": option_id,
            "selectedRationale": body.get("rationale") or body.get("selectionRationale") or "Option selected.",
            "rejectedOptionIds": _string_list(body.get("rejectedOptionIds")),
            "requiresApproval": requires_approval,
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type="option.selected",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:option:{option_id}"),
            actor=actor,
            payload={
                "runStatus": status,
                "selectedOptionId": option_id,
                "selectionRationale": option_set["selectedRationale"],
                "rejectedOptionIds": option_set["rejectedOptionIds"],
            },
            evidence_refs=_string_list(body.get("evidenceRefs")),
            option_set=option_set,
            pre_state=self._pre_state(run_id),
        )
        return {"optionSet": option_set, "event": event["event"], **self.get_action_run(run_id)}

    def decide_approval(self, run_id: str, approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
        decision = str(body.get("decision") or "").strip().lower()
        if decision not in {"granted", "rejected"}:
            raise ValueError("decision must be granted or rejected")
        action = "approval.grant" if decision == "granted" else "approval.reject"
        actor = _actor(body.get("actor"), role="override authority", actor_id="aegis-approver")
        self._require_action(run_id, action, actor, body)
        status = "approval_granted" if decision == "granted" else "approval_rejected"
        approval = {
            "approvalId": approval_id,
            "status": decision,
            "rationale": body.get("rationale") or f"Approval {decision}.",
            "actor": actor,
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type=f"approval.{decision}",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:approval:{approval_id}:{decision}"),
            actor=actor,
            payload={"runStatus": status, "approval": approval},
            evidence_refs=_string_list(body.get("evidenceRefs")),
            approval_state=approval,
            pre_state=self._pre_state(run_id),
        )
        return {"approval": approval, "event": event["event"], **self.get_action_run(run_id)}

    def request_evidence(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="operator", actor_id="aegis-operator")
        self._require_action(run_id, "evidence.request", actor, body)
        request_id = str(body.get("requestId") or f"evidence_{uuid4().hex}")
        evidence_request = {
            "requestId": request_id,
            "status": "requested",
            "requiredEvidenceRefs": _string_list(body.get("requiredEvidenceRefs")),
            "reason": body.get("reason") or "Additional evidence is required before release.",
            "actor": actor,
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type="evidence.requested",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:evidence:{request_id}"),
            actor=actor,
            payload={"runStatus": "evidence_required", "evidenceRequest": evidence_request},
            evidence_refs=evidence_request["requiredEvidenceRefs"],
            pre_state=self._pre_state(run_id),
        )
        return {"evidenceRequest": evidence_request, "event": event["event"], **self.get_action_run(run_id)}

    def ingest_evidence_facts(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._require_run(run_id)
        actor = _actor(body.get("actor"), role="workflow runtime", actor_id="aegis-fact-extractor")
        extracted_facts, evidence_refs, evidence_hashes = _extract_fact_records(body)
        if not extracted_facts:
            raise ValueError("at least one evidence fact is required")
        rejected = [
            fact
            for fact in extracted_facts
            if fact["authorityClass"] in AUTHORITATIVE_FACT_CLASSES
            and not fact["canSatisfyAuthoritativeRules"]
        ]
        if rejected:
            names = ", ".join(fact["factName"] for fact in rejected)
            raise ValueError(f"Authoritative evidence facts require source refs and source hashes: {names}")

        fact_ledger = _fact_ledger_payload(extracted_facts)
        event = self._repository.append_event(
            run_id=run_id,
            event_type="evidence.facts.ingested",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:evidence-facts:{fact_ledger['factHash']}"),
            actor=actor,
            payload={
                "extractedFacts": extracted_facts,
                "factLedger": fact_ledger,
                "evidenceHashes": evidence_hashes,
                "authorityBoundary": (
                    "Only provenance-backed asserted or inferred facts may satisfy authoritative rules; "
                    "advisory and similar-case-derived facts remain non-authoritative."
                ),
            },
            evidence_refs=evidence_refs,
            pre_state=self._pre_state(run_id),
        )
        return {
            "runId": run_id,
            "factLedger": fact_ledger,
            "event": event["event"],
            **self.get_action_run(run_id),
        }

    def request_override(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="operator", actor_id="aegis-operator")
        self._require_action(run_id, "override.request", actor, body)
        override_id = str(body.get("overrideId") or f"override_{uuid4().hex}")
        override = {
            "overrideId": override_id,
            "status": "requested",
            "reason": body.get("reason") or "Override requested for supervised release.",
            "actor": actor,
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type="override.requested",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:override:{override_id}:requested"),
            actor=actor,
            payload={"runStatus": "override_requested", "approval": {"override": override}},
            approval_state={"override": override},
            pre_state=self._pre_state(run_id),
        )
        return {"override": override, "event": event["event"], **self.get_action_run(run_id)}

    def decide_override(self, run_id: str, override_id: str, body: dict[str, Any]) -> dict[str, Any]:
        decision = str(body.get("decision") or "").strip().lower()
        if decision not in {"granted", "rejected"}:
            raise ValueError("decision must be granted or rejected")
        actor = _actor(body.get("actor"), role="override authority", actor_id="aegis-override-authority")
        self._require_action(run_id, "override.decide", actor, body)
        status = "override_granted" if decision == "granted" else "override_rejected"
        override = {
            "overrideId": override_id,
            "status": decision,
            "rationale": body.get("rationale") or f"Override {decision}.",
            "actor": actor,
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type=f"override.{decision}",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:override:{override_id}:{decision}"),
            actor=actor,
            payload={"runStatus": status, "approval": {"override": override}},
            approval_state={"override": override},
            pre_state=self._pre_state(run_id),
        )
        return {"override": override, "event": event["event"], **self.get_action_run(run_id)}

    def trigger_fallback(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="workflow runtime", actor_id="aegis-runtime")
        self._require_action(run_id, "fallback.trigger", actor, body)
        fallback = {
            "state": "triggered",
            "fallbackId": str(body.get("fallbackId") or "safe_fallback"),
            "reason": body.get("reason") or "Safe fallback selected by runtime policy.",
            "actor": actor,
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type="fallback.triggered",
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:fallback:{fallback['fallbackId']}"),
            actor=actor,
            payload={"runStatus": "fallback_triggered", "fallback": fallback},
            fallback_state=fallback,
            pre_state=self._pre_state(run_id),
        )
        return {"fallback": fallback, "event": event["event"], **self.get_action_run(run_id)}

    def seal_receipt(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        actor = _actor(body.get("actor"), role="signature authority", actor_id="aegis-ledger")
        self._require_action(run_id, "receipt.seal", actor, body)
        failed = bool(body.get("simulateFailure") or body.get("failed"))
        status = "receipt_failed" if failed else "sealed"
        receipt = {
            "receiptId": str(body.get("receiptId") or f"receipt_{run_id}"),
            "signatureState": "failed" if failed else "sealed",
            "failureReason": body.get("failureReason") if failed else None,
            "actor": actor,
        }
        receipt["receiptHash"] = stable_hash({"runId": run_id, "receipt": receipt})
        event_type = "receipt.seal.failed" if failed else "receipt.sealed"
        event = self._repository.append_event(
            run_id=run_id,
            event_type=event_type,
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:{event_type}:{receipt['receiptId']}"),
            actor=actor,
            payload={"runStatus": status, "receipt": receipt, "receiptHash": receipt["receiptHash"]},
            receipt=receipt,
            pre_state=self._pre_state(run_id),
        )
        snapshot = self._repository.materialize_session_snapshot(run_id)
        return {"receipt": receipt, "snapshot": snapshot, "event": event["event"], **self.get_action_run(run_id)}

    def get_receipt(self, run_id: str) -> dict[str, Any]:
        snapshot = self._materialized_snapshot(run_id)
        return {
            "receipt": snapshot["snapshot"].get("receipt", {}),
            "snapshotId": snapshot["snapshotId"],
            "snapshotHash": snapshot["snapshotHash"],
        }

    def export_passport(self, run_id: str) -> dict[str, Any]:
        snapshot = self._materialized_snapshot(run_id)
        snapshot_payload = snapshot["snapshot"]
        passport = {
            "passportType": "aegis-decision-passport",
            "schemaVersion": "aegis-decision-passport-v1",
            "runId": run_id,
            "sourceSnapshotId": snapshot["snapshotId"],
            "sourceSnapshotHash": snapshot["snapshotHash"],
            "eventSequenceRange": snapshot["eventSequenceRange"],
            "proposal": deepcopy(snapshot_payload.get("proposal", {})),
            "policy": deepcopy(snapshot_payload.get("policy", {})),
            "gateDecision": deepcopy(snapshot_payload.get("gateDecision", {})),
            "options": deepcopy(snapshot_payload.get("options", {})),
            "approval": deepcopy(snapshot_payload.get("approval", {})),
            "fallback": deepcopy(snapshot_payload.get("fallback", {})),
            "receipt": deepcopy(snapshot_payload.get("receipt", {})),
            "sectionHashes": deepcopy(snapshot_payload.get("sectionHashes", {})),
            "validation": {
                "source": "SessionSnapshot",
                "snapshotHashMatches": snapshot_payload.get("snapshotHash") == snapshot["snapshotHash"],
                "sectionHashesMatch": _section_hashes_match(snapshot, snapshot_payload),
            },
        }
        passport["passportHash"] = stable_hash(passport)
        return {"passport": passport, "snapshot": snapshot}

    def get_dossier(self, run_id: str, export_format: str = "json") -> dict[str, Any]:
        snapshot = self._materialized_snapshot(run_id)
        dossier = {
            "dossierType": "aegis-action-firewall-baseline",
            "runId": run_id,
            "sourceSnapshotId": snapshot["snapshotId"],
            "sourceSnapshotHash": snapshot["snapshotHash"],
            "events": deepcopy(snapshot["snapshot"].get("events", [])),
            "receipt": deepcopy(snapshot["snapshot"].get("receipt", {})),
            "policy": deepcopy(snapshot["snapshot"].get("policy", {})),
            "sanitization": deepcopy(
                snapshot["snapshot"].get("proposal", {}).get(
                    "sanitization",
                    {
                        "synthetic": True,
                        "containsCustomerData": False,
                        "containsPhi": False,
                        "containsSecrets": False,
                    },
                )
            ),
        }
        dossier["exports"] = {
            "jsonLd": _dossier_json_ld(dossier, snapshot),
            "svg": _dossier_svg(dossier, snapshot),
        }
        export_format = _normalise_export_format(export_format)
        if export_format == "json":
            return {"dossier": dossier}
        if export_format == "json-ld":
            return {"dossier": dossier, "export": {"format": "json-ld", "document": dossier["exports"]["jsonLd"]}}
        if export_format == "svg":
            return {
                "dossier": dossier,
                "export": {
                    "format": "svg",
                    "mediaType": "image/svg+xml",
                    "document": dossier["exports"]["svg"],
                },
            }
        raise ValueError("format must be one of json, json-ld, svg")

    def evaluate_sla(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        run = self._require_run(run_id)
        proposal = self._repository.get_latest_action_proposal(run_id)
        events = self._repository.list_events(run_id)
        sla = _sla_contract(proposal, events)
        deadline = _parse_instant(
            body.get("deadline")
            or body.get("deadlineAt")
            or sla.get("deadline")
            or sla.get("deadlineAt")
        )
        if deadline is None:
            raise ValueError("SLA evaluation requires deadline or deadlineAt")
        warning_at = _parse_instant(body.get("warningAt") or sla.get("warningAt"))
        escalation_at = _parse_instant(body.get("escalationAt") or sla.get("escalationAt"))
        warning_minutes = int(body.get("warningMinutes") or sla.get("warningMinutes") or 2)
        escalation_minutes = int(body.get("escalationMinutes") or sla.get("escalationMinutes") or 5)
        warning_at = warning_at or deadline - timedelta(minutes=warning_minutes)
        escalation_at = escalation_at or deadline + timedelta(minutes=escalation_minutes)
        now = _parse_instant(body.get("now") or body.get("currentTime") or body.get("current_time"))
        now = now or datetime.now(timezone.utc)

        if now >= escalation_at:
            state = "escalated"
            event_type = "sla.escalated"
            run_status = "escalated"
            reason = body.get("reason") or "SLA escalation timer expired."
        elif now >= deadline:
            state = "breached"
            event_type = "sla.breached"
            run_status = "escalated"
            reason = body.get("reason") or "SLA breach timer expired."
        elif now >= warning_at:
            state = "warning"
            event_type = "sla.warning"
            run_status = run.get("status")
            reason = body.get("reason") or "SLA warning threshold reached."
        else:
            return {
                "sla": {
                    **sla,
                    "state": "met",
                    "now": _isoformat(now),
                    "deadline": _isoformat(deadline),
                    "warningAt": _isoformat(warning_at),
                    "escalationAt": _isoformat(escalation_at),
                },
                "event": None,
                **self.get_action_run(run_id),
            }

        actor = _actor(body.get("actor"), role="workflow runtime", actor_id="aegis-runtime")
        payload_sla = {
            **sla,
            "state": state,
            "reason": reason,
            "now": _isoformat(now),
            "deadline": _isoformat(deadline),
            "warningAt": _isoformat(warning_at),
            "escalationAt": _isoformat(escalation_at),
        }
        event = self._repository.append_event(
            run_id=run_id,
            event_type=event_type,
            idempotency_key=str(body.get("idempotencyKey") or f"{run_id}:{event_type}:{_isoformat(deadline)}"),
            actor=actor,
            payload={"runStatus": run_status, "sla": payload_sla},
            pre_state=self._pre_state(run_id),
        )
        return {"sla": payload_sla, "event": event["event"], **self.get_action_run(run_id)}

    def get_agent_risk_heatmap(self) -> dict[str, Any]:
        rows = []
        for run in self._repository.list_workflow_runs():
            try:
                proposal = self._repository.get_latest_action_proposal(run["runId"])
                events = self._repository.list_events(run["runId"])
            except LookupError:
                continue
            rows.append(_risk_heatmap_row(run, proposal, events))
        rows = sorted(rows, key=lambda row: (-row["riskScore"], row["agentId"], row["runId"]))
        return {
            "source": "aegis-event-ledger",
            "certifiedConfidenceThreshold": CERTIFIED_CONFIDENCE_THRESHOLD,
            "rows": rows,
            "summary": {
                "rowCount": len(rows),
                "highRiskCount": sum(1 for row in rows if row["riskBand"] == "high"),
                "breachCount": sum(1 for row in rows if row.get("slaState") in {"breached", "escalated"}),
            },
        }

    def replay_policy(self, policy_id: str, body: dict[str, Any]) -> dict[str, Any]:
        policy = _replay_policy(policy_id, body)
        snapshots = body.get("snapshots") if isinstance(body.get("snapshots"), list) else _default_replay_snapshots()
        groups: dict[str, list[dict[str, Any]]] = {
            "unchanged": [],
            "newlyAllowed": [],
            "newlyDenied": [],
            "newlyEscalated": [],
            "evidenceInsufficient": [],
        }
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            replay = _replay_snapshot(snapshot, policy)
            groups[_replay_group(snapshot.get("previousDecision"), replay["decision"])].append(replay)
        result = {
            "policyId": policy_id,
            "scenario": "robot-action-firewall-route-release",
            "source": "deterministic-policy-graph",
            "authoritative": True,
            "narrativeAuthoritative": False,
            "policy": policy,
            "groups": groups,
            "summary": {group: len(items) for group, items in groups.items()},
        }
        result["replayHash"] = stable_hash(result)
        return result

    def get_counterfactuals_for_proposal(self, proposal_id: str) -> dict[str, Any]:
        run_id = self._repository.get_run_id_for_proposal(proposal_id)
        if run_id is None:
            raise LookupError(f"AEGIS action proposal '{proposal_id}' was not found")
        result = self.get_counterfactuals(run_id)
        result["proposalId"] = proposal_id
        return result

    def get_counterfactuals(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        proposal = self._repository.get_latest_action_proposal(run_id)
        events = self._repository.list_events(run_id)
        gate_decision = _latest_payload_value(events, "gateDecision") or proposal.get("gateDecision", {})
        approval = _latest_payload_value(events, "approval") or proposal.get("approval", {})
        fallback = _latest_payload_value(events, "fallback") or proposal.get("fallback", {})
        fact_records = _fact_records(run, proposal, events)
        facts = {name: record.get("value") for name, record in fact_records.items()}
        evidence_refs = set(_string_list(proposal.get("evidenceRefs")))
        evidence_hashes = _dict_value(proposal.get("evidenceHashes"))
        event_evidence_refs = {
            ref
            for event in events
            for ref in _string_list(event.get("evidenceRefs"))
        }
        policy_hashes = _dict_value(run.get("policyHashes")) | _dict_value(proposal.get("policyHashes"))
        items: list[dict[str, Any]] = []

        for fact_name in _string_list(gate_decision.get("requiredFacts")):
            fact_record = fact_records.get(fact_name)
            fact_value = facts.get(fact_name)
            if fact_name not in facts or fact_value is None or fact_value == "":
                items.append(
                    _counterfactual_item(
                        "missing_fact",
                        fact_name,
                        "missing_fact",
                        f"Assert fact '{fact_name}' before the rule graph can pass.",
                        current_value=fact_value,
                        required_value="asserted non-empty fact",
                        provenance=["gateDecision.requiredFacts", "proposal.facts"],
                        satisfied_by_action="assert_fact",
                    )
                )
            elif not fact_record or not fact_record.get("canSatisfyAuthoritativeRules"):
                items.append(
                    _counterfactual_item(
                        "fact_provenance",
                        fact_name,
                        "non_authoritative_fact",
                        f"Provide provenance-backed asserted or inferred evidence for fact '{fact_name}'.",
                        current_value={
                            "value": fact_value,
                            "authorityClass": (fact_record or {}).get("authorityClass", "unknown"),
                            "advisoryOnly": (fact_record or {}).get("advisoryOnly", True),
                        },
                        required_value="asserted or inferred fact with source refs and hashes",
                        evidence_refs=(fact_record or {}).get("sourceRefs", []),
                        provenance=(fact_record or {}).get("sourceRefs", []) or ["factProvenance"],
                        satisfied_by_action="attach_provenance_backed_evidence",
                    )
                )

        for evidence_ref in _string_list(gate_decision.get("requiredEvidenceRefs")):
            if evidence_ref not in evidence_refs and evidence_ref not in event_evidence_refs:
                items.append(
                    _counterfactual_item(
                        "missing_evidence",
                        evidence_ref,
                        "missing_evidence",
                        f"Attach evidence '{evidence_ref}' before the rule graph can pass.",
                        current_value="missing",
                        required_value="present evidence ref",
                        evidence_refs=[evidence_ref],
                        provenance=["gateDecision.requiredEvidenceRefs", "event.evidenceRefs"],
                        satisfied_by_action="attach_evidence",
                    )
                )
            elif evidence_ref not in evidence_hashes:
                items.append(
                    _counterfactual_item(
                        "evidence_hash",
                        evidence_ref,
                        "missing_evidence_hash",
                        f"Hash evidence '{evidence_ref}' before the rule graph can pass.",
                        current_value="missing_hash",
                        required_value="sha256 evidence hash",
                        evidence_refs=[evidence_ref],
                        provenance=["proposal.evidenceHashes"],
                        satisfied_by_action="hash_evidence",
                    )
                )

        required_policy_versions = _dict_value(gate_decision.get("requiredPolicyVersions"))
        for key in sorted(required_policy_versions):
            required_value = required_policy_versions[key]
            if policy_hashes.get(key) != required_value:
                items.append(
                    _counterfactual_item(
                        "policy_version",
                        key,
                        "policy_version",
                        f"Use required policy version '{key}' before the rule graph can pass.",
                        current_value=policy_hashes.get(key),
                        required_value=required_value,
                        policy_refs=[key],
                        provenance=["gateDecision.requiredPolicyVersions", "run.policyHashes"],
                        satisfied_by_action="update_policy_version",
                    )
                )

        for threshold in _normalise_thresholds(gate_decision.get("thresholds")):
            if not _threshold_satisfied(threshold):
                threshold_id = str(threshold.get("id") or threshold.get("name") or "threshold")
                items.append(
                    _counterfactual_item(
                        "threshold",
                        threshold_id,
                        "threshold",
                        f"Meet threshold '{threshold_id}' before the rule graph can pass.",
                        current_value=threshold.get("currentValue"),
                        required_value=threshold.get("requiredValue"),
                        provenance=["gateDecision.thresholds"],
                        satisfied_by_action="adjust_threshold_input",
                    )
                )

        required_approvals = _string_list(gate_decision.get("requiredApprovals"))
        if run.get("status") in {"approval_required", "escalated", "override_requested"} and not required_approvals:
            required_approvals = [str(_dict_value(approval).get("requiredRole") or "override authority")]
        approval_status = str(_dict_value(approval).get("status") or "").lower()
        for role in required_approvals:
            if approval_status not in {"granted", "approved"}:
                items.append(
                    _counterfactual_item(
                        "approval",
                        role,
                        "approval",
                        f"Record approval from '{role}' before the rule graph can pass.",
                        current_value=approval_status or "missing",
                        required_value="granted",
                        provenance=["gateDecision.requiredApprovals", "approval.status"],
                        satisfied_by_action="grant_approval",
                    )
                )

        fallback_required = bool(gate_decision.get("fallbackRequired"))
        fallback_state = str(_dict_value(fallback).get("state") or "").lower()
        if fallback_required and fallback_state not in {"ready", "triggered", "available"}:
            items.append(
                _counterfactual_item(
                    "fallback_availability",
                    "fallback",
                    "fallback_availability",
                    "Provide an available fallback path before the rule graph can pass.",
                    current_value=fallback_state or "missing",
                    required_value="ready",
                    provenance=["gateDecision.fallbackRequired", "fallback.state"],
                    satisfied_by_action="provide_fallback",
                )
            )

        authority_required = gate_decision.get("authorityRequired")
        denied_authority_events = [event for event in events if event.get("type") == "authorization.denied"]
        if authority_required or denied_authority_events:
            attempted_roles = [
                str(event.get("actor", {}).get("role") or "unknown")
                for event in denied_authority_events
            ]
            items.append(
                _counterfactual_item(
                    "authority",
                    str(authority_required or "authorized_actor"),
                    "authority",
                    "Use an actor with the required authority before the rule graph can pass.",
                    current_value=attempted_roles or "missing",
                    required_value=authority_required or "authorized role",
                    provenance=["gateDecision.authorityRequired", "authorization.denied"],
                    satisfied_by_action="use_authorized_actor",
                )
            )

        items = sorted(items, key=lambda item: (item["category"], item["target"]))
        result = {
            "runId": run_id,
            "workflowId": run["workflowId"],
            "runStatus": run["status"],
            "source": "deterministic-rule-graph",
            "authoritative": True,
            "narrativeAuthoritative": False,
            "counterfactuals": items,
            "summary": {
                "blockingCount": len(items),
                "categories": sorted({item["category"] for item in items}),
                "canPassWithoutChanges": len(items) == 0,
            },
        }
        result["counterfactualHash"] = stable_hash(
            {
                "runId": result["runId"],
                "workflowId": result["workflowId"],
                "runStatus": result["runStatus"],
                "counterfactuals": result["counterfactuals"],
                "source": result["source"],
            }
        )
        return result

    def find_similar_cases(self, run_id: str, limit: int = 5) -> dict[str, Any]:
        target_run = self._require_run(run_id)
        if target_run["workflowId"] != ROBOT_ACTION_FIREWALL_WORKFLOW_ID:
            raise ValueError(
                "Options Ledger similar-case retrieval is currently scoped to robot-action-firewall runs"
            )
        target_snapshot = self._materialized_snapshot(run_id)["snapshot"]
        candidates = [
            candidate
            for candidate in self._repository.list_workflow_runs(ROBOT_ACTION_FIREWALL_WORKFLOW_ID)
            if candidate["runId"] != run_id
        ]
        results = [
            _similar_case_result(
                target_snapshot,
                self._materialized_snapshot(candidate["runId"])["snapshot"],
            )
            for candidate in candidates
        ]
        results = sorted(results, key=lambda item: (-item["score"], item["caseRunId"]))[: max(0, int(limit))]
        read_model = {
            "runId": run_id,
            "workflowId": target_run["workflowId"],
            "scope": {
                "workflowId": ROBOT_ACTION_FIREWALL_WORKFLOW_ID,
                "retrievalMode": "deterministic-options-ledger-read-model",
            },
            "authorityBoundary": {
                "advisoryOnly": True,
                "canSatisfyAuthoritativeRules": False,
                "reason": (
                    "Similar cases explain option memory and prior outcomes only; they never satisfy "
                    "authoritative evidence or rule facts."
                ),
            },
            "results": results,
        }
        read_model["readModelHash"] = stable_hash(read_model)
        return read_model

    def _require_run(self, run_id: str) -> dict[str, Any]:
        run = self._repository.get_workflow_run(run_id)
        if run is None:
            raise LookupError(f"AEGIS action run '{run_id}' was not found")
        return run

    def _pre_state(self, run_id: str) -> dict[str, Any]:
        state = self.get_action_run(run_id)
        return {
            "runStatus": state["run"]["status"],
            "allowedActions": state["allowedActions"],
            "latestEventType": state["run"]["latestEventType"],
        }

    def _require_action(self, run_id: str, action: str, actor: dict[str, Any], body: dict[str, Any]) -> None:
        state = self.get_action_run(run_id)
        allowed_actions = state["allowedActions"]
        if action not in allowed_actions:
            self._append_denial(
                run_id,
                action,
                actor,
                body,
                reason=f"Action '{action}' is not allowed while run status is '{state['run']['status']}'",
                event_type="runtime.action.denied",
            )
            raise AegisRuntimeStateError(
                f"Action '{action}' is not allowed while run status is '{state['run']['status']}'"
            )

        role = _normalized_role(actor)
        permitted_roles = ACTION_ROLES[action]
        if role not in permitted_roles:
            self._append_denial(
                run_id,
                action,
                actor,
                body,
                reason=f"Role '{actor.get('role')}' is not authorized for '{action}'",
                event_type="authorization.denied",
            )
            raise AegisRuntimeAuthorizationError(f"Role '{actor.get('role')}' is not authorized for '{action}'")

    def _append_denial(
        self,
        run_id: str,
        action: str,
        actor: dict[str, Any],
        body: dict[str, Any],
        *,
        reason: str,
        event_type: str,
    ) -> None:
        run = self._require_run(run_id)
        idempotency_key = str(
            body.get("idempotencyKey")
            or f"{run_id}:{event_type}:{stable_hash({'action': action, 'actor': actor, 'reason': reason})}"
        )
        self._repository.append_event(
            run_id=run_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "runStatus": run.get("status"),
                "attemptedAction": action,
                "reason": reason,
            },
            pre_state=self._pre_state(run_id),
        )

    def _materialized_snapshot(self, run_id: str) -> dict[str, Any]:
        latest = self._repository.get_latest_snapshot(run_id)
        state = self.get_action_run(run_id)
        latest_sequence = state["run"]["eventCursor"]["latestSequence"]
        if latest and latest["eventSequenceRange"][1] == latest_sequence:
            return latest
        return self._repository.materialize_session_snapshot(run_id)

    def _authoritative_gate_failures(self, run_id: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        required_facts = _string_list(body.get("requiredFacts"))
        if not required_facts:
            return []
        run = self._require_run(run_id)
        proposal = self._repository.get_latest_action_proposal(run_id)
        events = self._repository.list_events(run_id)
        fact_records = _fact_records(run, proposal, events)
        failures: list[dict[str, Any]] = []
        for fact_name in required_facts:
            fact = fact_records.get(fact_name)
            if not fact or fact.get("value") is None or fact.get("value") == "":
                failures.append({"factName": fact_name, "reason": "missing"})
            elif not fact.get("canSatisfyAuthoritativeRules"):
                failures.append(
                    {
                        "factName": fact_name,
                        "reason": "non_authoritative",
                        "authorityClass": fact.get("authorityClass"),
                    }
                )
        return failures


def _allowed_actions(status: str | None) -> list[str]:
    return deepcopy(STATUS_ALLOWED_ACTIONS.get(status or "", []))


def _actor(value: Any, *, role: str, actor_id: str) -> dict[str, Any]:
    if isinstance(value, dict):
        actor = deepcopy(value)
    else:
        actor = {}
    actor.setdefault("kind", "system" if role in {"policy gate", "workflow runtime", "signature authority"} else "human")
    actor.setdefault("id", actor_id)
    actor.setdefault("role", role)
    return actor


def _normalized_role(actor: dict[str, Any]) -> str:
    return str(actor.get("role") or "").strip().lower().replace("_", " ").replace("-", " ")


def _dict_value(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _float_value(*values: Any, default: float) -> float:
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _actor_for_enforcement(proposal_payload: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return _dict_value(body.get("requestingActor") or body.get("requesting_actor")) or _dict_value(
        proposal_payload.get("actor")
    ) or _dict_value(body.get("actor"))


def _normalise_export_format(value: Any) -> str:
    export_format = str(value or "json").strip().lower().replace("_", "-")
    aliases = {"jsonld": "json-ld", "ld-json": "json-ld", "image-svg": "svg"}
    return aliases.get(export_format, export_format)


def _dossier_json_ld(dossier: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": {
            "aegis": "https://inferra.ai/aegis#",
            "prov": "http://www.w3.org/ns/prov#",
            "runId": "aegis:runId",
            "sourceSnapshotHash": "aegis:sourceSnapshotHash",
            "eventHash": "aegis:eventHash",
        },
        "@type": "aegis:DecisionDossier",
        "@id": f"aegis:dossier:{dossier['runId']}",
        "runId": dossier["runId"],
        "sourceSnapshotHash": dossier["sourceSnapshotHash"],
        "sourceSnapshotId": dossier["sourceSnapshotId"],
        "policy": deepcopy(dossier.get("policy", {})),
        "receipt": deepcopy(dossier.get("receipt", {})),
        "events": [
            {
                "@type": "prov:Activity",
                "@id": f"aegis:event:{event.get('eventId')}",
                "sequence": event.get("sequence"),
                "eventType": event.get("type"),
                "eventHash": event.get("eventHash"),
                "evidenceRefs": deepcopy(event.get("evidenceRefs") or []),
            }
            for event in snapshot["snapshot"].get("events", [])
        ],
    }


def _dossier_svg(dossier: dict[str, Any], snapshot: dict[str, Any]) -> str:
    status = str(snapshot["snapshot"].get("run", {}).get("status") or "unknown")
    event_count = len(snapshot["snapshot"].get("events", []))
    snapshot_hash = dossier["sourceSnapshotHash"]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="260" viewBox="0 0 760 260" '
        'role="img" aria-label="AEGIS decision dossier">'
        '<rect width="760" height="260" fill="#f8fafc"/>'
        '<rect x="32" y="32" width="696" height="196" rx="8" fill="#ffffff" stroke="#0f172a"/>'
        '<text x="56" y="76" font-family="Arial, sans-serif" font-size="24" fill="#0f172a">'
        "AEGIS Decision Dossier</text>"
        f'<text x="56" y="116" font-family="Arial, sans-serif" font-size="16" fill="#334155">Run: {dossier["runId"]}</text>'
        f'<text x="56" y="148" font-family="Arial, sans-serif" font-size="16" fill="#334155">Status: {status}</text>'
        f'<text x="56" y="180" font-family="Arial, sans-serif" font-size="16" fill="#334155">Events: {event_count}</text>'
        f'<text x="56" y="212" font-family="Arial, sans-serif" font-size="12" fill="#475569">Snapshot: {snapshot_hash}</text>'
        "</svg>"
    )


def _sla_contract(proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sla = _dict_value(proposal.get("sla"))
    latest = _latest_payload_value(events, "sla")
    if latest:
        sla.update(latest)
    if "state" not in sla:
        if any(event.get("type") == "sla.escalated" for event in events):
            sla["state"] = "escalated"
        elif any(event.get("type") == "sla.breached" for event in events):
            sla["state"] = "breached"
        elif any(event.get("type") == "sla.warning" for event in events):
            sla["state"] = "warning"
        elif sla:
            sla["state"] = "met"
    return sla


def _parse_instant(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _risk_heatmap_row(run: dict[str, Any], proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    proposal_payload = _dict_value(proposal.get("proposal"))
    actor = _dict_value(proposal.get("actor")) or _dict_value(proposal_payload.get("actor"))
    action = _dict_value(proposal_payload.get("action"))
    autonomy_policy = _dict_value(proposal_payload.get("autonomyPolicy"))
    facts = _dict_value(proposal.get("facts"))
    gate_decision = _latest_payload_value(events, "gateDecision") or _dict_value(proposal.get("gateDecision"))
    confidence = _float_value(gate_decision.get("confidence"), autonomy_policy.get("confidence"), default=1.0)
    risk_score = _risk_score(
        explicit=autonomy_policy.get("riskScore") or action.get("riskScore"),
        facts=facts,
        status=run.get("status"),
        confidence=confidence,
    )
    sla = _sla_contract(proposal, events)
    latest_event = events[-1] if events else {}
    return {
        "agentId": str(actor.get("id") or "unknown-agent"),
        "agentRole": str(actor.get("role") or "unknown"),
        "runId": run["runId"],
        "workflowId": run["workflowId"],
        "status": run.get("status"),
        "requestedAutonomyLevel": extract_requested_autonomy_level(
            autonomy_policy,
            action,
            default="supervised_autonomy",
        ),
        "riskScore": risk_score,
        "riskBand": _risk_band(risk_score),
        "confidence": confidence,
        "slaState": sla.get("state"),
        "latestEventType": latest_event.get("type"),
        "latestEventHash": latest_event.get("eventHash"),
        "evidenceCompleteness": _evidence_completeness(proposal),
    }


def _risk_score(*, explicit: Any, facts: dict[str, Any], status: Any, confidence: float) -> int:
    try:
        return max(0, min(100, int(round(float(explicit)))))
    except (TypeError, ValueError):
        pass
    score = 25
    obstacle_confidence = facts.get("obstacleConfidence") or facts.get("obstacleClassificationConfidence")
    try:
        if float(obstacle_confidence) < CERTIFIED_CONFIDENCE_THRESHOLD:
            score += 25
    except (TypeError, ValueError):
        pass
    if confidence < CERTIFIED_CONFIDENCE_THRESHOLD:
        score += 15
    if status in {"denied", "escalated", "approval_required", "evidence_required", "receipt_failed"}:
        score += 20
    if status in {"sealed", "allowed"}:
        score -= 10
    return max(0, min(100, score))


def _risk_band(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _evidence_completeness(proposal: dict[str, Any]) -> dict[str, Any]:
    refs = _string_list(proposal.get("evidenceRefs"))
    hashes = _dict_value(proposal.get("evidenceHashes"))
    hashed_count = sum(1 for ref in refs if ref in hashes)
    return {
        "requiredRefs": len(refs),
        "hashedRefs": hashed_count,
        "complete": len(refs) == hashed_count,
    }


def _replay_policy(policy_id: str, body: dict[str, Any]) -> dict[str, Any]:
    if not policy_id:
        raise ValueError("policyId is required")
    return {
        "policyId": policy_id,
        "certifiedObstacleConfidenceThreshold": float(
            body.get("certifiedObstacleConfidenceThreshold")
            or body.get("certifiedThreshold")
            or CERTIFIED_CONFIDENCE_THRESHOLD
        ),
        "requiredDockEvidence": bool(body.get("requiredDockEvidence", True)),
        "activeDockExclusion": bool(body.get("activeDockExclusion", True)),
        "requireOverrideAuthority": bool(body.get("requireOverrideAuthority", True)),
    }


def _default_replay_snapshots() -> list[dict[str, Any]]:
    return [
        {
            "snapshotId": "route-release-unchanged-allow",
            "previousDecision": "allowed",
            "facts": {"obstacleClassificationConfidence": 0.93, "activeDock": False},
            "evidenceRefs": ["ev-dock-clearance"],
            "overrideAuthorityPresent": True,
        },
        {
            "snapshotId": "route-release-newly-allowed",
            "previousDecision": "denied",
            "facts": {"obstacleClassificationConfidence": 0.87, "activeDock": False},
            "evidenceRefs": ["ev-dock-clearance"],
            "overrideAuthorityPresent": True,
        },
        {
            "snapshotId": "route-release-newly-denied",
            "previousDecision": "allowed",
            "facts": {"obstacleClassificationConfidence": 0.82, "activeDock": False},
            "evidenceRefs": ["ev-dock-clearance"],
            "overrideAuthorityPresent": True,
        },
        {
            "snapshotId": "route-release-newly-escalated",
            "previousDecision": "allowed",
            "facts": {"obstacleClassificationConfidence": 0.91, "activeDock": False},
            "evidenceRefs": ["ev-dock-clearance"],
            "overrideAuthorityPresent": False,
        },
        {
            "snapshotId": "route-release-evidence-insufficient",
            "previousDecision": "allowed",
            "facts": {"obstacleClassificationConfidence": 0.91, "activeDock": False},
            "evidenceRefs": [],
            "overrideAuthorityPresent": True,
        },
    ]


def _replay_snapshot(snapshot: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    facts = _dict_value(snapshot.get("facts"))
    evidence_refs = set(_string_list(snapshot.get("evidenceRefs")))
    reasons = []
    decision = "allowed"
    confidence = _float_value(facts.get("obstacleClassificationConfidence"), default=0.0)
    if policy["requiredDockEvidence"] and "ev-dock-clearance" not in evidence_refs:
        decision = "evidence_insufficient"
        reasons.append("Required dock-clearance evidence is missing.")
    elif policy["activeDockExclusion"] and bool(facts.get("activeDock")):
        decision = "denied"
        reasons.append("Active dock exclusion blocks route release.")
    elif confidence < policy["certifiedObstacleConfidenceThreshold"]:
        decision = "denied"
        reasons.append("Obstacle confidence is below the certified route-release threshold.")
    elif policy["requireOverrideAuthority"] and not bool(snapshot.get("overrideAuthorityPresent")):
        decision = "escalated"
        reasons.append("Override authority is missing for this release context.")
    return {
        "snapshotId": str(snapshot.get("snapshotId") or snapshot.get("id") or "snapshot"),
        "previousDecision": str(snapshot.get("previousDecision") or "unknown"),
        "decision": decision,
        "reasons": reasons,
        "facts": facts,
        "evidenceRefs": sorted(evidence_refs),
        "counterfactuals": _replay_counterfactuals(decision, reasons),
    }


def _replay_group(previous_decision: Any, decision: str) -> str:
    previous = str(previous_decision or "").lower()
    if decision == "evidence_insufficient":
        return "evidenceInsufficient"
    if decision == "escalated":
        return "newlyEscalated" if previous != decision else "unchanged"
    if previous == decision:
        return "unchanged"
    if decision == "allowed":
        return "newlyAllowed"
    if decision == "denied":
        return "newlyDenied"
    return "unchanged"


def _replay_counterfactuals(decision: str, reasons: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "source": "deterministic-policy-graph",
            "decision": decision,
            "description": reason,
            "narrativeAuthoritative": False,
        }
        for reason in reasons
    ]


def _extract_fact_records(body: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    extraction_method = str(body.get("extractionMethod") or "deterministic-evidence-mapping")
    default_authority = _authority_class(body.get("authorityClass") or "asserted")
    records: list[dict[str, Any]] = []
    evidence_refs: list[str] = []
    evidence_hashes: dict[str, str] = {}

    for evidence in _normalise_evidence_items(body.get("evidence")):
        source_ref = str(evidence.get("id") or evidence.get("evidenceRef") or "").strip()
        source_hash = str(
            evidence.get("contentHash")
            or evidence.get("content_hash")
            or evidence.get("hash")
            or ""
        ).strip()
        if source_ref:
            evidence_refs.append(source_ref)
        if source_ref and source_hash:
            evidence_hashes[source_ref] = source_hash
        source = {
            "sourceRefs": [source_ref] if source_ref else [],
            "sourceHashes": [source_hash] if source_hash else [],
            "sourceLabel": evidence.get("sourceLabel"),
            "sourceUri": evidence.get("sourceUri"),
        }
        for fact in _normalise_fact_items(evidence.get("facts")):
            records.append(
                _fact_record_from_payload(
                    fact,
                    default_authority=default_authority,
                    default_extraction_method=extraction_method,
                    source=source,
                )
            )

    body_hashes = _dict_value(body.get("evidenceHashes"))
    for ref, content_hash in body_hashes.items():
        if ref and content_hash:
            evidence_hashes[str(ref)] = str(content_hash)

    for fact in _normalise_fact_items(body.get("facts")):
        source_refs = _unique_strings(fact.get("sourceRefs") or fact.get("evidenceRefs"))
        source_hashes = _unique_strings(fact.get("sourceHashes") or fact.get("evidenceHashes"))
        for ref in source_refs:
            if ref in evidence_hashes and evidence_hashes[ref] not in source_hashes:
                source_hashes.append(evidence_hashes[ref])
        records.append(
            _fact_record_from_payload(
                fact,
                default_authority=default_authority,
                default_extraction_method=extraction_method,
                source={
                    "sourceRefs": source_refs,
                    "sourceHashes": source_hashes,
                    "sourceLabel": fact.get("sourceLabel"),
                    "sourceUri": fact.get("sourceUri"),
                },
            )
        )
        evidence_refs.extend(source_refs)

    return records, _unique_strings(evidence_refs), evidence_hashes


def _normalise_evidence_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


def _normalise_fact_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [{"factName": str(key), "value": deepcopy(fact_value)} for key, fact_value in value.items()]
    if isinstance(value, list):
        items: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                items.append(deepcopy(item))
        return items
    return []


def _fact_record_from_payload(
    fact: dict[str, Any],
    *,
    default_authority: str,
    default_extraction_method: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    fact_name = str(fact.get("factName") or fact.get("name") or fact.get("key") or "").strip()
    if not fact_name:
        raise ValueError("evidence fact name is required")
    source_refs = _unique_strings(fact.get("sourceRefs") or fact.get("evidenceRefs") or source.get("sourceRefs"))
    source_hashes = _unique_strings(fact.get("sourceHashes") or fact.get("evidenceHashes") or source.get("sourceHashes"))
    authority_class = _authority_class(fact.get("authorityClass") or default_authority)
    extraction_method = str(fact.get("extractionMethod") or default_extraction_method)
    confidence = float(fact.get("confidence", 1.0))
    can_satisfy = (
        authority_class in AUTHORITATIVE_FACT_CLASSES
        and bool(source_refs)
        and bool(source_hashes)
        and bool(extraction_method)
    )
    record = {
        "factName": fact_name,
        "value": deepcopy(fact.get("value")),
        "valueType": str(fact.get("valueType") or _value_type(fact.get("value"))),
        "authorityClass": authority_class,
        "extractionMethod": extraction_method,
        "confidence": confidence,
        "sourceRefs": source_refs,
        "sourceHashes": source_hashes,
        "provenance": {
            "sourceLabel": fact.get("sourceLabel") or source.get("sourceLabel"),
            "sourceUri": fact.get("sourceUri") or source.get("sourceUri"),
            "sourceRefs": source_refs,
            "sourceHashes": source_hashes,
        },
        "canSatisfyAuthoritativeRules": can_satisfy,
        "advisoryOnly": not can_satisfy,
        "authorityReason": (
            "provenance-backed asserted or inferred fact"
            if can_satisfy
            else "advisory, learned, similar-case-derived, or missing source provenance"
        ),
    }
    record["factHash"] = stable_hash(record)
    return record


def _authority_class(value: Any) -> str:
    authority = str(value or "advisory").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "similar_case": "similar_case_advisory",
        "similar_case_derived": "similar_case_advisory",
        "retrieval": "retrieval_advisory",
        "retrieved": "retrieval_advisory",
        "learned_fact": "learned",
    }
    return aliases.get(authority, authority)


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"


def _fact_ledger_payload(extracted_facts: list[dict[str, Any]]) -> dict[str, Any]:
    authoritative = [
        fact["factName"]
        for fact in extracted_facts
        if fact.get("canSatisfyAuthoritativeRules")
    ]
    advisory = [
        fact["factName"]
        for fact in extracted_facts
        if not fact.get("canSatisfyAuthoritativeRules")
    ]
    payload = {
        "contract": "aegis-evidence-fact-ledger-v1",
        "extractedFacts": deepcopy(extracted_facts),
        "authoritativeFactNames": sorted(authoritative),
        "advisoryFactNames": sorted(advisory),
    }
    payload["factHash"] = stable_hash(payload)
    return payload


def _fact_records(
    run: dict[str, Any],
    proposal: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    proposal_refs = _string_list(proposal.get("evidenceRefs"))
    proposal_hashes = _dict_value(proposal.get("evidenceHashes"))
    proposal_source_hashes = [proposal_hashes[ref] for ref in proposal_refs if ref in proposal_hashes]
    for source in (_dict_value(run.get("facts")), _dict_value(proposal.get("facts"))):
        for fact_name, value in source.items():
            records[str(fact_name)] = _fact_record_from_payload(
                {
                    "factName": str(fact_name),
                    "value": value,
                    "authorityClass": "asserted",
                    "extractionMethod": "proposal_assertion",
                    "sourceRefs": proposal_refs,
                    "sourceHashes": proposal_source_hashes,
                    "sourceLabel": "proposal.facts",
                },
                default_authority="asserted",
                default_extraction_method="proposal_assertion",
                source={"sourceRefs": proposal_refs, "sourceHashes": proposal_source_hashes},
            )
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        for fact in payload.get("extractedFacts", []) if isinstance(payload.get("extractedFacts"), list) else []:
            if isinstance(fact, dict) and fact.get("factName"):
                records[str(fact["factName"])] = deepcopy(fact)
    return records


def _unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    unique: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def _outcome(value: Any, *, default: str) -> str:
    outcome = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "requireapproval": "require_approval",
        "requires_approval": "require_approval",
        "requireevidence": "require_evidence",
        "requires_evidence": "require_evidence",
    }
    outcome = aliases.get(outcome, outcome)
    if outcome not in OUTCOME_TO_STATUS:
        raise ValueError(
            "outcome must be one of allow, deny, modify, escalate, require_approval, require_evidence, fallback"
        )
    return outcome


def _decision_payload(body: dict[str, Any], outcome: str, status: str) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "status": status,
        "reason": body.get("reason") or _default_reason(outcome),
        "confidence": float(body.get("confidence", 1.0)),
        "calibration": body.get("calibration") or "deterministic_contract_fixture",
        "requiredEvidenceRefs": _string_list(body.get("requiredEvidenceRefs")),
        "requiredFacts": _string_list(body.get("requiredFacts")),
        "requiredApprovals": _string_list(body.get("requiredApprovals")),
        "requiredPolicyVersions": _dict_value(body.get("requiredPolicyVersions")),
        "thresholds": _normalise_thresholds(body.get("thresholds") or body.get("requiredThresholds")),
        "fallbackRequired": bool(body.get("fallbackRequired", outcome == "fallback")),
        "authorityRequired": body.get("authorityRequired"),
        "rationale": body.get("rationale") or _default_reason(outcome),
    }


def _default_reason(outcome: str) -> str:
    return {
        "allow": "All pre-flight and gate constraints are satisfied.",
        "deny": "A mandatory safety or policy constraint is false.",
        "modify": "The proposal can proceed only after a bounded modification.",
        "escalate": "The proposal needs human escalation before release.",
        "require_approval": "A human approval gate is required before release.",
        "require_evidence": "Additional evidence is required before release.",
        "fallback": "The safe fallback path must be selected.",
    }[outcome]


def _option_set_for_outcome(outcome: str, body: dict[str, Any]) -> dict[str, Any]:
    option_set = _dict_value(body.get("optionSet")) or deepcopy(DEFAULT_OPTION_SET)
    selected_by_outcome = {
        "allow": "allow",
        "deny": None,
        "modify": "modify",
        "escalate": "modify",
        "require_approval": "modify",
        "require_evidence": None,
        "fallback": "fallback",
    }
    option_set["selectedOptionId"] = body.get("selectedOptionId", selected_by_outcome[outcome])
    if outcome == "deny":
        option_set["rejectedOptionIds"] = [option["id"] for option in option_set.get("considered", [])]
    return option_set


def _approval_requirement(outcome: str, body: dict[str, Any]) -> dict[str, Any]:
    if outcome not in {"escalate", "require_approval", "modify"}:
        return _dict_value(body.get("approval"))
    approval_id = str(body.get("approvalId") or "approval-primary")
    return {
        "approvalId": approval_id,
        "status": "required",
        "requiredRole": "override authority",
        "reason": _default_reason(outcome),
    }


def _fallback_requirement(outcome: str, body: dict[str, Any]) -> dict[str, Any]:
    if outcome != "fallback":
        return _dict_value(body.get("fallback"))
    return {
        "state": "ready",
        "fallbackId": str(body.get("fallbackId") or "safe_fallback"),
        "reason": _default_reason(outcome),
    }


def _event_cursor(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {"latestSequence": 0, "latestEventId": None, "latestHash": None}
    latest = events[-1]
    return {
        "latestSequence": latest["sequence"],
        "latestEventId": latest["eventId"],
        "latestHash": latest["eventHash"],
    }


def _latest_payload_value(events: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for event in reversed(events):
        payload = event.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get(key), dict):
            return deepcopy(payload[key])
    return {}


def _normalise_thresholds(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


def _threshold_satisfied(threshold: dict[str, Any]) -> bool:
    current = threshold.get("currentValue")
    required = threshold.get("requiredValue")
    operator = str(threshold.get("operator") or ">=").strip()
    try:
        current_number = float(current)
        required_number = float(required)
    except (TypeError, ValueError):
        return current == required if operator in {"=", "==", "equals"} else False
    if operator == ">=":
        return current_number >= required_number
    if operator == ">":
        return current_number > required_number
    if operator == "<=":
        return current_number <= required_number
    if operator == "<":
        return current_number < required_number
    if operator in {"=", "==", "equals"}:
        return current_number == required_number
    return False


def _counterfactual_item(
    category: str,
    target: str,
    requirement_type: str,
    description: str,
    *,
    current_value: Any,
    required_value: Any,
    evidence_refs: list[str] | None = None,
    policy_refs: list[str] | None = None,
    provenance: list[str] | None = None,
    satisfied_by_action: str,
) -> dict[str, Any]:
    payload = {
        "category": category,
        "target": target,
        "requirementType": requirement_type,
        "description": description,
        "currentValue": current_value,
        "requiredValue": required_value,
        "evidenceRefs": evidence_refs or [],
        "policyRefs": policy_refs or [],
        "provenance": provenance or [],
        "blocking": True,
        "satisfiedByAction": satisfied_by_action,
    }
    payload["id"] = stable_hash(payload)
    return payload


def _similar_case_result(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    score_components = _similarity_components(target, candidate)
    score = round(sum(component["weight"] * component["value"] for component in score_components), 4)
    result = {
        "caseRunId": candidate["run"]["runId"],
        "workflowId": candidate["run"]["workflowId"],
        "caseStatus": candidate["run"].get("status"),
        "sourceSnapshotHash": candidate.get("snapshotHash"),
        "score": score,
        "scoreComponents": score_components,
        "explanation": [
            component["reason"]
            for component in score_components
            if component["value"] > 0
        ],
        "options": deepcopy(candidate.get("options", {})),
        "policy": {
            "ruleVersionHash": candidate.get("policy", {}).get("ruleVersionHash"),
            "importTreeHash": candidate.get("policy", {}).get("importTreeHash"),
        },
        "advisoryFacts": _similar_case_advisory_facts(candidate),
        "authorityBoundary": {
            "advisoryOnly": True,
            "canSatisfyAuthoritativeRules": False,
            "reason": "Prior case facts are retrieved memory and cannot satisfy current authoritative rules.",
        },
    }
    result["similarityHash"] = stable_hash(
        {
            "caseRunId": result["caseRunId"],
            "sourceSnapshotHash": result["sourceSnapshotHash"],
            "score": result["score"],
            "scoreComponents": result["scoreComponents"],
        }
    )
    return result


def _similarity_components(target: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    target_action = _dict_value(target.get("proposal", {}).get("action"))
    candidate_action = _dict_value(candidate.get("proposal", {}).get("action"))
    target_facts = _dict_value(target.get("facts"))
    candidate_facts = _dict_value(candidate.get("facts"))
    target_policy = _dict_value(target.get("policy"))
    candidate_policy = _dict_value(candidate.get("policy"))
    target_options = _dict_value(target.get("options"))
    candidate_options = _dict_value(candidate.get("options"))
    return [
        _score_component(
            "actionKind",
            0.20,
            1.0 if target_action.get("kind") == candidate_action.get("kind") else 0.0,
            f"Action kind match: {candidate_action.get('kind')}",
        ),
        _score_component(
            "targetAsset",
            0.15,
            1.0 if target_action.get("target") == candidate_action.get("target") else 0.0,
            f"Target asset match: {candidate_action.get('target')}",
        ),
        _score_component(
            "factOverlap",
            0.20,
            _fact_overlap(target_facts, candidate_facts),
            "Shared fact names and exact values overlap.",
        ),
        _score_component(
            "policyHash",
            0.15,
            _policy_overlap(target_policy, candidate_policy),
            "Rule version and import tree hashes overlap.",
        ),
        _score_component(
            "evidenceCompleteness",
            0.15,
            _evidence_completeness_similarity(target, candidate),
            "Evidence completeness is similar.",
        ),
        _score_component(
            "optionOutcome",
            0.15,
            _option_outcome_similarity(target_options, candidate_options),
            "Selected and rejected option outcomes are similar.",
        ),
    ]


def _score_component(name: str, weight: float, value: float, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "weight": weight,
        "value": round(max(0.0, min(1.0, float(value))), 4),
        "reason": reason,
    }


def _fact_overlap(target_facts: dict[str, Any], candidate_facts: dict[str, Any]) -> float:
    keys = set(target_facts) | set(candidate_facts)
    if not keys:
        return 0.0
    matches = sum(1 for key in keys if key in target_facts and target_facts.get(key) == candidate_facts.get(key))
    return matches / len(keys)


def _policy_overlap(target_policy: dict[str, Any], candidate_policy: dict[str, Any]) -> float:
    keys = ["ruleVersionHash", "importTreeHash", "policyVersionHash"]
    available = [key for key in keys if target_policy.get(key) or candidate_policy.get(key)]
    if not available:
        return 0.0
    matches = sum(1 for key in available if target_policy.get(key) == candidate_policy.get(key))
    return matches / len(available)


def _evidence_completeness_similarity(target: dict[str, Any], candidate: dict[str, Any]) -> float:
    target_completeness = _evidence_completeness_ratio(target)
    candidate_completeness = _evidence_completeness_ratio(candidate)
    return 1.0 - abs(target_completeness - candidate_completeness)


def _evidence_completeness_ratio(snapshot: dict[str, Any]) -> float:
    evidence = _dict_value(snapshot.get("evidence"))
    refs = _string_list(evidence.get("refs"))
    hashes = _dict_value(evidence.get("hashes"))
    if not refs:
        return 0.0
    return len([ref for ref in refs if hashes.get(ref)]) / len(refs)


def _option_outcome_similarity(target_options: dict[str, Any], candidate_options: dict[str, Any]) -> float:
    score = 0.0
    if target_options.get("selectedOptionId") and target_options.get("selectedOptionId") == candidate_options.get(
        "selectedOptionId"
    ):
        score += 0.6
    target_rejected = set(_string_list(target_options.get("rejectedOptionIds")))
    candidate_rejected = set(_string_list(candidate_options.get("rejectedOptionIds")))
    if target_rejected or candidate_rejected:
        score += 0.4 * (len(target_rejected & candidate_rejected) / len(target_rejected | candidate_rejected))
    elif not target_options.get("selectedOptionId") and not candidate_options.get("selectedOptionId"):
        score += 0.4
    return score


def _similar_case_advisory_facts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot_hash = str(snapshot.get("snapshotHash") or "")
    run_id = str(snapshot.get("run", {}).get("runId") or "")
    facts = _dict_value(snapshot.get("facts"))
    return [
        {
            "factName": fact_name,
            "value": deepcopy(value),
            "authorityClass": "similar_case_advisory",
            "extractionMethod": "options-ledger-similar-case",
            "confidence": 0.0,
            "sourceRefs": [run_id] if run_id else [],
            "sourceHashes": [snapshot_hash] if snapshot_hash else [],
            "provenance": {
                "source": "options-ledger-similar-case",
                "caseRunId": run_id,
                "sourceSnapshotHash": snapshot_hash,
            },
            "canSatisfyAuthoritativeRules": False,
            "advisoryOnly": True,
        }
        for fact_name, value in sorted(facts.items())
    ]


def _section_hashes_match(snapshot: dict[str, Any], snapshot_payload: dict[str, Any]) -> bool:
    section_hashes = snapshot_payload.get("sectionHashes") or {}
    expected = {
        "proposalHash": snapshot.get("proposalHash"),
        "evidenceHash": snapshot.get("evidenceHash"),
        "policyHash": snapshot.get("policyHash"),
        "optionSetHash": snapshot.get("optionSetHash"),
        "approvalHash": snapshot.get("approvalHash"),
        "fallbackHash": snapshot.get("fallbackHash"),
        "receiptHash": snapshot.get("receiptHash"),
    }
    return all(section_hashes.get(key) == value for key, value in expected.items() if value is not None)
