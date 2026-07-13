"""AEGIS-scoped rule-store API routes."""

from copy import deepcopy
import re
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.adapters.inbound.http.dependencies import get_aegis_db_session, require_scope
from src.adapters.inbound.http.schemas.validation import (
    RuleValidateResponse,
    ValidationEntryDetail,
)
from src.adapters.inbound.http.schemas.rules import RuleGraphResponse
from src.adapters.outbound.persistence.aegis_rule_repository import AegisRuleRepositoryImpl
from src.adapters.outbound.persistence.aegis_workflow_repository import AegisWorkflowRepository
from src.domain.aegis.rule_store import (
    AEGIS_PRODUCT,
    AEGIS_RULE_STORE,
    build_import_tree,
    build_policy_integrity,
    rule_version_hash,
    validation_status,
)
from src.domain.aegis.workflow_authoring import AegisWorkflowAuthoringService
from src.services.rule_service import RuleService
from src.services.rule_validation_service import ValidationResult

router = APIRouter(prefix="/api/v1/aegis/rules", tags=["aegis-rules"])


class AegisStoreError(BaseModel):
    code: str
    message: str
    ruleName: str | None = None
    store: str = AEGIS_RULE_STORE


class AegisRuleSummaryResponse(BaseModel):
    rule_id: int | None = None
    name: str | None = None
    category: str | None = None
    description: str | None = None
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    latest_file_id: int | None = None
    ruleVersionHash: str | None = None
    importTreeHash: str | None = None
    validationStatus: str = "unknown"
    targetNodeName: str | None = None
    errors: list[AegisStoreError] = Field(default_factory=list)


class AegisRuleDetailResponse(AegisRuleSummaryResponse):
    ruleText: str


class SaveAegisRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field("", max_length=255)
    description: str = Field("", max_length=2000)
    ruleText: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None
    requireWorkflowImpactPass: bool = False
    createOnly: bool = False
    targetNodeName: str | None = Field(None, max_length=255)


class UpdateAegisRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field("", max_length=255)
    description: str = Field("", max_length=2000)
    ruleText: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None
    requireWorkflowImpactPass: bool = False
    targetNodeName: str | None = Field(None, max_length=255)


class AegisRuleVersionCreateRequest(BaseModel):
    ruleText: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None
    requireWorkflowImpactPass: bool = False


class AegisRuleCreatedResponse(BaseModel):
    ruleName: str | None = None
    category: str | None = None
    description: str | None = None
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    latest_file_id: int | None = None
    ruleVersionHash: str | None = None
    importTreeHash: str | None = None
    validationStatus: str = "unknown"
    targetNodeName: str | None = None


class AegisRuleWorkflowRenameUpdate(BaseModel):
    workflowId: str
    title: str
    versionId: str
    versionHash: str
    nodeIds: list[str] = Field(default_factory=list)
    nodeLabels: list[str] = Field(default_factory=list)


class AegisRuleImportRenameUpdate(BaseModel):
    ruleName: str
    latest_file_id: int | None = None
    ruleVersionHash: str | None = None
    importTreeHash: str | None = None


class AegisRuleUpdateResponse(AegisRuleCreatedResponse):
    previousRuleName: str | None = None
    updatedWorkflowReferences: list[AegisRuleWorkflowRenameUpdate] = Field(default_factory=list)
    updatedRuleImports: list[AegisRuleImportRenameUpdate] = Field(default_factory=list)


class AegisRuleTextResponse(BaseModel):
    ruleText: str
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    ruleName: str
    latest_file_id: int | None = None
    ruleVersionHash: str | None = None
    importTreeHash: str | None = None
    validationStatus: str = "unknown"


class AegisRuleValidateRequest(BaseModel):
    rule_text: str = Field(..., max_length=1_000_000)
    rule_name: str | None = Field(None, max_length=255)


class AegisRuleGraphPreviewRequest(BaseModel):
    ruleText: str = Field(..., min_length=1, max_length=1_000_000)
    ruleName: str | None = Field(None, max_length=255)


class AegisRuleGraphResponse(RuleGraphResponse):
    targetNodeNames: list[str] = Field(default_factory=list)
    selectedTargetNodeName: str | None = None


class UpdateAegisRuleTargetRequest(BaseModel):
    targetNodeName: str = Field(..., min_length=1, max_length=255)
    requireWorkflowImpactPass: bool = False


class AegisImportEntry(BaseModel):
    name: str
    content_hash: str
    node_count: int
    depth: int
    direct_imports: list[str] = Field(default_factory=list)


class AegisImportTreeResponse(BaseModel):
    ruleName: str
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    imports: list[AegisImportEntry]
    missing: list[str] = Field(default_factory=list)
    has_cycles: bool
    total_count: int
    offset: int
    limit: int
    importTreeHash: str
    errors: list[AegisStoreError] = Field(default_factory=list)


class AegisRuleVersionResponse(BaseModel):
    ruleName: str
    ruleText: str
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    latest_file_id: int | None = None
    ruleVersionHash: str | None = None
    importTreeHash: str | None = None
    validationStatus: str = "unknown"


