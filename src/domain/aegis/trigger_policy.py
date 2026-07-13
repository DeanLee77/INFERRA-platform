from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any
from uuid import uuid4

from src.adapters.outbound.persistence.aegis_trigger_policy_repository import (
    AegisTriggerIdempotencyConflictError,
    AegisTriggerPolicyRepository,
)
from src.domain.aegis.phase3_runtime import AegisPhase3RuntimeService
from src.domain.aegis.rule_store import stable_hash
from src.domain.fact_values import FactValue
from src.domain.inference.session import InferenceSession
from src.domain.inference.session_service import InferenceSessionService
from src.domain.state import FactSource
from src.domain.state.feature_flags import get_feature_flags
from src.services.rule_service import RuleService


class AegisTriggerAuthorizationError(PermissionError):
    """Raised when an actor cannot perform a trigger operation."""


class AegisTriggerConflictError(ValueError):
    """Raised when a policy conflicts with an active policy or graph invariant."""


class AegisTriggerValidationError(ValueError):
    """Raised when a trigger policy or request is invalid."""


TRIGGER_MODES = {"recommend_only", "human_approval_required", "automatic"}
TARGET_TYPES = {"rule_set", "action"}
SOURCE_TYPES = {"rule_set", "direct"}
OUTCOME_TRIGGER_ROLES = {"aegis runtime", "policy gate", "workflow runtime"}
DIRECT_TRIGGER_ROLES = {"aegis runtime", "operator", "policy gate", "workflow runtime"}
DEFAULT_FACT_SOURCE_FILTER = ("ASSERTED", "INFERRED")


