"""Persisted AEGIS workflow authoring contracts."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.adapters.outbound.persistence.aegis_workflow_repository import AegisWorkflowRepository
from src.domain.aegis.rule_store import AEGIS_PRODUCT, AEGIS_RULE_STORE, build_policy_integrity, stable_hash
from src.services.rule_service import RuleService

AUTHORING_MODES = ("Author", "Validate", "Simulate", "Runtime", "Proof")
GENERATION_CONTRACT_VERSION = "aegis-workflow-generation-v1"
GENERATION_TEMPLATE_ID = "deterministic-action-firewall-v1"
GENERATED_ACTIVATION_APPROVAL_STATUS = {"approved", "rejected"}
TERMINAL_NODE_TYPES = {"CERTIFICATION_EXPORT"}
SANCTIONED_NODE_TYPES = {
    "REQUEST",
    "EVIDENCE_CAPTURE",
    "FACT_EXTRACTION",
    "RULE_GATE",
    "OPTION_SET",
    "HUMAN_APPROVAL",
    "AGENT_ACTION",
    "ACTUATION",
    "ESCALATION",
    "FALLBACK",
    "RECEIPT_SEAL",
    "CERTIFICATION_EXPORT",
}
ALLOWED_TRANSITIONS = {
    "REQUEST": {
        "EVIDENCE_CAPTURE",
        "FACT_EXTRACTION",
        "RULE_GATE",
        "OPTION_SET",
        "HUMAN_APPROVAL",
    },
    "EVIDENCE_CAPTURE": {
        "FACT_EXTRACTION",
        "RULE_GATE",
        "OPTION_SET",
        "HUMAN_APPROVAL",
        "AGENT_ACTION",
    },
    "FACT_EXTRACTION": {"RULE_GATE", "OPTION_SET", "HUMAN_APPROVAL", "AGENT_ACTION"},
    "RULE_GATE": {
        "OPTION_SET",
        "HUMAN_APPROVAL",
        "AGENT_ACTION",
        "ACTUATION",
        "ESCALATION",
        "FALLBACK",
        "RECEIPT_SEAL",
    },
    "OPTION_SET": {"HUMAN_APPROVAL", "AGENT_ACTION", "ACTUATION", "ESCALATION", "FALLBACK", "RECEIPT_SEAL"},
    "HUMAN_APPROVAL": {"AGENT_ACTION", "ACTUATION", "ESCALATION", "FALLBACK", "RECEIPT_SEAL"},
    "AGENT_ACTION": {"ACTUATION", "RECEIPT_SEAL", "FALLBACK", "ESCALATION"},
    "ACTUATION": {"RECEIPT_SEAL", "FALLBACK", "ESCALATION"},
    "ESCALATION": {"HUMAN_APPROVAL", "FALLBACK", "RECEIPT_SEAL"},
    "FALLBACK": {"RECEIPT_SEAL"},
    "RECEIPT_SEAL": {"CERTIFICATION_EXPORT"},
    "CERTIFICATION_EXPORT": set(),
}
COMMON_REQUIRED_FIELDS = {
    "id",
    "label",
    "type",
    "owner",
    "role",
    "entryCriteria",
    "exitCriteria",
    "requiredEvidenceRefs",
    "producedEvidenceRefs",
    "recoveryActions",
}
COMMON_REQUIRED_NESTED_FIELDS = {
    "conditionMetadata.entryConditions",
    "conditionMetadata.exitConditions",
}
EMPTY_LIST_ALLOWED_FIELDS = {"producedEvidenceRefs", "opposingEvidenceRefs"}
NODE_REQUIRED_FIELDS = {
    "REQUEST": {
        "requester",
        "requestedOutcome",
        "actionDomain",
        "inputFacts",
        "idempotencyKey",
    },
    "EVIDENCE_CAPTURE": {"evidenceOwner", "acceptedValueTypes", "freshnessRequirement"},
    "FACT_EXTRACTION": {"inputEvidenceRefs", "producedFactRefs", "extractionMethod"},
    "RULE_GATE": {"ruleName", "targetNodeName"},
    "OPTION_SET": {"options"},
    "HUMAN_APPROVAL": {"approverRole", "authoritySource", "allowedDecisions", "rationaleRequired"},
    "AGENT_ACTION": {"agentId", "autonomyLevel", "requestedAction", "riskScore", "fallbackPath"},
    "ACTUATION": {"assetLayer", "commandSummary", "safeMode", "fallbackTrigger", "stopCondition"},
    "ESCALATION": {"escalationReason", "targetOwner", "slaImpact"},
    "FALLBACK": {"fallbackTrigger", "fallbackAction", "safetyRationale"},
    "RECEIPT_SEAL": {"receiptType", "eventSequenceRange", "previousHash"},
    "CERTIFICATION_EXPORT": {"exportFormat", "dossierId", "includedArtifacts"},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _value_at(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _has_value(payload: dict[str, Any], dotted_path: str) -> bool:
    value = _value_at(payload, dotted_path)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _has_required_field(payload: dict[str, Any], dotted_path: str) -> bool:
    if dotted_path.split(".")[-1] in EMPTY_LIST_ALLOWED_FIELDS:
        return _value_at(payload, dotted_path) is not None
    return _has_value(payload, dotted_path)


def _normalise_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalise_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _slug(value: Any) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "workflow"))
    slug = "-".join(part for part in cleaned.split("-") if part)
    return slug[:64] or "workflow"


def _node_field(node: dict[str, Any], key: str) -> Any:
    value = node.get(key)
    if value is not None:
        return value
    policy_binding = node.get("policyBinding")
    if isinstance(policy_binding, dict):
        return policy_binding.get(key)
    return None


class AegisWorkflowActivationError(ValueError):
    """Raised when a workflow activation gate is not satisfied."""


class AegisWorkflowAuthoringService:
    """Application service for persisted Workflow Studio authoring."""

    def __init__(
        self,
        repository: AegisWorkflowRepository,
        rule_service: RuleService | None = None,
    ):
        self._repository = repository
        self._rule_service = rule_service

    def list_workflows(self) -> list[dict[str, Any]]:
        return self._repository.list_definitions()

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        definition = self._repository.get_definition(workflow_id)
        if definition is None:
            raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
        latest = self._repository.get_latest_version(workflow_id)
        if latest is None:
            return definition
        return self._workflow_response(definition, latest)

    def create_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str(payload.get("id") or payload.get("workflowId") or f"workflow-{uuid4().hex[:12]}")
        definition = self._canonical_definition(workflow_id, payload)
        return self._persist_new_workflow(definition, created_by=payload.get("createdBy"))

    def generate_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = self._draft_workflow_id(payload, "generate")
        definition = self._generated_template_definition(
            workflow_id,
            payload,
            generation_kind="generate",
        )
        return self._persist_generated_workflow(definition, created_by=payload.get("createdBy"))

    def regenerate_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_workflow_id = str(payload.get("workflowId") or payload.get("sourceWorkflowId") or "").strip()
        if not source_workflow_id:
            raise ValueError("workflowId or sourceWorkflowId is required for regeneration")
        latest = self._repository.get_latest_version(source_workflow_id)
        if latest is None:
            raise LookupError(f"AEGIS workflow '{source_workflow_id}' was not found")
        base_definition = latest["definition"]
        workflow_id = self._draft_workflow_id(payload, "regenerate", source_workflow_id=source_workflow_id)
        definition = self._generated_template_definition(
            workflow_id,
            payload,
            generation_kind="regenerate",
            base_definition=base_definition,
        )
        return self._persist_generated_workflow(definition, created_by=payload.get("createdBy"))

    def extend_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_workflow_id = str(payload.get("workflowId") or payload.get("sourceWorkflowId") or "").strip()
        if not source_workflow_id:
            raise ValueError("workflowId or sourceWorkflowId is required for extension")
        latest = self._repository.get_latest_version(source_workflow_id)
        if latest is None:
            raise LookupError(f"AEGIS workflow '{source_workflow_id}' was not found")
        base_definition = latest["definition"]
        workflow_id = self._draft_workflow_id(payload, "extend", source_workflow_id=source_workflow_id)
        definition = self._generated_template_definition(
            workflow_id,
            payload,
            generation_kind="extend",
            base_definition=base_definition,
        )
        return self._persist_generated_workflow(definition, created_by=payload.get("createdBy"))

    def update_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._repository.get_latest_version(workflow_id)
        if current is None:
            raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
        expected_hash = payload.get("expectedVersionHash") or payload.get("ifMatchVersionHash")
        base_definition = deepcopy(current["definition"])
        merged = {**base_definition, **payload, "id": workflow_id, "workflowId": workflow_id}
        merged.pop("expectedVersionHash", None)
        merged.pop("ifMatchVersionHash", None)
        definition = self._canonical_definition(workflow_id, merged)
        validation = self.validate_definition(definition)
        version = self._repository.append_version(
            workflow_id=workflow_id,
            version_id=f"wfv-{uuid4().hex}",
            definition_payload=definition,
            validation_snapshot=validation,
            version_hash=self.version_hash(definition),
            graph_hash=self.graph_hash(definition),
            status=self._definition_status(definition, validation),
            expected_version_hash=str(expected_hash) if expected_hash else None,
            created_by=payload.get("updatedBy") or payload.get("createdBy"),
        )
        return {
            "workflow": self.get_workflow(workflow_id),
            "version": version,
            "validation": validation,
        }

    def list_versions(self, workflow_id: str) -> dict[str, Any]:
        return {
            "workflowId": workflow_id,
            "versions": self._repository.list_versions(workflow_id),
        }

    def get_version(self, workflow_id: str, version_id: str) -> dict[str, Any]:
        version = self._repository.get_version(workflow_id, version_id)
        if version is None:
            raise LookupError(f"Workflow version '{version_id}' was not found")
        return version

    def validate_workflow(self, workflow_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            definition = self._canonical_definition(workflow_id, payload)
        else:
            latest = self._repository.get_latest_version(workflow_id)
            if latest is None:
                raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
            definition = latest["definition"]
        return self.validate_definition(definition)

    def compile_workflow(self, workflow_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        latest = self._repository.get_latest_version(workflow_id)
        if latest is None:
            raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
        if payload:
            definition = self._canonical_definition(workflow_id, payload)
            version_hash = self.version_hash(definition)
            graph_hash = self.graph_hash(definition)
            version_id = latest["versionId"] if version_hash == latest["versionHash"] else f"draft-{uuid4().hex}"
        else:
            definition = latest["definition"]
            version_hash = latest["versionHash"]
            graph_hash = latest["graphHash"]
            version_id = latest["versionId"]

        validation = self.validate_definition(definition)
        blocking = [diagnostic for diagnostic in validation["diagnostics"] if diagnostic["blocksCompile"]]
        if blocking:
            return {
                "workflowId": workflow_id,
                "versionId": version_id,
                "status": "compile_blocked",
                "activationReady": False,
                "diagnostics": blocking,
                "validation": validation,
            }

        activation_requirement = self._activation_requirement(definition, validation)
        activation_ready = not activation_requirement["blocksActivation"]
        compile_status = "compiled" if activation_ready else "compiled_activation_pending"
        compile_output = {
            "workflowId": workflow_id,
            "versionId": version_id,
            "status": compile_status,
            "activationReady": activation_ready,
            "activationRequirement": activation_requirement,
            "compiledAt": _utc_now(),
            "graphHash": graph_hash,
            "versionHash": version_hash,
            "validationTimestamp": validation["validatedAt"],
            "ruleBindings": validation["ruleBindings"],
            "compiledPolicyRefs": [
                {
                    "ruleName": binding["ruleName"],
                    "targetNodeName": binding.get("targetNodeName"),
                    "ruleVersionHash": binding.get("ruleVersionHash"),
                    "importTreeHash": binding.get("importTreeHash"),
                    "validationStatus": binding.get("validationStatus"),
                }
                for binding in validation["ruleBindings"]
            ],
            "evidenceContract": self._evidence_contract(definition),
            "factIngestionContract": self._fact_ingestion_contract(definition),
            "confidenceExplanation": self._confidence_explanation(definition, validation),
            "receiptRequirements": self._receipt_requirements(definition),
        }
        if version_id == latest["versionId"]:
            self._repository.store_compile_output(
                workflow_id=workflow_id,
                version_id=version_id,
                compile_output=compile_output,
                status="compiled" if activation_ready else "activation_pending",
            )
        return compile_output

    def record_activation_approval(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        latest = self._repository.get_latest_version(workflow_id)
        if latest is None:
            raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
        definition = deepcopy(latest["definition"])
        if not self._is_generated_definition(definition):
            raise ValueError("Activation approval is required only for generated workflow drafts")

        decision = str(payload.get("decision") or payload.get("status") or "approved").strip().lower()
        if decision not in GENERATED_ACTIVATION_APPROVAL_STATUS:
            raise ValueError("activation approval decision must be approved or rejected")

        metadata = deepcopy(definition.get("metadata") or {})
        generation = deepcopy(metadata.get("generation") or {})
        approval = deepcopy(generation.get("humanActivationApproval") or {})
        approval.update(
            {
                "required": True,
                "status": decision,
                "approvalId": str(payload.get("approvalId") or f"approval-{uuid4().hex}"),
                "approvedBy": payload.get("approvedBy") or payload.get("actor") or "workflow-owner",
                "approverRole": str(payload.get("approverRole") or approval.get("approverRole") or "workflow owner"),
                "rationale": str(payload.get("rationale") or f"Generated workflow activation {decision}."),
                "decidedAt": _utc_now(),
            }
        )
        generation["humanActivationApproval"] = approval
        metadata["generation"] = generation
        definition["metadata"] = metadata

        validation = self.validate_definition(definition)
        version = self._repository.append_version(
            workflow_id=workflow_id,
            version_id=f"wfv-{uuid4().hex}",
            definition_payload=definition,
            validation_snapshot=validation,
            version_hash=self.version_hash(definition),
            graph_hash=self.graph_hash(definition),
            status="generated_draft" if validation["valid"] else "invalid",
            expected_version_hash=latest["versionHash"],
            created_by=payload.get("approvedBy") or payload.get("createdBy"),
        )
        return {
            "workflow": self.get_workflow(workflow_id),
            "version": version,
            "validation": validation,
            "activationApproval": approval,
        }

    def activate_workflow(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        latest = self._repository.get_latest_version(workflow_id)
        if latest is None:
            raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
        definition = latest["definition"]
        validation = self.validate_definition(definition)
        if not validation["valid"]:
            raise AegisWorkflowActivationError("Workflow validation must pass before activation")

        activation_requirement = self._activation_requirement(definition, validation)
        if activation_requirement["blocksActivation"]:
            raise AegisWorkflowActivationError(activation_requirement["reason"])

        compile_output = self.compile_workflow(workflow_id)
        activation = {
            "workflowId": workflow_id,
            "status": "active",
            "activatedAt": _utc_now(),
            "activatedBy": payload.get("activatedBy") or payload.get("actor") or "workflow-owner",
            "approval": activation_requirement["approval"],
            "validation": {
                "valid": validation["valid"],
                "severityCounts": validation["severityCounts"],
                "validationTimestamp": validation["validatedAt"],
            },
        }
        compile_output = deepcopy(compile_output)
        compile_output["activation"] = activation
        version = self._repository.store_compile_output(
            workflow_id=workflow_id,
            version_id=latest["versionId"],
            compile_output=compile_output,
            status="active",
        )
        return {
            "workflowId": workflow_id,
            "status": "active",
            "activation": activation,
            "version": version,
            "compileOutput": compile_output,
        }

    def validate_definition(self, definition: dict[str, Any]) -> dict[str, Any]:
        diagnostics: list[dict[str, Any]] = []
        rule_bindings: list[dict[str, Any]] = []
        nodes = _normalise_list(definition.get("nodes"))
        transitions = _normalise_list(definition.get("transitions"))
        node_by_id = {
            str(node.get("id")): node
            for node in nodes
            if isinstance(node, dict) and node.get("id")
        }
        duplicate_ids = self._duplicate_node_ids(nodes)

        if not nodes:
            diagnostics.append(self._diagnostic("EMPTY_WORKFLOW", "error", "Workflow has no nodes."))

        for node_id in duplicate_ids:
            diagnostics.append(
                self._diagnostic(
                    "DUPLICATE_NODE_ID",
                    "error",
                    f"Node id '{node_id}' appears more than once.",
                    node_id=node_id,
                    field="id",
                )
            )

        for node in nodes:
            if not isinstance(node, dict):
                diagnostics.append(self._diagnostic("INVALID_NODE", "error", "Node payload must be an object."))
                continue
            self._validate_node_contract(node, diagnostics)

        self._validate_transitions(transitions, node_by_id, diagnostics)
        self._validate_reachability(nodes, transitions, node_by_id, diagnostics)
        self._validate_evidence_contract(definition, nodes, diagnostics)
        rule_bindings.extend(self._validate_rule_bindings(nodes, diagnostics))

        severity_counts = {
            "error": sum(1 for diagnostic in diagnostics if diagnostic["severity"] == "error"),
            "warning": sum(1 for diagnostic in diagnostics if diagnostic["severity"] == "warning"),
            "info": sum(1 for diagnostic in diagnostics if diagnostic["severity"] == "info"),
        }
        return {
            "workflowId": definition["id"],
            "valid": severity_counts["error"] == 0,
            "severityCounts": severity_counts,
            "diagnostics": diagnostics,
            "ruleBindings": rule_bindings,
            "graphHash": self.graph_hash(definition),
            "versionHash": self.version_hash(definition),
            "validatedAt": _utc_now(),
        }

    @staticmethod
    def version_hash(definition: dict[str, Any]) -> str:
        return stable_hash({"definition": definition, "contract": "aegis-workflow-authoring-v1"})

    @staticmethod
    def graph_hash(definition: dict[str, Any]) -> str:
        return stable_hash(
            {
                "nodes": definition.get("nodes", []),
                "transitions": definition.get("transitions", []),
                "receiptPolicy": definition.get("receiptPolicy", {}),
            }
        )

    def _canonical_definition(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        nodes = deepcopy(payload.get("nodes") or [])
        transitions = deepcopy(payload.get("transitions") or [])
        return {
            "id": workflow_id,
            "workflowId": workflow_id,
            "title": str(payload.get("title") or payload.get("name") or workflow_id),
            "domain": str(payload.get("domain") or "general"),
            "modes": list(payload.get("modes") or AUTHORING_MODES),
            "isSynthetic": bool(payload.get("isSynthetic", False)),
            "nodes": nodes,
            "transitions": transitions,
            "evidence": deepcopy(payload.get("evidence") or []),
            "receiptPolicy": deepcopy(payload.get("receiptPolicy") or {}),
            "dossierSchema": deepcopy(payload.get("dossierSchema") or {}),
            "metadata": deepcopy(payload.get("metadata") or {}),
        }

    def _persist_new_workflow(self, definition: dict[str, Any], *, created_by: str | None = None) -> dict[str, Any]:
        workflow_id = str(definition["id"])
        validation = self.validate_definition(definition)
        version_hash = self.version_hash(definition)
        graph_hash = self.graph_hash(definition)
        status = self._definition_status(definition, validation)

        self._repository.create_definition(
            workflow_id=workflow_id,
            title=str(definition.get("title") or workflow_id),
            domain=str(definition.get("domain") or "general"),
            created_by=created_by,
        )
        version = self._repository.append_version(
            workflow_id=workflow_id,
            version_id=f"wfv-{uuid4().hex}",
            definition_payload=definition,
            validation_snapshot=validation,
            version_hash=version_hash,
            graph_hash=graph_hash,
            status=status,
            created_by=created_by,
        )
        return {
            "workflow": self.get_workflow(workflow_id),
            "version": version,
            "validation": validation,
        }

    def _persist_generated_workflow(
        self,
        definition: dict[str, Any],
        *,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        initial_validation = self.validate_definition(definition)
        definition = self._definition_with_generation_validation(definition, initial_validation)
        result = self._persist_new_workflow(definition, created_by=created_by)
        metadata = result["workflow"].get("metadata", {})
        return {
            **result,
            "generatedDraft": deepcopy(metadata.get("generation", {})),
        }

    def _draft_workflow_id(
        self,
        payload: dict[str, Any],
        generation_kind: str,
        *,
        source_workflow_id: str | None = None,
    ) -> str:
        explicit_id = payload.get("id") or payload.get("draftWorkflowId")
        if generation_kind == "generate":
            explicit_id = explicit_id or payload.get("workflowId")
        if explicit_id:
            return str(explicit_id)

        fingerprint = stable_hash(
            {
                "kind": generation_kind,
                "sourceWorkflowId": source_workflow_id,
                "templateId": payload.get("templateId") or GENERATION_TEMPLATE_ID,
                "domain": payload.get("domain"),
                "title": payload.get("title") or payload.get("objective"),
                "facts": _normalise_dict(payload.get("facts")),
                "evidenceRefs": _string_list(payload.get("evidenceRefs")),
                "ruleName": payload.get("ruleName") or payload.get("policyRuleName"),
            }
        )[7:19]
        stem = source_workflow_id or payload.get("domain") or payload.get("title") or "workflow"
        return f"{_slug(stem)}-{generation_kind}-{fingerprint}"

    def _generated_template_definition(
        self,
        workflow_id: str,
        payload: dict[str, Any],
        *,
        generation_kind: str,
        base_definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = deepcopy(base_definition or {})
        domain = str(payload.get("domain") or base.get("domain") or "general")
        title = str(payload.get("title") or payload.get("objective") or f"{domain.title()} Generated Workflow")
        template_id = str(payload.get("templateId") or GENERATION_TEMPLATE_ID)
        rule_name = str(payload.get("ruleName") or payload.get("policyRuleName") or "robot_safety_gate")
        target_node_name = str(payload.get("targetNodeName") or "eligible")
        node_prefix = _slug(workflow_id)
        facts = _normalise_dict(payload.get("facts")) or {"requestComplete": True}

        evidence = deepcopy(payload.get("evidence")) if isinstance(payload.get("evidence"), list) else []
        evidence_refs = _string_list(payload.get("evidenceRefs")) or [
            str(item.get("id")) for item in evidence if isinstance(item, dict) and item.get("id")
        ]
        if not evidence_refs:
            evidence_refs = [f"{node_prefix}-request-evidence"]
        if not evidence:
            evidence = [
                {
                    "id": evidence_ref,
                    "sourceLayer": "ASSERTED",
                    "value": "deterministic generation input",
                    "valueType": "string",
                    "confidence": 1.0,
                    "trustScore": 0.9,
                    "sourceLabel": "aegis-generation-request",
                    "sourceUri": f"synthetic://aegis/workflows/{workflow_id}/generation/{evidence_ref}",
                    "contentHash": stable_hash({"workflowId": workflow_id, "evidenceRef": evidence_ref}),
                    "freshnessState": "fresh",
                    "sanitization": {"synthetic": True},
                }
                for evidence_ref in evidence_refs
            ]

        request_node_id = f"{node_prefix}-request"
        evidence_node_id = f"{node_prefix}-evidence"
        fact_node_id = f"{node_prefix}-facts"
        rule_node_id = f"{node_prefix}-rule"
        options_node_id = f"{node_prefix}-options"
        approval_node_id = f"{node_prefix}-approval"
        action_node_id = f"{node_prefix}-actuation"
        receipt_node_id = f"{node_prefix}-receipt"

        fact_evidence_ref = f"{node_prefix}-fact-source"
        extracted_fact_ref = f"{node_prefix}-extracted-facts"
        rule_result_ref = f"{node_prefix}-rule-result"
        selected_option_ref = f"{node_prefix}-selected-option"
        approval_ref = f"{node_prefix}-human-approval"
        actuation_ref = f"{node_prefix}-actuation-result"
        receipt_ref = f"{node_prefix}-receipt"

        nodes = [
            {
                "id": request_node_id,
                "label": "Generated request intake",
                "type": "REQUEST",
                "owner": payload.get("owner") or "AEGIS generation service",
                "role": "AI planner",
                "entryCriteria": ["generation request received"],
                "exitCriteria": ["requested outcome and grounding facts captured"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "generation request received"}],
                    "exitConditions": [{"condition": "requested outcome and grounding facts captured"}],
                },
                "requiredEvidenceRefs": evidence_refs,
                "producedEvidenceRefs": [],
                "recoveryActions": ["reject generated draft"],
                "requester": payload.get("requester") or "aegis-deterministic-generator",
                "requestedOutcome": payload.get("requestedOutcome") or title,
                "actionDomain": domain,
                "inputFacts": facts,
                "idempotencyKey": f"{workflow_id}:request",
            },
            {
                "id": evidence_node_id,
                "label": "Evidence grounding",
                "type": "EVIDENCE_CAPTURE",
                "owner": payload.get("evidenceOwner") or "AEGIS evidence registry",
                "role": "evidence collector",
                "entryCriteria": ["request facts available"],
                "exitCriteria": ["evidence references normalized"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "request facts available"}],
                    "exitConditions": [{"condition": "evidence references normalized"}],
                },
                "requiredEvidenceRefs": evidence_refs,
                "producedEvidenceRefs": [fact_evidence_ref],
                "recoveryActions": ["request missing evidence"],
                "evidenceOwner": payload.get("evidenceOwner") or "AEGIS evidence registry",
                "acceptedValueTypes": ["string", "number", "boolean", "json"],
                "freshnessRequirement": payload.get("freshnessRequirement") or "current generation request",
            },
            {
                "id": fact_node_id,
                "label": "Fact extraction",
                "type": "FACT_EXTRACTION",
                "owner": "AEGIS fact extractor",
                "role": "fact grounding",
                "entryCriteria": ["evidence normalized"],
                "exitCriteria": ["asserted facts available for rule gate"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "evidence normalized"}],
                    "exitConditions": [{"condition": "asserted facts available for rule gate"}],
                },
                "requiredEvidenceRefs": [fact_evidence_ref],
                "producedEvidenceRefs": [extracted_fact_ref],
                "recoveryActions": ["request corrected evidence"],
                "inputEvidenceRefs": evidence_refs,
                "producedFactRefs": sorted(facts.keys()),
                "extractionMethod": "deterministic-template-mapping",
            },
            {
                "id": rule_node_id,
                "label": "Policy gate",
                "type": "RULE_GATE",
                "owner": "INFERRA policy mesh",
                "role": "policy gate",
                "entryCriteria": ["facts extracted"],
                "exitCriteria": ["policy target evaluated"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "facts extracted"}],
                    "exitConditions": [{"condition": "policy target evaluated"}],
                },
                "requiredEvidenceRefs": [extracted_fact_ref],
                "producedEvidenceRefs": [rule_result_ref],
                "recoveryActions": ["request evidence", "escalate to owner"],
                "ruleName": rule_name,
                "targetNodeName": target_node_name,
            },
            {
                "id": options_node_id,
                "label": "Governed options",
                "type": "OPTION_SET",
                "owner": "AEGIS options ledger",
                "role": "options engine",
                "entryCriteria": ["policy result available"],
                "exitCriteria": ["approved option selected or fallback chosen"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "policy result available"}],
                    "exitConditions": [{"condition": "approved option selected or fallback chosen"}],
                },
                "requiredEvidenceRefs": [rule_result_ref],
                "producedEvidenceRefs": [selected_option_ref],
                "recoveryActions": ["select fallback", "request approval"],
                "options": [
                    {
                        "id": "human-reviewed-release",
                        "label": "Human-reviewed release",
                        "status": "available",
                        "confidence": float(payload.get("confidence", 0.82)),
                        "risk": float(payload.get("risk", 0.35)),
                        "supportingEvidenceRefs": [rule_result_ref],
                        "opposingEvidenceRefs": [],
                        "constraints": ["human activation approval required"],
                        "rationale": "Generated workflows require explicit human approval before activation.",
                        "requiredRole": payload.get("activationApproverRole") or "workflow owner",
                        "requiresApproval": True,
                        "wouldTriggerNodeId": approval_node_id,
                        "fallbackIfRejected": receipt_node_id,
                    }
                ],
            },
            {
                "id": approval_node_id,
                "label": "Activation approval",
                "type": "HUMAN_APPROVAL",
                "owner": payload.get("approvalOwner") or "workflow owner",
                "role": payload.get("activationApproverRole") or "workflow owner",
                "entryCriteria": ["generated draft validated"],
                "exitCriteria": ["activation approval recorded"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "generated draft validated"}],
                    "exitConditions": [{"condition": "activation approval recorded"}],
                },
                "requiredEvidenceRefs": [selected_option_ref],
                "producedEvidenceRefs": [approval_ref],
                "recoveryActions": ["reject generated draft", "request regeneration"],
                "approverRole": payload.get("activationApproverRole") or "workflow owner",
                "authoritySource": payload.get("authoritySource") or "AEGIS generated workflow governance",
                "allowedDecisions": ["approved", "rejected"],
                "rationaleRequired": True,
            },
            {
                "id": action_node_id,
                "label": "Bounded actuation",
                "type": "ACTUATION",
                "owner": payload.get("actuationOwner") or "workflow runtime",
                "role": "control layer",
                "entryCriteria": ["activation approval approved"],
                "exitCriteria": ["bounded action completed or blocked"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "activation approval approved"}],
                    "exitConditions": [{"condition": "bounded action completed or blocked"}],
                },
                "requiredEvidenceRefs": [approval_ref],
                "producedEvidenceRefs": [actuation_ref],
                "recoveryActions": ["execute fallback"],
                "assetLayer": payload.get("assetLayer") or "synthetic_runtime",
                "commandSummary": payload.get("commandSummary") or "Deterministic generated workflow no-op release",
                "safeMode": True,
                "fallbackTrigger": "activation.approval_rejected",
                "stopCondition": "receipt failed",
            },
            {
                "id": receipt_node_id,
                "label": "Seal generation receipt",
                "type": "RECEIPT_SEAL",
                "owner": "aegis-ledger",
                "role": "signature authority",
                "entryCriteria": ["actuation or rejection outcome available"],
                "exitCriteria": ["generation receipt sealed"],
                "conditionMetadata": {
                    "entryConditions": [{"condition": "actuation or rejection outcome available"}],
                    "exitConditions": [{"condition": "generation receipt sealed"}],
                },
                "requiredEvidenceRefs": [actuation_ref, rule_result_ref],
                "producedEvidenceRefs": [receipt_ref],
                "recoveryActions": ["retry receipt sealing"],
                "receiptType": "aegis_generated_workflow_receipt",
                "eventSequenceRange": [1, 8],
                "previousHash": "sha256:genesis",
            },
        ]
        transitions = [
            {"fromNodeId": request_node_id, "toNodeId": evidence_node_id, "triggerEvent": "request.created"},
            {"fromNodeId": evidence_node_id, "toNodeId": fact_node_id, "triggerEvent": "evidence.captured"},
            {"fromNodeId": fact_node_id, "toNodeId": rule_node_id, "triggerEvent": "facts.extracted"},
            {"fromNodeId": rule_node_id, "toNodeId": options_node_id, "triggerEvent": "rule.evaluated"},
            {"fromNodeId": options_node_id, "toNodeId": approval_node_id, "triggerEvent": "option.selected"},
            {"fromNodeId": approval_node_id, "toNodeId": action_node_id, "triggerEvent": "approval.approved"},
            {"fromNodeId": action_node_id, "toNodeId": receipt_node_id, "triggerEvent": "actuation.completed"},
        ]
        definition = {
            "id": workflow_id,
            "workflowId": workflow_id,
            "title": title,
            "domain": domain,
            "modes": list(payload.get("modes") or base.get("modes") or AUTHORING_MODES),
            "isSynthetic": False,
            "nodes": nodes,
            "transitions": transitions,
            "evidence": evidence,
            "receiptPolicy": {"sealOnEvents": ["receipt.sealed"], "requiredFields": ["ruleVersionHash"]},
            "dossierSchema": deepcopy(base.get("dossierSchema") or {}),
            "metadata": deepcopy(base.get("metadata") or {}),
        }
        metadata = definition["metadata"]
        metadata["generation"] = {
            "generatedDraft": True,
            "contractVersion": GENERATION_CONTRACT_VERSION,
            "source": "deterministic-template",
            "templateId": template_id,
            "generationKind": generation_kind,
            "baseWorkflowId": base.get("id") or base.get("workflowId"),
            "changeSet": self._change_set(base if base_definition else {}, definition),
            "basis": {
                "facts": sorted(facts.keys()),
                "evidenceRefs": sorted(evidence_refs),
                "ruleBasis": [{"ruleName": rule_name, "targetNodeName": target_node_name}],
                "policyVersionRequirements": {
                    "ruleName": rule_name,
                    "targetNodeName": target_node_name,
                },
            },
            "unresolvedAssumptions": _string_list(payload.get("unresolvedAssumptions")),
            "confidence": {
                "score": float(payload.get("confidence", 0.82)),
                "calibration": "deterministic-template-baseline",
                "authorityBoundary": {
                    "authoritativeFacts": "provenance-backed asserted or inferred facts only",
                    "similarCases": "advisory-only Options Ledger memory",
                },
                "factors": [
                    "sanctioned node template",
                    "rule-store validation required",
                    "evidence-to-fact provenance required",
                    "human activation approval required",
                ],
            },
            "humanActivationApproval": {
                "required": True,
                "status": "pending",
                "approvalId": None,
                "approverRole": payload.get("activationApproverRole") or "workflow owner",
            },
        }
        return self._canonical_definition(workflow_id, definition)

    def _definition_with_generation_validation(
        self,
        definition: dict[str, Any],
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        updated = deepcopy(definition)
        metadata = deepcopy(updated.get("metadata") or {})
        generation = deepcopy(metadata.get("generation") or {})
        generation["validationResult"] = {
            "valid": validation["valid"],
            "severityCounts": deepcopy(validation["severityCounts"]),
            "diagnostics": deepcopy(validation["diagnostics"]),
            "ruleBindings": deepcopy(validation["ruleBindings"]),
            "graphHash": validation["graphHash"],
        }
        metadata["generation"] = generation
        updated["metadata"] = metadata
        return updated

    def _activation_requirement(self, definition: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        if not validation["valid"]:
            return {
                "blocksActivation": True,
                "approvalRequired": self._is_generated_definition(definition),
                "reason": "Workflow validation must pass before activation.",
                "approval": self._generated_activation_approval(definition),
                "validation": {"valid": False, "severityCounts": validation["severityCounts"]},
            }
        if not self._is_generated_definition(definition):
            return {
                "blocksActivation": False,
                "approvalRequired": False,
                "reason": "Manual workflow definition does not require generated-draft activation approval.",
                "approval": {"required": False, "status": "not_required"},
                "validation": {"valid": True, "severityCounts": validation["severityCounts"]},
            }

        approval = self._generated_activation_approval(definition)
        if approval.get("status") != "approved":
            return {
                "blocksActivation": True,
                "approvalRequired": True,
                "reason": "Generated workflow requires approved human activation approval.",
                "approval": approval,
                "validation": {"valid": True, "severityCounts": validation["severityCounts"]},
            }
        return {
            "blocksActivation": False,
            "approvalRequired": True,
            "reason": "Generated workflow validation and human activation approval are satisfied.",
            "approval": approval,
            "validation": {"valid": True, "severityCounts": validation["severityCounts"]},
        }

    @staticmethod
    def _is_generated_definition(definition: dict[str, Any]) -> bool:
        generation = _normalise_dict(_normalise_dict(definition.get("metadata")).get("generation"))
        return bool(generation.get("generatedDraft")) or generation.get("source") == "deterministic-template"

    @staticmethod
    def _generated_activation_approval(definition: dict[str, Any]) -> dict[str, Any]:
        generation = _normalise_dict(_normalise_dict(definition.get("metadata")).get("generation"))
        approval = _normalise_dict(generation.get("humanActivationApproval"))
        approval.setdefault("required", bool(generation))
        approval.setdefault("status", "pending" if generation else "not_required")
        return approval

    @staticmethod
    def _change_set(base_definition: dict[str, Any], draft_definition: dict[str, Any]) -> dict[str, Any]:
        base_nodes = {
            str(node.get("id")): node
            for node in _normalise_list(base_definition.get("nodes"))
            if isinstance(node, dict) and node.get("id")
        }
        draft_nodes = {
            str(node.get("id")): node
            for node in _normalise_list(draft_definition.get("nodes"))
            if isinstance(node, dict) and node.get("id")
        }
        base_transitions = {
            stable_hash(transition): transition
            for transition in _normalise_list(base_definition.get("transitions"))
            if isinstance(transition, dict)
        }
        draft_transitions = {
            stable_hash(transition): transition
            for transition in _normalise_list(draft_definition.get("transitions"))
            if isinstance(transition, dict)
        }
        return {
            "addedNodeIds": sorted(set(draft_nodes) - set(base_nodes)),
            "removedNodeIds": sorted(set(base_nodes) - set(draft_nodes)),
            "modifiedNodeIds": sorted(
                node_id
                for node_id in set(base_nodes) & set(draft_nodes)
                if stable_hash(base_nodes[node_id]) != stable_hash(draft_nodes[node_id])
            ),
            "addedTransitions": [
                draft_transitions[key] for key in sorted(set(draft_transitions) - set(base_transitions))
            ],
            "removedTransitions": [
                base_transitions[key] for key in sorted(set(base_transitions) - set(draft_transitions))
            ],
        }

    def _workflow_response(self, definition: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(version["definition"])
        payload.update(
            {
                "status": definition["status"],
                "currentVersionId": definition["currentVersionId"],
                "currentVersionHash": definition["currentVersionHash"],
                "version": definition["version"],
                "graphHash": definition["graphHash"],
                "validation": version["validation"],
                "compileOutput": version["compileOutput"],
                "createdAt": definition["createdAt"],
                "updatedAt": definition["updatedAt"],
            }
        )
        return payload

    def _definition_status(self, definition: dict[str, Any], validation: dict[str, Any]) -> str:
        if self._is_generated_definition(definition) and validation["valid"]:
            return "generated_draft"
        return "validated" if validation["valid"] else "invalid"

    def _validate_node_contract(self, node: dict[str, Any], diagnostics: list[dict[str, Any]]) -> None:
        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        if node_type not in SANCTIONED_NODE_TYPES:
            diagnostics.append(
                self._diagnostic(
                    "UNSANCTIONED_NODE_TYPE",
                    "error",
                    f"Node type '{node_type or '<missing>'}' is not sanctioned for AEGIS authoring.",
                    node_id=node_id or None,
                    field="type",
                )
            )
            return

        for field_name in sorted(COMMON_REQUIRED_FIELDS | NODE_REQUIRED_FIELDS.get(node_type, set())):
            if not _has_required_field(node, field_name) and not _has_required_field(
                node,
                f"policyBinding.{field_name}",
            ):
                diagnostics.append(
                    self._diagnostic(
                        "MISSING_REQUIRED_PROOF_FIELD",
                        "error",
                        f"{node_type} node is missing required proof field '{field_name}'.",
                        node_id=node_id or None,
                        field=field_name,
                    )
                )
        for field_name in sorted(COMMON_REQUIRED_NESTED_FIELDS):
            if not _has_value(node, field_name):
                diagnostics.append(
                    self._diagnostic(
                        "MISSING_REQUIRED_PROOF_FIELD",
                        "error",
                        f"{node_type} node is missing required proof field '{field_name}'.",
                        node_id=node_id or None,
                        field=field_name,
                    )
                )

        if node_type == "OPTION_SET":
            self._validate_options(node, diagnostics)

    def _validate_options(self, node: dict[str, Any], diagnostics: list[dict[str, Any]]) -> None:
        node_id = str(node.get("id") or "")
        options = _normalise_list(node.get("options"))
        if not options:
            return
        required = {
            "id",
            "label",
            "status",
            "confidence",
            "risk",
            "supportingEvidenceRefs",
            "opposingEvidenceRefs",
            "constraints",
            "rationale",
            "requiredRole",
            "requiresApproval",
            "wouldTriggerNodeId",
            "fallbackIfRejected",
        }
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                diagnostics.append(
                    self._diagnostic(
                        "INVALID_OPTION",
                        "error",
                        "Workflow option payload must be an object.",
                        node_id=node_id,
                        field=f"options[{index}]",
                    )
                )
                continue
            for field_name in sorted(required):
                if not _has_required_field(option, field_name):
                    diagnostics.append(
                        self._diagnostic(
                            "MISSING_OPTION_PROOF_FIELD",
                            "error",
                            f"Option is missing required proof field '{field_name}'.",
                            node_id=node_id,
                            field=f"options[{index}].{field_name}",
                        )
                    )

    def _validate_transitions(
        self,
        transitions: list[Any],
        node_by_id: dict[str, dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        for index, transition in enumerate(transitions):
            if not isinstance(transition, dict):
                diagnostics.append(
                    self._diagnostic(
                        "INVALID_TRANSITION",
                        "error",
                        "Transition payload must be an object.",
                        field=f"transitions[{index}]",
                    )
                )
                continue
            from_id = str(transition.get("fromNodeId") or transition.get("from") or "")
            to_id = str(transition.get("toNodeId") or transition.get("to") or "")
            from_node = node_by_id.get(from_id)
            to_node = node_by_id.get(to_id)
            if from_node is None:
                diagnostics.append(
                    self._diagnostic(
                        "UNKNOWN_TRANSITION_SOURCE",
                        "error",
                        f"Transition source '{from_id}' does not exist.",
                        node_id=from_id or None,
                        field=f"transitions[{index}].fromNodeId",
                    )
                )
            if to_node is None:
                diagnostics.append(
                    self._diagnostic(
                        "UNKNOWN_TRANSITION_TARGET",
                        "error",
                        f"Transition target '{to_id}' does not exist.",
                        node_id=to_id or None,
                        field=f"transitions[{index}].toNodeId",
                    )
                )
            if from_node is None or to_node is None:
                continue
            from_type = str(from_node.get("type") or "")
            to_type = str(to_node.get("type") or "")
            if to_type not in ALLOWED_TRANSITIONS.get(from_type, set()):
                diagnostics.append(
                    self._diagnostic(
                        "INVALID_TRANSITION",
                        "error",
                        f"Transition from {from_type} to {to_type} is not allowed.",
                        node_id=from_id,
                        field=f"transitions[{index}]",
                    )
                )

    def _validate_reachability(
        self,
        nodes: list[Any],
        transitions: list[Any],
        node_by_id: dict[str, dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        request_nodes = [
            str(node.get("id"))
            for node in nodes
            if isinstance(node, dict) and node.get("type") == "REQUEST" and node.get("id")
        ]
        receipt_nodes = {
            str(node.get("id"))
            for node in nodes
            if isinstance(node, dict) and node.get("type") == "RECEIPT_SEAL" and node.get("id")
        }
        if not request_nodes:
            diagnostics.append(
                self._diagnostic(
                    "MISSING_START_NODE",
                    "error",
                    "Workflow requires a REQUEST start node.",
                    field="nodes",
                )
            )
            return
        if not receipt_nodes:
            diagnostics.append(
                self._diagnostic(
                    "MISSING_RECEIPT_NODE",
                    "error",
                    "Workflow requires a RECEIPT_SEAL node before activation.",
                    receipt_requirement="RECEIPT_SEAL",
                )
            )
            return

        adjacency: dict[str, list[str]] = {}
        for transition in transitions:
            if not isinstance(transition, dict):
                continue
            from_id = str(transition.get("fromNodeId") or transition.get("from") or "")
            to_id = str(transition.get("toNodeId") or transition.get("to") or "")
            if from_id in node_by_id and to_id in node_by_id:
                adjacency.setdefault(from_id, []).append(to_id)

        seen: set[str] = set()
        queue = deque(request_nodes)
        while queue:
            node_id = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)
            queue.extend(adjacency.get(node_id, []))

        unreachable_receipts = receipt_nodes - seen
        for node_id in sorted(unreachable_receipts):
            diagnostics.append(
                self._diagnostic(
                    "UNREACHABLE_REQUIRED_RECEIPT",
                    "error",
                    f"Receipt node '{node_id}' is not reachable from a REQUEST node.",
                    node_id=node_id,
                    receipt_requirement="RECEIPT_SEAL",
                )
            )

    def _validate_evidence_contract(
        self,
        definition: dict[str, Any],
        nodes: list[Any],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        evidence_ids = {
            str(item.get("id"))
            for item in _normalise_list(definition.get("evidence"))
            if isinstance(item, dict) and item.get("id")
        }
        produced_refs = {
            str(ref)
            for node in nodes
            if isinstance(node, dict)
            for ref in _normalise_list(node.get("producedEvidenceRefs"))
        }
        available_refs = evidence_ids | produced_refs
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "")
            for ref in _normalise_list(node.get("requiredEvidenceRefs")):
                if str(ref) not in available_refs:
                    diagnostics.append(
                        self._diagnostic(
                            "UNRESOLVED_EVIDENCE_REF",
                            "error",
                            f"Required evidence ref '{ref}' is not present or produced by any node.",
                            node_id=node_id,
                            field="requiredEvidenceRefs",
                            evidence_ref=str(ref),
                        )
                    )

    def _validate_rule_bindings(
        self,
        nodes: list[Any],
        diagnostics: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict) or node.get("type") != "RULE_GATE":
                continue
            node_id = str(node.get("id") or "")
            rule_name = str(_node_field(node, "ruleName") or "")
            target_node_name = str(_node_field(node, "targetNodeName") or "")
            if not rule_name or self._rule_service is None:
                continue
            try:
                latest_file = self._rule_service.get_latest_rule_file(rule_name)
                rule_text = self._rule_service.decode_rule_file(latest_file)
                integrity = build_policy_integrity(self._rule_service, rule_name, rule_text, latest_file.file_id)
                target_node_names = self._rule_service.get_target_node_names(rule_name)
            except LookupError:
                diagnostics.append(
                    self._diagnostic(
                        "RULE_NOT_FOUND",
                        "error",
                        f"Rule '{rule_name}' was not found in the AEGIS rule store.",
                        node_id=node_id,
                        field="ruleName",
                        rule_name=rule_name,
                    )
                )
                continue

            binding = {
                "nodeId": node_id,
                "ruleName": rule_name,
                "targetNodeName": target_node_name,
                "targetNodeNames": target_node_names,
                "product": AEGIS_PRODUCT,
                "store": AEGIS_RULE_STORE,
                "ruleVersionHash": integrity["ruleVersionHash"],
                "importTreeHash": integrity["importTreeHash"],
                "validationStatus": integrity["validationStatus"],
                "missingImports": integrity["missingImports"],
                "hasImportCycles": integrity["hasImportCycles"],
                "latestFileId": integrity["latestFileId"],
            }
            bindings.append(binding)

            if integrity["validationStatus"] != "valid":
                diagnostics.append(
                    self._diagnostic(
                        "INVALID_RULE_BINDING",
                        "error",
                        f"Rule '{rule_name}' does not validate.",
                        node_id=node_id,
                        field="ruleName",
                        rule_name=rule_name,
                    )
                )
            for missing in integrity["missingImports"]:
                diagnostics.append(
                    self._diagnostic(
                        "UNRESOLVED_IMPORT",
                        "error",
                        f"Imported rule '{missing}' is missing from the AEGIS rule store.",
                        node_id=node_id,
                        field="ruleName",
                        rule_name=rule_name,
                        import_name=missing,
                    )
                )
            if integrity["hasImportCycles"]:
                diagnostics.append(
                    self._diagnostic(
                        "CIRCULAR_IMPORT",
                        "error",
                        f"Rule '{rule_name}' import tree contains a cycle.",
                        node_id=node_id,
                        field="ruleName",
                        rule_name=rule_name,
                    )
                )
            if target_node_name and target_node_name not in target_node_names:
                diagnostics.append(
                    self._diagnostic(
                        "INVALID_RULE_TARGET",
                        "error",
                        f"Rule target '{target_node_name}' is not exported by '{rule_name}'.",
                        node_id=node_id,
                        field="targetNodeName",
                        rule_name=rule_name,
                    )
                )
        return bindings

    def _evidence_contract(self, definition: dict[str, Any]) -> dict[str, Any]:
        nodes = _normalise_list(definition.get("nodes"))
        required = sorted(
            {
                str(ref)
                for node in nodes
                if isinstance(node, dict)
                for ref in _normalise_list(node.get("requiredEvidenceRefs"))
            }
        )
        produced = sorted(
            {
                str(ref)
                for node in nodes
                if isinstance(node, dict)
                for ref in _normalise_list(node.get("producedEvidenceRefs"))
            }
        )
        evidence_ids = sorted(
            {
                str(evidence.get("id"))
                for evidence in _normalise_list(definition.get("evidence"))
                if isinstance(evidence, dict) and evidence.get("id")
            }
        )
        return {
            "requiredEvidenceRefs": required,
            "producedEvidenceRefs": produced,
            "providedEvidenceRefs": evidence_ids,
        }

    def _fact_ingestion_contract(self, definition: dict[str, Any]) -> dict[str, Any]:
        fact_nodes = [
            node
            for node in _normalise_list(definition.get("nodes"))
            if isinstance(node, dict) and node.get("type") == "FACT_EXTRACTION"
        ]
        produced_fact_refs = sorted(
            {
                str(ref)
                for node in fact_nodes
                for ref in _normalise_list(node.get("producedFactRefs"))
            }
        )
        input_evidence_refs = sorted(
            {
                str(ref)
                for node in fact_nodes
                for ref in _normalise_list(node.get("inputEvidenceRefs"))
            }
        )
        return {
            "contract": "aegis-evidence-fact-ledger-v1",
            "nodeIds": [str(node["id"]) for node in fact_nodes if node.get("id")],
            "inputEvidenceRefs": input_evidence_refs,
            "producedFactRefs": produced_fact_refs,
            "authoritativeFactClasses": ["asserted", "inferred"],
            "advisoryOnlyClasses": ["advisory", "learned", "retrieval_advisory", "similar_case_advisory"],
            "authoritativeRuleBoundary": (
                "Generated workflows must use provenance-backed extracted facts for rule gates; "
                "similar-case memory is only advisory."
            ),
        }

    def _confidence_explanation(self, definition: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        generation = _normalise_dict(_normalise_dict(definition.get("metadata")).get("generation"))
        confidence = _normalise_dict(generation.get("confidence"))
        return {
            "score": confidence.get("score"),
            "calibration": confidence.get("calibration"),
            "factors": deepcopy(confidence.get("factors") or []),
            "validationSeverityCounts": deepcopy(validation.get("severityCounts") or {}),
            "authorityBoundary": deepcopy(confidence.get("authorityBoundary") or {}),
            "explainabilityLimit": (
                "Confidence explains deterministic template coverage and validation status; it does not "
                "make retrieved or advisory facts authoritative."
            ),
        }

    def _receipt_requirements(self, definition: dict[str, Any]) -> dict[str, Any]:
        receipt_nodes = [
            node
            for node in _normalise_list(definition.get("nodes"))
            if isinstance(node, dict) and node.get("type") == "RECEIPT_SEAL"
        ]
        return {
            "nodeIds": [node["id"] for node in receipt_nodes if node.get("id")],
            "policy": deepcopy(definition.get("receiptPolicy") or {}),
        }

    @staticmethod
    def _duplicate_node_ids(nodes: list[Any]) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for node in nodes:
            if not isinstance(node, dict) or not node.get("id"):
                continue
            node_id = str(node["id"])
            if node_id in seen:
                duplicates.add(node_id)
            seen.add(node_id)
        return duplicates

    @staticmethod
    def _diagnostic(
        code: str,
        severity: str,
        message: str,
        *,
        node_id: str | None = None,
        field: str | None = None,
        rule_name: str | None = None,
        import_name: str | None = None,
        evidence_ref: str | None = None,
        receipt_requirement: str | None = None,
    ) -> dict[str, Any]:
        blocks_save_version = severity == "error"
        blocks_compile = severity == "error"
        diagnostic = {
            "code": code,
            "severity": severity,
            "message": message,
            "nodeId": node_id,
            "field": field,
            "ruleName": rule_name,
            "importName": import_name,
            "evidenceRef": evidence_ref,
            "receiptRequirement": receipt_requirement,
            "blocksSaveVersion": blocks_save_version,
            "blocksCompile": blocks_compile,
        }
        return {key: value for key, value in diagnostic.items() if value is not None}