class AegisRuleWorkflowReference(BaseModel):
    workflowId: str
    title: str
    domain: str
    status: str
    currentVersionId: str | None = None
    currentVersionHash: str | None = None
    bindingType: str
    boundRuleNames: list[str] = Field(default_factory=list)
    nodeIds: list[str] = Field(default_factory=list)
    nodeLabels: list[str] = Field(default_factory=list)
    targetNodeNames: list[str] = Field(default_factory=list)


class AegisRuleWorkflowUsageSummary(BaseModel):
    directWorkflowDefinitions: int
    indirectWorkflowDefinitions: int
    workflowRuns: int


class AegisRuleWorkflowUsageResponse(BaseModel):
    ruleName: str
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    directWorkflowDefinitions: list[AegisRuleWorkflowReference] = Field(default_factory=list)
    indirectWorkflowDefinitions: list[AegisRuleWorkflowReference] = Field(default_factory=list)
    workflowRuns: list[dict[str, Any]] = Field(default_factory=list)
    runUsageAvailable: bool = False
    summary: AegisRuleWorkflowUsageSummary


class AegisRuleWorkflowImpactTestRequest(BaseModel):
    ruleText: str = Field(..., min_length=1, max_length=1_000_000)
    workflowIds: list[str] | None = None
    targetNodeName: str | None = Field(None, max_length=255)


class AegisRuleWorkflowImpactDiagnostic(BaseModel):
    code: str
    severity: str
    message: str
    workflowId: str | None = None
    nodeId: str | None = None
    field: str | None = None
    ruleName: str | None = None


class AegisRuleWorkflowImpactTestRow(BaseModel):
    workflowId: str
    title: str
    bindingType: str
    status: str
    nodeIds: list[str] = Field(default_factory=list)
    diagnostics: list[AegisRuleWorkflowImpactDiagnostic] = Field(default_factory=list)


class AegisRuleWorkflowImpactTestResponse(BaseModel):
    ruleName: str
    product: str = AEGIS_PRODUCT
    store: str = AEGIS_RULE_STORE
    passed: bool
    draftRuleVersionHash: str
    draftImportTreeHash: str | None = None
    draftValidationStatus: str
    targetNodes: list[str] = Field(default_factory=list)
    diagnostics: list[AegisRuleWorkflowImpactDiagnostic] = Field(default_factory=list)
    tests: list[AegisRuleWorkflowImpactTestRow] = Field(default_factory=list)
    usage: AegisRuleWorkflowUsageResponse


class AegisRuleTargetUpdateResponse(BaseModel):
    ruleName: str
    targetNodeName: str
    targetNodeNames: list[str] = Field(default_factory=list)
    impact: AegisRuleWorkflowImpactTestResponse | None = None


def _service(db: Session) -> RuleService:
    return RuleService(AegisRuleRepositoryImpl(db))


def _validation_response(result: ValidationResult) -> RuleValidateResponse:
    return RuleValidateResponse(
        valid=result.valid,
        errors=[
            ValidationEntryDetail(
                code=error.code,
                message=error.message,
                waiver_id=error.waiver_id,
                line=error.line,
                node_name=error.node_name,
            )
            for error in result.errors
        ],
        warnings=[
            ValidationEntryDetail(
                code=warning.code,
                message=warning.message,
                waiver_id=warning.waiver_id,
                line=warning.line,
                node_name=warning.node_name,
            )
            for warning in result.warnings
        ],
    )


def _integrity_errors(integrity: dict[str, Any]) -> list[AegisStoreError]:
    errors: list[AegisStoreError] = []
    for missing in integrity.get("missingImports", []):
        errors.append(
            AegisStoreError(
                code="UNRESOLVED_IMPORT",
                message=f"Imported rule '{missing}' is missing from the AEGIS rule store",
                ruleName=missing,
            )
        )
    if integrity.get("hasImportCycles"):
        errors.append(
            AegisStoreError(
                code="CIRCULAR_IMPORT",
                message="AEGIS import tree contains a cycle",
            )
        )
    return errors


def _summary(service: RuleService, rule: Any) -> AegisRuleSummaryResponse:
    rule_id = rule.get("rule_id") if isinstance(rule, dict) else rule.rule_id
    name = rule.get("name") if isinstance(rule, dict) else rule.name
    category = rule.get("category") if isinstance(rule, dict) else rule.category
    description = rule.get("description") if isinstance(rule, dict) else rule.description
    target_node_name = _rule_target_node_name(rule)
    response = AegisRuleSummaryResponse(
        rule_id=rule_id,
        name=name,
        category=category,
        description=description,
        targetNodeName=target_node_name,
    )
    if not name:
        return response
    try:
        latest_file = service.get_latest_rule_file(name)
        rule_text = service.decode_rule_file(latest_file)
        integrity = build_policy_integrity(service, name, rule_text, latest_file.file_id)
        response.latest_file_id = latest_file.file_id
        response.ruleVersionHash = integrity["ruleVersionHash"]
        response.importTreeHash = integrity["importTreeHash"]
        response.validationStatus = integrity["validationStatus"]
        response.errors = _integrity_errors(integrity)
    except LookupError:
        response.errors = [
            AegisStoreError(
                code="MISSING_RULE_FILE",
                message=f"Rule '{name}' has no latest AEGIS rule file",
                ruleName=name,
            )
        ]
    return response