class AegisTriggerPolicyService:
    """Governed runtime for direct and outcome-triggered downstream execution."""

    def __init__(
        self,
        repository: AegisTriggerPolicyRepository,
        rule_service: RuleService,
        session_service: InferenceSessionService,
        phase3_service: AegisPhase3RuntimeService,
        llm_configuration_provider: Callable[[], dict[str, Any]] | None = None,
    ):
        self._repository = repository
        self._rule_service = rule_service
        self._session_service = session_service
        self._phase3_service = phase3_service
        self._llm_configuration_provider = llm_configuration_provider

    def create_policy(self, body: dict[str, Any], *, owner_id: str | None = None) -> dict[str, Any]:
        policy_id = str(body.get("policyId") or body.get("policy_id") or f"aegis_trigger_policy_{uuid4().hex}")
        version = str(body.get("version") or body.get("policyVersion") or "v1")
        mode = _normalise_mode(body.get("mode"))
        status = str(body.get("status") or "active").strip().lower()
        if status not in {"active", "inactive"}:
            raise AegisTriggerValidationError("status must be active or inactive")

        source = _normalise_source(body)
        target = _normalise_target(body)
        constraints = _normalise_constraints(body)
        source_key = _source_key(source)
        target_key = _target_key(target)

        self._validate_rule_targets(source, target)
        conflict = self._repository.find_active_conflict(
            source_key=source_key,
            target_key=target_key,
            exclude_policy_id=policy_id,
        )
        if conflict and status == "active":
            raise AegisTriggerConflictError(
                "An active trigger policy already governs this source and target"
            )
        if status == "active":
            self._validate_no_rule_set_cycle(source, target, policy_id)

        payload = {
            "when": deepcopy(body.get("when") if isinstance(body.get("when"), dict) else {}),
            "description": str(body.get("description") or ""),
            "createdBy": owner_id or body.get("createdBy"),
        }
        policy_hash = stable_hash(
            {
                "policyId": policy_id,
                "version": version,
                "mode": mode,
                "source": source,
                "target": target,
                "constraints": constraints,
                "payload": payload,
            }
        )
        policy = self._repository.upsert_policy(
            policy_id=policy_id,
            version=version,
            mode=mode,
            source_key=source_key,
            target_key=target_key,
            source=source,
            target=target,
            constraints=constraints,
            payload=payload,
            policy_hash=policy_hash,
            status=status,
            created_by=owner_id,
        )
        return {"policy": policy}

    def list_policies(self, *, status: str | None = None) -> dict[str, Any]:
        return {"policies": self._repository.list_policies(status=status)}

    def trigger_from_outcome(self, body: dict[str, Any], *, owner_id: str | None = None) -> dict[str, Any]:
        policy = self._require_policy(body)
        actor = _actor(body.get("actor"), role="workflow runtime", actor_id="aegis-trigger-runtime")
        _require_actor(actor, OUTCOME_TRIGGER_ROLES, "outcome trigger")
        source_result = _dict_value(body.get("sourceResult") or body.get("source_result"))
        if not source_result:
            raise AegisTriggerValidationError("sourceResult is required")
        if not _source_result_matches_policy(policy, source_result):
            raise AegisTriggerValidationError("sourceResult does not match trigger policy source")
        return self._evaluate_trigger(
            policy=policy,
            body=body,
            actor=actor,
            event_type="trigger.outcome.completed",
            source_event=source_result,
            owner_id=owner_id,
        )

    def trigger_direct(self, body: dict[str, Any], *, owner_id: str | None = None) -> dict[str, Any]:
        policy = self._require_policy(body)
        actor = _actor(body.get("actor"), role="operator", actor_id=owner_id or "aegis-trigger-requester")
        _require_actor(actor, DIRECT_TRIGGER_ROLES, "direct trigger")
        if policy["source"].get("type") != "direct":
            raise AegisTriggerValidationError("direct trigger requests require a direct-source policy")
        return self._evaluate_trigger(
            policy=policy,
            body=body,
            actor=actor,
            event_type="trigger.direct.requested",
            source_event=_dict_value(body.get("event")) or {"type": "direct_request"},
            owner_id=owner_id,
        )

    def _require_policy(self, body: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(body.get("policyId") or body.get("policy_id") or "").strip()
        if not policy_id:
            raise AegisTriggerValidationError("policyId is required")
        policy = self._repository.get_policy(policy_id)
        if policy is None:
            raise LookupError(f"Trigger policy '{policy_id}' was not found")
        if policy.get("status") != "active":
            raise AegisTriggerValidationError(f"Trigger policy '{policy_id}' is not active")
        return policy

    def _validate_rule_targets(self, source: dict[str, Any], target: dict[str, Any]) -> None:
        if source["type"] == "rule_set":
            self._rule_service.get_rule_by_name(str(source["ruleName"]))
        if target["type"] != "rule_set":
            return
        rule_name = str(target["ruleName"])
        target_node = str(target.get("targetNodeName") or "").strip()
        parser = self._rule_service.build_rule_set_parser(rule_name)
        if not target_node:
            raise AegisTriggerValidationError("rule-set trigger targets require targetNodeName")
        if target_node not in parser.get_node_set().get_node_dictionary():
            raise LookupError(f"Target node '{target_node}' does not exist in rule '{rule_name}'")

    def _validate_no_rule_set_cycle(
        self,
        source: dict[str, Any],
        target: dict[str, Any],
        policy_id: str,
    ) -> None:
        if source["type"] != "rule_set" or target["type"] != "rule_set":
            return
        edges = [
            (_rule_set_cycle_key(policy["source"]), _rule_set_cycle_key(policy["target"]))
            for policy in self._repository.list_policies(status="active")
            if policy["policyId"] != policy_id
            and policy["source"].get("type") == "rule_set"
            and policy["target"].get("type") == "rule_set"
        ]
        new_edge = (_rule_set_cycle_key(source), _rule_set_cycle_key(target))
        edges.append(new_edge)
        if _has_path(edges, new_edge[1], new_edge[0]):
            raise AegisTriggerConflictError("Trigger policy would create a rule-set trigger cycle")

    def _evaluate_trigger(
        self,
        *,
        policy: dict[str, Any],
        body: dict[str, Any],
        actor: dict[str, Any],
        event_type: str,
        source_event: dict[str, Any],
        owner_id: str | None,
    ) -> dict[str, Any]:
        idempotency_key = str(body.get("idempotencyKey") or body.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise AegisTriggerValidationError("idempotencyKey is required")
        facts_passed = _filter_facts(
            _dict_value(body.get("facts")) or _dict_value(source_event.get("facts")),
            _fact_source_filter(policy["constraints"]),
        )
        fingerprint = stable_hash(
            {
                "policyId": policy["policyId"],
                "policyHash": policy["policyHash"],
                "eventType": event_type,
                "sourceEvent": source_event,
                "actor": actor,
                "factsPassed": facts_passed,
                "correlationId": body.get("correlationId"),
            }
        )
        existing = self._repository.get_receipt_by_idempotency(
            policy_id=policy["policyId"],
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            stored_fingerprint = (existing.get("payload") or {}).get("fingerprint")
            if stored_fingerprint != fingerprint:
                raise AegisTriggerIdempotencyConflictError(
                    f"Trigger idempotency key '{idempotency_key}' was reused with different content"
                )
            return {"policy": policy, "triggerReceipt": existing, "idempotentReplay": True}

        skipped = self._guardrail_decision(policy, body, source_event)
        if skipped is not None:
            return self._record_receipt(
                policy=policy,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                facts_passed=facts_passed,
                source_event=source_event,
                decision="blocked",
                status="skipped",
                approval_state={},
                execution={"status": "not_started"},
                guardrail=skipped,
                correlation_id=_optional_str(body.get("correlationId")),
                fingerprint=fingerprint,
            )

        if not _outcome_condition_matches(policy, source_event):
            return self._record_receipt(
                policy=policy,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                facts_passed=facts_passed,
                source_event=source_event,
                decision="not_applicable",
                status="skipped",
                approval_state={},
                execution={"status": "not_started"},
                guardrail={"state": "passed", "reason": "outcome_condition_not_matched"},
                correlation_id=_optional_str(body.get("correlationId")),
                fingerprint=fingerprint,
            )

        mode = policy["mode"]
        if mode == "recommend_only":
            return self._record_receipt(
                policy=policy,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                facts_passed=facts_passed,
                source_event=source_event,
                decision="recommended",
                status="recommendation_recorded",
                approval_state={},
                execution={"status": "not_started"},
                guardrail={"state": "passed"},
                correlation_id=_optional_str(body.get("correlationId")),
                fingerprint=fingerprint,
            )
        if mode == "human_approval_required":
            approval = {
                "state": "required",
                "requiredRole": str(policy["constraints"].get("approvalRole") or "override authority"),
                "reason": "Trigger policy requires human approval before downstream execution.",
            }
            return self._record_receipt(
                policy=policy,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                facts_passed=facts_passed,
                source_event=source_event,
                decision="approval_required",
                status="waiting_for_approval",
                approval_state=approval,
                execution={"status": "not_started"},
                guardrail={"state": "passed"},
                correlation_id=_optional_str(body.get("correlationId")),
                fingerprint=fingerprint,
            )

        try:
            execution = self._execute_target(policy, body, actor, facts_passed, owner_id)
        except Exception as exc:
            return self._record_receipt(
                policy=policy,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                facts_passed=facts_passed,
                source_event=source_event,
                decision="execution_failed",
                status="failed",
                approval_state={},
                execution={"status": "failed", "error": str(exc)},
                guardrail={"state": "passed"},
                correlation_id=_optional_str(body.get("correlationId")),
                fingerprint=fingerprint,
            )
        return self._record_receipt(
            policy=policy,
            idempotency_key=idempotency_key,
            event_type=event_type,
            actor=actor,
            facts_passed=facts_passed,
            source_event=source_event,
            decision="executed",
            status="started",
            approval_state={"state": "not_required"},
            execution=execution,
            guardrail={"state": "passed"},
            correlation_id=_optional_str(body.get("correlationId")),
            fingerprint=fingerprint,
        )

    def _guardrail_decision(
        self,
        policy: dict[str, Any],
        body: dict[str, Any],
        source_event: dict[str, Any],
    ) -> dict[str, Any] | None:
        constraints = policy["constraints"]
        depth = _int_value(body.get("depth"), source_event.get("triggerDepth"), default=0)
        max_depth = _int_value(constraints.get("maxDepth"), default=4)
        if depth >= max_depth:
            return {
                "state": "blocked",
                "reason": "max_depth_exceeded",
                "depth": depth,
                "maxDepth": max_depth,
            }
        threshold = _float_value(constraints.get("confidenceThreshold"), default=0.0)
        confidence = _float_value(body.get("confidence"), source_event.get("confidence"), default=1.0)
        if confidence < threshold:
            return {
                "state": "blocked",
                "reason": "confidence_below_threshold",
                "confidence": confidence,
                "threshold": threshold,
            }
        required_evidence = _string_list(constraints.get("requiredEvidenceRefs"))
        evidence_refs = set(_string_list(body.get("evidenceRefs")) + _string_list(source_event.get("evidenceRefs")))
        missing_evidence = [ref for ref in required_evidence if ref not in evidence_refs]
        if missing_evidence:
            return {
                "state": "blocked",
                "reason": "missing_required_evidence",
                "missingEvidenceRefs": missing_evidence,
            }
        supplied_snapshot = _dict_value(
            body.get("featureFlagSnapshot") or source_event.get("featureFlagSnapshot")
        )
        if supplied_snapshot and not _snapshot_matches_current(supplied_snapshot):
            return {
                "state": "blocked",
                "reason": "feature_flag_snapshot_mismatch",
                "snapshotKeys": sorted(supplied_snapshot),
            }
        return None

    def _execute_target(
        self,
        policy: dict[str, Any],
        body: dict[str, Any],
        actor: dict[str, Any],
        facts_passed: dict[str, Any],
        owner_id: str | None,
    ) -> dict[str, Any]:
        target = policy["target"]
        if target["type"] == "rule_set":
            session = self._session_service.create_session_from_rule(
                rule_name=str(target["ruleName"]),
                target_node_name=str(target["targetNodeName"]),
                rule_service=self._rule_service,
                owner_id=owner_id,
                ontology_profile=target.get("ontologyProfile"),
                ontology_flags=target.get("ontologyFlags"),
                llm_configuration=(
                    self._llm_configuration_provider()
                    if self._llm_configuration_provider is not None
                    else None
                ),
            )
            _apply_facts(session, facts_passed)
            self._session_service.save_session(session)
            return {
                "type": "rule_set",
                "status": "started",
                "sessionId": session.session_id,
                "ruleName": session.rule_name,
                "targetNodeName": session.target_node_name,
                "ownerId": session.owner_id,
                "featureFlagSnapshot": (
                    session.feature_flags.snapshot() if session.feature_flags is not None else {}
                ),
            }

        action = deepcopy(target["action"])
        action_body = {
            "runId": body.get("targetRunId") or f"aegis_trigger_action_{uuid4().hex}",
            "proposalId": body.get("proposalId") or f"aegis_trigger_proposal_{uuid4().hex}",
            "workflowId": target.get("workflowId") or "aegis-action-firewall",
            "workflowVersionId": target.get("workflowVersionId"),
            "action": action,
            "actor": actor,
            "facts": {name: fact["value"] for name, fact in facts_passed.items()},
            "evidenceRefs": _string_list(body.get("evidenceRefs")),
            "evidenceHashes": _dict_value(body.get("evidenceHashes")),
            "policyHashes": {
                "triggerPolicyHash": policy["policyHash"],
                "triggerPolicyVersion": policy["version"],
            },
            "idempotencyKey": str(body.get("actionIdempotencyKey") or f"{body.get('idempotencyKey')}:action"),
        }
        result = self._phase3_service.create_action_proposal(action_body)
        return {
            "type": "action",
            "status": "proposed",
            "runId": result["run"]["runId"],
            "proposalId": result["actionProposal"]["proposalId"],
            "allowedActions": result["allowedActions"],
        }

    def _record_receipt(
        self,
        *,
        policy: dict[str, Any],
        idempotency_key: str,
        event_type: str,
        actor: dict[str, Any],
        facts_passed: dict[str, Any],
        source_event: dict[str, Any],
        decision: str,
        status: str,
        approval_state: dict[str, Any],
        execution: dict[str, Any],
        guardrail: dict[str, Any],
        correlation_id: str | None,
        fingerprint: str,
    ) -> dict[str, Any]:
        trigger_run_id = f"aegis_trigger_{uuid4().hex}"
        payload = {
            "fingerprint": fingerprint,
            "policy": {
                "policyId": policy["policyId"],
                "version": policy["version"],
                "policyHash": policy["policyHash"],
            },
            "sourceEvent": _source_event_audit_summary(source_event),
        }
        result = self._repository.append_receipt(
            trigger_run_id=trigger_run_id,
            policy_id=policy["policyId"],
            idempotency_key=idempotency_key,
            event_type=event_type,
            mode=policy["mode"],
            decision=decision,
            status=status,
            source=policy["source"],
            target=policy["target"],
            actor=actor,
            facts_passed=facts_passed,
            approval_state=approval_state,
            execution=execution,
            guardrail=guardrail,
            correlation_id=correlation_id,
            policy_hash=policy["policyHash"],
            payload=payload,
            fingerprint=fingerprint,
        )
        return {
            "policy": policy,
            "triggerReceipt": result["receipt"],
            "idempotentReplay": result["idempotentReplay"],
        }


def _normalise_mode(value: Any) -> str:
    mode = str(value or "recommend_only").strip().lower().replace("-", "_")
    if mode not in TRIGGER_MODES:
        raise AegisTriggerValidationError(
            "mode must be recommend_only, human_approval_required, or automatic"
        )
    return mode


def _normalise_source(body: dict[str, Any]) -> dict[str, Any]:
    raw = _dict_value(body.get("source"))
    source_type = str(raw.get("type") or body.get("sourceType") or "rule_set").strip().lower().replace("-", "_")
    if source_type not in SOURCE_TYPES:
        raise AegisTriggerValidationError("source.type must be rule_set or direct")
    if source_type == "direct":
        return {
            "type": "direct",
            "eventType": str(raw.get("eventType") or body.get("eventType") or "direct_request"),
        }
    rule_name = str(raw.get("ruleName") or body.get("sourceRuleName") or body.get("source_rule_name") or "").strip()
    if not rule_name:
        raise AegisTriggerValidationError("rule-set trigger sources require ruleName")
    return {"type": "rule_set", "ruleName": rule_name}


def _normalise_target(body: dict[str, Any]) -> dict[str, Any]:
    raw = _dict_value(body.get("target"))
    target_type = str(raw.get("type") or body.get("targetType") or "rule_set").strip().lower().replace("-", "_")
    if target_type not in TARGET_TYPES:
        raise AegisTriggerValidationError("target.type must be rule_set or action")
    if target_type == "rule_set":
        rule_name = str(raw.get("ruleName") or body.get("targetRuleName") or body.get("target_rule_name") or "").strip()
        target_node = str(
            raw.get("targetNodeName") or body.get("targetNodeName") or body.get("target_node_name") or ""
        ).strip()
        target = {"type": "rule_set", "ruleName": rule_name, "targetNodeName": target_node}
        if raw.get("ontologyProfile"):
            target["ontologyProfile"] = raw.get("ontologyProfile")
        if isinstance(raw.get("ontologyFlags"), dict):
            target["ontologyFlags"] = deepcopy(raw["ontologyFlags"])
        if not rule_name:
            raise AegisTriggerValidationError("rule-set trigger targets require ruleName")
        return target

    action = _dict_value(raw.get("action") or body.get("action"))
    if not action.get("kind") or not action.get("target"):
        raise AegisTriggerValidationError("action trigger targets require action.kind and action.target")
    return {
        "type": "action",
        "workflowId": str(raw.get("workflowId") or body.get("workflowId") or "aegis-action-firewall"),
        "workflowVersionId": raw.get("workflowVersionId") or body.get("workflowVersionId"),
        "action": action,
    }


def _normalise_constraints(body: dict[str, Any]) -> dict[str, Any]:
    raw = _dict_value(body.get("constraints"))
    constraints = {
        "maxDepth": _int_value(raw.get("maxDepth"), body.get("maxDepth"), default=4),
        "factSourceFilter": _fact_source_filter(raw),
        "confidenceThreshold": _float_value(raw.get("confidenceThreshold"), body.get("confidenceThreshold"), default=0.0),
        "requiredEvidenceRefs": _string_list(raw.get("requiredEvidenceRefs") or body.get("requiredEvidenceRefs")),
    }
    if raw.get("approvalRole"):
        constraints["approvalRole"] = str(raw["approvalRole"])
    return constraints


def _source_key(source: dict[str, Any]) -> str:
    if source["type"] == "direct":
        return f"direct:{source['eventType']}"
    return f"rule_set:{source['ruleName']}"


def _target_key(target: dict[str, Any]) -> str:
    if target["type"] == "action":
        action = target["action"]
        return f"action:{target.get('workflowId')}:{action.get('kind')}:{action.get('target')}"
    return f"rule_set:{target['ruleName']}:{target['targetNodeName']}"


def _rule_set_cycle_key(value: dict[str, Any]) -> str:
    return f"rule_set:{value['ruleName']}"


def _has_path(edges: list[tuple[str, str]], start: str, goal: str) -> bool:
    adjacency: dict[str, set[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, set()).add(target)
    stack = [start]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return False


def _source_result_matches_policy(policy: dict[str, Any], source_result: dict[str, Any]) -> bool:
    source = policy["source"]
    if source.get("type") != "rule_set":
        return False
    return str(source_result.get("ruleName") or source_result.get("rule_name") or "") == source["ruleName"]


def _outcome_condition_matches(policy: dict[str, Any], source_event: dict[str, Any]) -> bool:
    when = _dict_value(policy.get("payload", {}).get("when"))
    if "outcome" not in when:
        return True
    expected = _normalise_outcome_value(when.get("outcome"))
    actual_value = (
        source_event["outcome"]
        if "outcome" in source_event
        else source_event.get("goalRuleValue")
    )
    actual = _normalise_outcome_value(actual_value)
    return expected == actual


def _normalise_outcome_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().lower()


def _source_event_audit_summary(source_event: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "ruleName",
        "rule_name",
        "outcome",
        "goalRuleValue",
        "confidence",
        "triggerDepth",
    ):
        if key in source_event:
            summary[key] = deepcopy(source_event[key])

    evidence_refs = _string_list(source_event.get("evidenceRefs"))
    if evidence_refs:
        summary["evidenceRefs"] = evidence_refs

    supplied_snapshot = _dict_value(source_event.get("featureFlagSnapshot"))
    if supplied_snapshot:
        summary["featureFlagSnapshot"] = {
            "keys": sorted(str(key) for key in supplied_snapshot),
            "snapshotHash": stable_hash(supplied_snapshot),
        }

    raw_facts = _dict_value(source_event.get("facts"))
    if raw_facts:
        source_counts: dict[str, int] = {}
        for raw in raw_facts.values():
            if isinstance(raw, dict) and "value" in raw:
                source = str(raw.get("source") or "ASSERTED").upper()
            else:
                source = "ASSERTED"
            source_counts[source] = source_counts.get(source, 0) + 1
        summary["factSummary"] = {
            "count": len(raw_facts),
            "sourceCounts": dict(sorted(source_counts.items())),
        }
    return summary


def _filter_facts(raw_facts: dict[str, Any], allowed_sources: list[str]) -> dict[str, Any]:
    allowed = {source.upper() for source in allowed_sources}
    facts: dict[str, Any] = {}
    for name, raw in raw_facts.items():
        if not name:
            continue
        if isinstance(raw, dict) and "value" in raw:
            value = raw.get("value")
            source = str(raw.get("source") or "ASSERTED").upper()
        else:
            value = raw
            source = "ASSERTED"
        if source not in allowed:
            continue
        facts[str(name)] = {
            "value": value,
            "source": source,
            "valueType": _fact_value_type(value),
        }
    return facts


def _apply_facts(session: InferenceSession, facts_passed: dict[str, Any]) -> None:
    assessment_state = session.inference_engine.get_assessment_state()
    for name, fact in facts_passed.items():
        source = FactSource.from_value(str(fact.get("source") or "ASSERTED").upper())
        assessment_state.set_fact(name, FactValue(fact.get("value")), source=source)


def _fact_source_filter(value: dict[str, Any]) -> list[str]:
    raw = value.get("factSourceFilter") or value.get("fact_source_filter") or DEFAULT_FACT_SOURCE_FILTER
    if not isinstance(raw, (list, tuple, set)):
        raw = DEFAULT_FACT_SOURCE_FILTER
    parsed = []
    for item in raw:
        source = str(item).strip().upper()
        if source in FactSource.__members__:
            parsed.append(source)
    return parsed or list(DEFAULT_FACT_SOURCE_FILTER)


def _snapshot_matches_current(supplied_snapshot: dict[str, Any]) -> bool:
    current = get_feature_flags().snapshot()
    return all(current.get(key) == value for key, value in supplied_snapshot.items())


def _fact_value_type(value: Any) -> str:
    return FactValue(value).get_value_type().value


def _actor(value: Any, *, role: str, actor_id: str) -> dict[str, Any]:
    actor = deepcopy(value) if isinstance(value, dict) else {}
    actor.setdefault("kind", "system" if role in OUTCOME_TRIGGER_ROLES else "human")
    actor.setdefault("id", actor_id)
    actor.setdefault("role", role)
    return actor


def _require_actor(actor: dict[str, Any], allowed_roles: set[str], operation: str) -> None:
    role = str(actor.get("role") or "").strip().lower().replace("_", " ").replace("-", " ")
    if role not in allowed_roles:
        raise AegisTriggerAuthorizationError(f"Role '{actor.get('role')}' is not authorized for {operation}")


def _dict_value(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(*values: Any, default: int) -> int:
    for value in values:
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def _float_value(*values: Any, default: float) -> float:
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default