def _detail(service: RuleService, rule_name: str) -> AegisRuleDetailResponse:
    rule = service.get_rule_by_name(rule_name)
    latest_file = service.get_latest_rule_file(rule_name)
    rule_text = service.decode_rule_file(latest_file)
    integrity = build_policy_integrity(service, rule_name, rule_text, latest_file.file_id)
    return AegisRuleDetailResponse(
        rule_id=rule.rule_id,
        name=rule.name,
        category=rule.category,
        description=rule.description,
        targetNodeName=rule.target_node_name,
        ruleText=rule_text,
        latest_file_id=latest_file.file_id,
        ruleVersionHash=integrity["ruleVersionHash"],
        importTreeHash=integrity["importTreeHash"],
        validationStatus=integrity["validationStatus"],
        errors=_integrity_errors(integrity),
    )


def _rule_target_node_name(rule: Any) -> str | None:
    if isinstance(rule, dict):
        value = rule.get("targetNodeName")
        if value is None:
            value = rule.get("target_node_name")
    else:
        value = getattr(rule, "target_node_name", None)
    normalized = str(value or "").strip()
    return normalized or None


def _target_payload_value(target_node_name: str | None) -> str | None:
    normalized = str(target_node_name or "").strip()
    return normalized or None


def _validate_selected_target(
    service: RuleService,
    rule_name: str,
    rule_text: str,
    target_node_name: str | None,
) -> list[str]:
    target_nodes = service.get_target_node_names_for_text(rule_name, rule_text)
    graph_nodes = service.get_node_names_for_text(rule_name, rule_text)
    normalized = _target_payload_value(target_node_name)
    if normalized and normalized not in graph_nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_RULE_TARGET",
                "message": f"Target node '{normalized}' does not exist in rule set '{rule_name}'.",
                "ruleName": rule_name,
                "targetNodeName": normalized,
                "graphNodeNames": graph_nodes,
                "targetNodeNames": target_nodes,
            },
        )
    return target_nodes


def _workflow_reference_count(usage: AegisRuleWorkflowUsageResponse) -> int:
    return len(usage.directWorkflowDefinitions) + len(usage.indirectWorkflowDefinitions)


def _node_policy_binding(node: dict[str, Any]) -> dict[str, Any]:
    binding = node.get("policyBinding")
    return binding if isinstance(binding, dict) else {}


def _node_field(node: dict[str, Any], key: str) -> Any:
    value = node.get(key)
    if value not in (None, ""):
        return value
    return _node_policy_binding(node).get(key)


def _node_rule_name(node: dict[str, Any]) -> str:
    return str(
        _node_field(node, "ruleName")
        or _node_field(node, "policyRuleName")
        or _node_field(node, "ruleSetName")
        or _node_field(node, "ruleRef")
        or ""
    ).strip()


def _node_target_name(node: dict[str, Any]) -> str:
    return str(_node_field(node, "targetNodeName") or _node_field(node, "target") or "").strip()


def _workflow_versions(db: Session) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    repository = AegisWorkflowRepository(db)
    versions: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for definition in repository.list_definitions():
        workflow_id = str(definition.get("id") or "")
        if not workflow_id:
            continue
        latest = repository.get_latest_version(workflow_id)
        if latest is None:
            continue
        payload = latest.get("definition")
        if isinstance(payload, dict):
            versions.append((definition, latest, payload))
    return versions


def _import_names_for_rule(service: RuleService, rule_name: str) -> set[str]:
    if not rule_name:
        return set()
    try:
        rule_text = service.get_rule_text(rule_name)
        tree = build_import_tree(service, rule_name, rule_text)
    except Exception:
        return set()
    return {entry.name for entry in tree.imports}


def _workflow_reference(
    definition: dict[str, Any],
    version: dict[str, Any],
    binding_type: str,
    nodes: list[dict[str, Any]],
) -> AegisRuleWorkflowReference:
    return AegisRuleWorkflowReference(
        workflowId=str(definition.get("id") or version.get("workflowId") or ""),
        title=str(definition.get("title") or version.get("workflowId") or ""),
        domain=str(definition.get("domain") or "general"),
        status=str(definition.get("status") or version.get("status") or "unknown"),
        currentVersionId=definition.get("currentVersionId") or version.get("versionId"),
        currentVersionHash=definition.get("currentVersionHash") or version.get("versionHash"),
        bindingType=binding_type,
        boundRuleNames=sorted({_node_rule_name(node) for node in nodes if _node_rule_name(node)}),
        nodeIds=[str(node.get("id") or "") for node in nodes if node.get("id")],
        nodeLabels=[str(node.get("label") or node.get("id") or "") for node in nodes],
        targetNodeNames=sorted({_node_target_name(node) for node in nodes if _node_target_name(node)}),
    )


def _build_workflow_usage(
    service: RuleService,
    db: Session,
    rule_name: str,
) -> AegisRuleWorkflowUsageResponse:
    service.get_rule_by_name(rule_name)
    import_cache: dict[str, set[str]] = {}
    direct: list[AegisRuleWorkflowReference] = []
    indirect: list[AegisRuleWorkflowReference] = []

    for definition, version, payload in _workflow_versions(db):
        direct_nodes: list[dict[str, Any]] = []
        indirect_nodes: list[dict[str, Any]] = []
        for node in payload.get("nodes") or []:
            if not isinstance(node, dict) or node.get("type") != "RULE_GATE":
                continue
            bound_rule_name = _node_rule_name(node)
            if not bound_rule_name:
                continue
            if bound_rule_name == rule_name:
                direct_nodes.append(node)
                continue
            if bound_rule_name not in import_cache:
                import_cache[bound_rule_name] = _import_names_for_rule(service, bound_rule_name)
            if rule_name in import_cache[bound_rule_name]:
                indirect_nodes.append(node)

        if direct_nodes:
            direct.append(_workflow_reference(definition, version, "direct", direct_nodes))
        if indirect_nodes:
            indirect.append(_workflow_reference(definition, version, "indirect", indirect_nodes))

    return AegisRuleWorkflowUsageResponse(
        ruleName=rule_name,
        directWorkflowDefinitions=direct,
        indirectWorkflowDefinitions=indirect,
        workflowRuns=[],
        runUsageAvailable=False,
        summary=AegisRuleWorkflowUsageSummary(
            directWorkflowDefinitions=len(direct),
            indirectWorkflowDefinitions=len(indirect),
            workflowRuns=0,
        ),
    )


def _impact_diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    workflow_id: str | None = None,
    node_id: str | None = None,
    field: str | None = None,
    rule_name: str | None = None,
) -> AegisRuleWorkflowImpactDiagnostic:
    return AegisRuleWorkflowImpactDiagnostic(
        code=code,
        severity=severity,
        message=message,
        workflowId=workflow_id,
        nodeId=node_id,
        field=field,
        ruleName=rule_name,
    )


def _build_workflow_impact_test(
    service: RuleService,
    db: Session,
    rule_name: str,
    rule_text: str,
    workflow_ids: list[str] | None = None,
    target_node_name: str | None = None,
) -> AegisRuleWorkflowImpactTestResponse:
    usage = _build_workflow_usage(service, db, rule_name)
    allowed_workflow_ids = {workflow_id for workflow_id in workflow_ids or [] if workflow_id}
    selected_refs = [
        ref
        for ref in [*usage.directWorkflowDefinitions, *usage.indirectWorkflowDefinitions]
        if not allowed_workflow_ids or ref.workflowId in allowed_workflow_ids
    ]
    diagnostics: list[AegisRuleWorkflowImpactDiagnostic] = []
    validation = service.validate_draft_rule(rule_text=rule_text, rule_name=rule_name)
    draft_import_tree_hash: str | None = None
    missing_imports: list[str] = []
    has_import_cycles = False
    target_nodes: list[str] = []
    selected_target_node = _target_payload_value(target_node_name)

    try:
        import_tree = build_import_tree(service, rule_name, rule_text)
        draft_import_tree_hash = import_tree.import_tree_hash
        missing_imports = import_tree.missing
        has_import_cycles = import_tree.has_cycles
    except Exception as exc:
        diagnostics.append(
            _impact_diagnostic(
                "IMPORT_TREE_FAILED",
                "error",
                f"Draft import tree could not be evaluated: {exc}",
                rule_name=rule_name,
            )
        )

    try:
        target_nodes = service.get_target_node_names_for_text(rule_name, rule_text)
        graph_nodes = service.get_node_names_for_text(rule_name, rule_text)
        if selected_target_node and selected_target_node not in graph_nodes:
            diagnostics.append(
                _impact_diagnostic(
                    "INVALID_SELECTED_TARGET",
                    "error",
                    f"Selected target node '{selected_target_node}' does not exist in the draft rule graph.",
                    field="targetNodeName",
                    rule_name=rule_name,
                )
            )
    except Exception as exc:
        diagnostics.append(
            _impact_diagnostic(
                "TARGET_EXTRACTION_FAILED",
                "error",
                f"Draft target nodes could not be extracted: {exc}",
                rule_name=rule_name,
            )
        )

    if not validation.valid:
        diagnostics.extend(
            _impact_diagnostic(
                error.code,
                "error",
                error.message,
                field=f"line:{error.line}" if error.line else None,
                rule_name=rule_name,
            )
            for error in validation.errors
        )

    for missing in missing_imports:
        diagnostics.append(
            _impact_diagnostic(
                "UNRESOLVED_IMPORT",
                "error",
                f"Imported rule '{missing}' is missing from the AEGIS rule store.",
                rule_name=rule_name,
            )
        )
    if has_import_cycles:
        diagnostics.append(
            _impact_diagnostic(
                "CIRCULAR_IMPORT",
                "error",
                "Draft import tree contains a cycle.",
                rule_name=rule_name,
            )
        )

    tests: list[AegisRuleWorkflowImpactTestRow] = []
    for ref in selected_refs:
        row_diagnostics = [
            diagnostic for diagnostic in diagnostics if diagnostic.severity == "error"
        ]
        if ref.bindingType == "direct":
            for target_name in ref.targetNodeNames:
                if target_name and target_name not in target_nodes:
                    row_diagnostics.append(
                        _impact_diagnostic(
                            "INVALID_RULE_TARGET",
                            "error",
                            f"Workflow target '{target_name}' is not exported by the draft rule.",
                            workflow_id=ref.workflowId,
                            field="targetNodeName",
                            rule_name=rule_name,
                        )
                    )
        tests.append(
            AegisRuleWorkflowImpactTestRow(
                workflowId=ref.workflowId,
                title=ref.title,
                bindingType=ref.bindingType,
                status="failed" if row_diagnostics else "passed",
                nodeIds=ref.nodeIds,
                diagnostics=row_diagnostics,
            )
        )

    passed = not any(diagnostic.severity == "error" for diagnostic in diagnostics) and not any(
        test.status == "failed" for test in tests
    )
    return AegisRuleWorkflowImpactTestResponse(
        ruleName=rule_name,
        passed=passed,
        draftRuleVersionHash=rule_version_hash(rule_text),
        draftImportTreeHash=draft_import_tree_hash,
        draftValidationStatus=validation_status(validation),
        targetNodes=target_nodes,
        diagnostics=diagnostics,
        tests=tests,
        usage=usage,
    )


def _set_node_rule_name(node: dict[str, Any], old_rule_name: str, new_rule_name: str) -> bool:
    updated = False
    for key in ("ruleName", "policyRuleName", "ruleSetName", "ruleRef"):
        if str(node.get(key) or "").strip() == old_rule_name:
            node[key] = new_rule_name
            updated = True
    binding = node.get("policyBinding")
    if isinstance(binding, dict):
        for key in ("ruleName", "policyRuleName", "ruleSetName", "ruleRef"):
            if str(binding.get(key) or "").strip() == old_rule_name:
                binding[key] = new_rule_name
                updated = True
    return updated


def _rewrite_workflow_rule_references(
    db: Session,
    service: RuleService,
    old_rule_name: str,
    new_rule_name: str,
) -> list[AegisRuleWorkflowRenameUpdate]:
    if old_rule_name == new_rule_name:
        return []

    repository = AegisWorkflowRepository(db)
    authoring = AegisWorkflowAuthoringService(repository, service)
    updates: list[AegisRuleWorkflowRenameUpdate] = []
    for definition in repository.list_definitions():
        workflow_id = str(definition.get("id") or "")
        if not workflow_id:
            continue
        latest = repository.get_latest_version(workflow_id)
        if latest is None or not isinstance(latest.get("definition"), dict):
            continue

        payload = deepcopy(latest["definition"])
        updated_nodes: list[dict[str, Any]] = []
        for node in payload.get("nodes") or []:
            if not isinstance(node, dict) or node.get("type") != "RULE_GATE":
                continue
            if _set_node_rule_name(node, old_rule_name, new_rule_name):
                updated_nodes.append(node)

        if not updated_nodes:
            continue

        validation = authoring.validate_definition(payload)
        version = repository.append_version(
            workflow_id=workflow_id,
            version_id=f"wfv-{uuid4().hex}",
            definition_payload=payload,
            validation_snapshot=validation,
            version_hash=authoring.version_hash(payload),
            graph_hash=authoring.graph_hash(payload),
            status="validated" if validation["valid"] else "invalid",
            expected_version_hash=latest["versionHash"],
            created_by="aegis-rule-rename",
        )
        updates.append(
            AegisRuleWorkflowRenameUpdate(
                workflowId=workflow_id,
                title=str(definition.get("title") or workflow_id),
                versionId=str(version["versionId"]),
                versionHash=str(version["versionHash"]),
                nodeIds=[str(node.get("id") or "") for node in updated_nodes if node.get("id")],
                nodeLabels=[str(node.get("label") or node.get("id") or "") for node in updated_nodes],
            )
        )
    return updates


def _rewrite_direct_import_name(rule_text: str, old_rule_name: str, new_rule_name: str) -> str:
    pattern = re.compile(rf"^(IMPORT:\s*){re.escape(old_rule_name)}(\s*)$", re.MULTILINE)
    return pattern.sub(lambda match: f"{match.group(1)}{new_rule_name}{match.group(2)}", rule_text)


def _rewrite_rule_import_references(
    service: RuleService,
    old_rule_name: str,
    new_rule_name: str,
) -> list[AegisRuleImportRenameUpdate]:
    if old_rule_name == new_rule_name:
        return []

    updates: list[AegisRuleImportRenameUpdate] = []
    for rule in service.list_rules():
        importer_name = str(rule.get("name") or rule.get("rule_name") or "").strip()
        if not importer_name or importer_name == new_rule_name:
            continue
        try:
            rule_text = service.get_rule_text(importer_name)
        except Exception:
            continue
        rewritten = _rewrite_direct_import_name(rule_text, old_rule_name, new_rule_name)
        if rewritten == rule_text:
            continue
        service.create_rule_file(importer_name, rewritten)
        latest_file = service.get_latest_rule_file(importer_name)
        integrity = build_policy_integrity(service, importer_name, rewritten, latest_file.file_id)
        updates.append(
            AegisRuleImportRenameUpdate(
                ruleName=importer_name,
                latest_file_id=latest_file.file_id,
                ruleVersionHash=integrity["ruleVersionHash"],
                importTreeHash=integrity["importTreeHash"],
            )
        )
    return updates


def _raise_invalid_rule(rule_name: str, rule_text: str, service: RuleService) -> None:
    validation = service.validate_draft_rule(rule_text=rule_text, rule_name=rule_name)
    if validation.valid:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "message": "AEGIS rule syntax validation must pass before this rule set can be saved.",
            "validation": _validation_response(validation).model_dump(mode="json"),
        },
    )


def _created_response(
    service: RuleService,
    rule_name: str,
    *,
    previous_rule_name: str | None = None,
    updated_workflows: list[AegisRuleWorkflowRenameUpdate] | None = None,
    updated_imports: list[AegisRuleImportRenameUpdate] | None = None,
) -> AegisRuleUpdateResponse:
    rule = service.get_rule_by_name(rule_name)
    latest_file = service.get_latest_rule_file(rule_name)
    rule_text = service.decode_rule_file(latest_file)
    integrity = build_policy_integrity(service, rule_name, rule_text, latest_file.file_id)
    return AegisRuleUpdateResponse(
        ruleName=rule.name,
        category=rule.category,
        description=rule.description,
        targetNodeName=rule.target_node_name,
        latest_file_id=latest_file.file_id,
        ruleVersionHash=integrity["ruleVersionHash"],
        importTreeHash=integrity["importTreeHash"],
        validationStatus=integrity["validationStatus"],
        previousRuleName=previous_rule_name,
        updatedWorkflowReferences=updated_workflows or [],
        updatedRuleImports=updated_imports or [],
    )


@router.get("", response_model=list[AegisRuleSummaryResponse])
async def list_aegis_rules(db: Session = Depends(get_aegis_db_session)) -> list[AegisRuleSummaryResponse]:
    service = _service(db)
    return [_summary(service, rule) for rule in service.list_rules()]


@router.post(
    "/validate",
    response_model=RuleValidateResponse,
)
async def validate_aegis_rule(
    request: AegisRuleValidateRequest,
    db: Session = Depends(get_aegis_db_session),
) -> RuleValidateResponse:
    service = _service(db)
    result = service.validate_draft_rule(
        rule_text=request.rule_text,
        rule_name=request.rule_name or "",
    )
    return _validation_response(result)


@router.post("/graph-preview", response_model=AegisRuleGraphResponse)
async def preview_aegis_rule_graph(
    payload: AegisRuleGraphPreviewRequest,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleGraphResponse:
    service = _service(db)
    rule_name = (payload.ruleName or "").strip()
    try:
        graph = service.get_rule_graph_data_for_text(rule_name, payload.ruleText)
        targets = service.get_target_node_names_for_text(rule_name, payload.ruleText)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "RULE_GRAPH_PREVIEW_FAILED",
                "message": str(exc),
                "ruleName": rule_name,
            },
        ) from exc
    return AegisRuleGraphResponse.model_validate(
        {
            **graph,
            "targetNodeNames": targets,
            "selectedTargetNodeName": None,
        }
    )


@router.post(
    "",
    dependencies=[Depends(require_scope("aegis:write"))],
    response_model=AegisRuleCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_aegis_rule(
    payload: SaveAegisRuleRequest,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleCreatedResponse:
    rule_name = payload.name.strip()
    if not rule_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule set name is required.")
    repository = AegisRuleRepositoryImpl(db)
    if payload.createOnly and repository.find_id_by_name(rule_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_RULE_NAME",
                "message": f"AEGIS rule set '{rule_name}' already exists.",
                "ruleName": rule_name,
            },
        )
    service = _service(db)
    selected_target = _target_payload_value(payload.targetNodeName)
    if selected_target:
        _validate_selected_target(service, rule_name, payload.ruleText, selected_target)
    if payload.requireWorkflowImpactPass:
        impact = _build_workflow_impact_test(
            service,
            db,
            rule_name,
            payload.ruleText,
            target_node_name=selected_target,
        )
        if not impact.passed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Affected AEGIS workflows must pass impact testing before this rule set can be saved.",
                    "impact": impact.model_dump(mode="json"),
                },
            )
    rule = service.save_converted_rule(
        rule_name,
        payload.category,
        payload.description,
        payload.ruleText,
        waived_error_ids=payload.waived_error_ids,
        target_node_name=selected_target,
    )
    if selected_target:
        repository.update_rule_target(rule_name, selected_target)
        rule.target_node_name = selected_target
    latest_file = service.get_latest_rule_file(rule_name)
    rule_text = service.decode_rule_file(latest_file)
    integrity = build_policy_integrity(service, rule_name, rule_text, latest_file.file_id)
    return AegisRuleCreatedResponse(
        ruleName=rule.name,
        category=rule.category,
        description=rule.description,
        targetNodeName=rule.target_node_name,
        latest_file_id=latest_file.file_id,
        ruleVersionHash=integrity["ruleVersionHash"],
        importTreeHash=integrity["importTreeHash"],
        validationStatus=integrity["validationStatus"],
    )


@router.patch(
    "/{rule_name}",
    dependencies=[Depends(require_scope("aegis:write"))],
    response_model=AegisRuleUpdateResponse,
)
async def update_aegis_rule(
    rule_name: str,
    payload: UpdateAegisRuleRequest,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleUpdateResponse:
    old_rule_name = rule_name.strip()
    new_rule_name = payload.name.strip()
    if not old_rule_name or not new_rule_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule set name is required.")

    repository = AegisRuleRepositoryImpl(db)
    service = RuleService(repository)
    existing_rule = service.get_rule_by_name(old_rule_name)
    existing_rule_text = service.get_rule_text(old_rule_name)
    syntax_changed = payload.ruleText != existing_rule_text
    if new_rule_name != old_rule_name and repository.find_id_by_name(new_rule_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_RULE_NAME",
                "message": f"AEGIS rule set '{new_rule_name}' already exists.",
                "ruleName": new_rule_name,
            },
        )

    selected_target = _target_payload_value(payload.targetNodeName)
    target_update_requested = payload.targetNodeName is not None
    target_changed = target_update_requested and selected_target != (existing_rule.target_node_name or "")
    if selected_target:
        _validate_selected_target(service, new_rule_name, payload.ruleText, selected_target)

    if syntax_changed:
        _raise_invalid_rule(new_rule_name, payload.ruleText, service)
    usage = _build_workflow_usage(service, db, old_rule_name) if target_changed else None
    if target_changed and usage and _workflow_reference_count(usage) > 0 and not payload.requireWorkflowImpactPass:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Affected AEGIS workflows must pass impact testing before the target node can be saved.",
                "ruleName": old_rule_name,
                "targetNodeName": selected_target,
                "usage": usage.model_dump(mode="json"),
            },
        )
    if payload.requireWorkflowImpactPass:
        impact = _build_workflow_impact_test(
            service,
            db,
            old_rule_name,
            payload.ruleText,
            target_node_name=selected_target,
        )
        if not impact.passed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Affected AEGIS workflows must pass impact testing before this rule set can be saved.",
                    "impact": impact.model_dump(mode="json"),
                },
            )

    updated = repository.update_rule_metadata(
        old_rule_name,
        new_rule_name,
        payload.category,
        payload.description,
        selected_target,
        target_update_requested,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{old_rule_name}' was not found")

    service.create_rule_file(
        new_rule_name,
        payload.ruleText,
        waived_error_ids=payload.waived_error_ids,
    )
    updated_imports = _rewrite_rule_import_references(service, old_rule_name, new_rule_name)
    updated_workflows = _rewrite_workflow_rule_references(db, service, old_rule_name, new_rule_name)
    return _created_response(
        service,
        new_rule_name,
        previous_rule_name=old_rule_name if old_rule_name != new_rule_name else None,
        updated_workflows=updated_workflows,
        updated_imports=updated_imports,
    )


@router.get("/{rule_name}", response_model=AegisRuleDetailResponse)
async def get_aegis_rule(
    rule_name: str,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleDetailResponse:
    return _detail(_service(db), rule_name)


@router.get("/{rule_name}/workflow-usage", response_model=AegisRuleWorkflowUsageResponse)
async def get_aegis_rule_workflow_usage(
    rule_name: str,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleWorkflowUsageResponse:
    return _build_workflow_usage(_service(db), db, rule_name)


@router.post("/{rule_name}/workflow-impact-test", response_model=AegisRuleWorkflowImpactTestResponse)
async def test_aegis_rule_workflow_impact(
    rule_name: str,
    payload: AegisRuleWorkflowImpactTestRequest,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleWorkflowImpactTestResponse:
    return _build_workflow_impact_test(
        _service(db),
        db,
        rule_name,
        payload.ruleText,
        payload.workflowIds,
        payload.targetNodeName,
    )


@router.get("/{rule_name}/graph", response_model=AegisRuleGraphResponse)
async def get_aegis_rule_graph(
    rule_name: str,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleGraphResponse:
    service = _service(db)
    rule = service.get_rule_by_name(rule_name)
    graph = service.get_rule_graph_data(rule_name)
    targets = service.get_target_node_names(rule_name)
    return AegisRuleGraphResponse.model_validate(
        {
            **graph,
            "targetNodeNames": targets,
            "selectedTargetNodeName": rule.target_node_name,
        }
    )


@router.patch(
    "/{rule_name}/target",
    dependencies=[Depends(require_scope("aegis:write"))],
    response_model=AegisRuleTargetUpdateResponse,
)
async def update_aegis_rule_target(
    rule_name: str,
    payload: UpdateAegisRuleTargetRequest,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleTargetUpdateResponse:
    normalized_rule_name = rule_name.strip()
    target_node_name = payload.targetNodeName.strip()
    if not normalized_rule_name or not target_node_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule target node is required.")

    repository = AegisRuleRepositoryImpl(db)
    service = RuleService(repository)
    rule = service.get_rule_by_name(normalized_rule_name)
    rule_text = service.get_rule_text(normalized_rule_name)
    target_nodes = _validate_selected_target(service, normalized_rule_name, rule_text, target_node_name)
    current_target = rule.target_node_name or ""
    if current_target == target_node_name:
        return AegisRuleTargetUpdateResponse(
            ruleName=normalized_rule_name,
            targetNodeName=target_node_name,
            targetNodeNames=target_nodes,
        )

    usage = _build_workflow_usage(service, db, normalized_rule_name)
    if _workflow_reference_count(usage) > 0 and not payload.requireWorkflowImpactPass:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Affected AEGIS workflows must pass impact testing before the target node can be saved.",
                "ruleName": normalized_rule_name,
                "targetNodeName": target_node_name,
                "usage": usage.model_dump(mode="json"),
            },
        )

    impact: AegisRuleWorkflowImpactTestResponse | None = None
    if payload.requireWorkflowImpactPass:
        impact = _build_workflow_impact_test(
            service,
            db,
            normalized_rule_name,
            rule_text,
            target_node_name=target_node_name,
        )
        if not impact.passed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Affected AEGIS workflows must pass impact testing before the target node can be saved.",
                    "impact": impact.model_dump(mode="json"),
                },
            )

    if not repository.update_rule_target(normalized_rule_name, target_node_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{normalized_rule_name}' was not found",
        )
    return AegisRuleTargetUpdateResponse(
        ruleName=normalized_rule_name,
        targetNodeName=target_node_name,
        targetNodeNames=target_nodes,
        impact=impact,
    )


@router.get("/{rule_name}/text", response_model=AegisRuleTextResponse)
async def get_aegis_rule_text(
    rule_name: str,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleTextResponse:
    detail = _detail(_service(db), rule_name)
    return AegisRuleTextResponse(
        ruleText=detail.ruleText,
        ruleName=rule_name,
        latest_file_id=detail.latest_file_id,
        ruleVersionHash=detail.ruleVersionHash,
        importTreeHash=detail.importTreeHash,
        validationStatus=detail.validationStatus,
    )


@router.post(
    "/{rule_name}/versions",
    dependencies=[Depends(require_scope("aegis:write"))],
    response_model=AegisRuleVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_aegis_rule_version(
    rule_name: str,
    payload: AegisRuleVersionCreateRequest,
    db: Session = Depends(get_aegis_db_session),
) -> AegisRuleVersionResponse:
    service = _service(db)
    if payload.requireWorkflowImpactPass:
        impact = _build_workflow_impact_test(service, db, rule_name, payload.ruleText)
        if not impact.passed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Affected AEGIS workflows must pass impact testing before this rule version can be saved.",
                    "impact": impact.model_dump(mode="json"),
                },
            )
    rule_text = service.create_rule_file(
        rule_name,
        payload.ruleText,
        waived_error_ids=payload.waived_error_ids,
    )
    latest_file = service.get_latest_rule_file(rule_name)
    integrity = build_policy_integrity(service, rule_name, rule_text, latest_file.file_id)
    return AegisRuleVersionResponse(
        ruleName=rule_name,
        ruleText=rule_text,
        latest_file_id=latest_file.file_id,
        ruleVersionHash=integrity["ruleVersionHash"],
        importTreeHash=integrity["importTreeHash"],
        validationStatus=integrity["validationStatus"],
    )


@router.get("/{rule_name}/targets", response_model=list[str])
async def list_aegis_rule_targets(
    rule_name: str,
    db: Session = Depends(get_aegis_db_session),
) -> list[str]:
    return _service(db).get_target_node_names(rule_name)


@router.get("/{rule_name}/imports", response_model=AegisImportTreeResponse)
async def get_aegis_rule_imports(
    rule_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_aegis_db_session),
) -> AegisImportTreeResponse:
    service = _service(db)
    rule_text = service.get_rule_text(rule_name)
    tree = build_import_tree(service, rule_name, rule_text)
    total_count = len(tree.imports)
    paged = tree.imports[offset : offset + limit]
    errors = [
        AegisStoreError(
            code="UNRESOLVED_IMPORT",
            message=f"Imported rule '{missing}' is missing from the AEGIS rule store",
            ruleName=missing,
        )
        for missing in tree.missing
    ]
    return AegisImportTreeResponse(
        ruleName=rule_name,
        imports=[
            AegisImportEntry(
                name=entry.name,
                content_hash=entry.content_hash,
                node_count=entry.node_count,
                depth=entry.depth,
                direct_imports=entry.direct_imports,
            )
            for entry in paged
        ],
        missing=tree.missing,
        has_cycles=tree.has_cycles,
        total_count=total_count,
        offset=offset,
        limit=limit,
        importTreeHash=tree.import_tree_hash,
        errors=errors,
    )
