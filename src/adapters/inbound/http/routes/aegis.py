"""AEGIS workflow runtime API routes."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.adapters.inbound.http.dependencies import get_aegis_db_session, get_db_session, get_session_store, require_scope
from src.adapters.inbound.http.routes.inference import _create_session_impl, _llm_configuration_snapshot, _request_user_id
from src.adapters.inbound.http.schemas.inference import SessionCreateRequest, SessionCreateResponse
from src.adapters.outbound.persistence.database import get_aegis_db
from src.adapters.outbound.persistence.aegis_event_ledger_repository import (
    AegisEventLedgerRepository,
    AegisEventSequenceError,
    AegisIdempotencyConflictError,
)
from src.adapters.outbound.persistence.aegis_rule_repository import AegisRuleRepositoryImpl
from src.adapters.outbound.persistence.aegis_trigger_policy_repository import (
    AegisTriggerIdempotencyConflictError,
    AegisTriggerPolicyRepository,
)
from src.adapters.outbound.persistence.aegis_workflow_repository import (
    AegisWorkflowConcurrencyError,
    AegisWorkflowRepository,
)
from src.domain.aegis import get_synthetic_aegis_runtime
from src.domain.aegis.autonomy import assign_autonomy_level, list_autonomy_levels
from src.domain.aegis.phase3_runtime import (
    AegisPhase3RuntimeService,
    AegisRuntimeAuthorizationError,
    AegisRuntimeStateError,
)
from src.domain.aegis.rule_store import (
    AEGIS_PRODUCT,
    AEGIS_RULE_STORE,
    build_import_tree,
    build_policy_integrity,
    stable_hash,
)
from src.domain.aegis.insurance_fraud_replay import (
    INSURANCE_WORKFLOW_ID,
    InsuranceFraudAuthorizationError,
    InsuranceFraudEventSequenceError,
    InsuranceFraudIdempotencyConflictError,
)
from src.domain.aegis.synthetic_workflow_runtime import EventSequenceError, ROBOT_RUN_ID, ROBOT_WORKFLOW_ID
from src.domain.aegis.trigger_policy import (
    AegisTriggerAuthorizationError,
    AegisTriggerConflictError,
    AegisTriggerPolicyService,
    AegisTriggerValidationError,
)
from src.domain.aegis.workflow_authoring import AegisWorkflowActivationError, AegisWorkflowAuthoringService
from src.domain.inference.session_service import InferenceSessionService
from src.infrastructure.logging_config import get_logger
from src.ports.session_store_port import SessionStorePort
from src.services.rule_service import RuleService


router = APIRouter(prefix="/api/v1/aegis", tags=["aegis-workflow-runtime"])
_logger = get_logger(__name__)


def _runtime():
    return get_synthetic_aegis_runtime()


def _rule_service(db: Session) -> RuleService:
    return RuleService(AegisRuleRepositoryImpl(db))


def _with_authoring_service(operation):
    db_context = get_aegis_db()
    db = next(db_context)
    try:
        service = AegisWorkflowAuthoringService(
            AegisWorkflowRepository(db),
            _rule_service(db),
        )
        return operation(service)
    finally:
        db_context.close()


def _session_service(
    session_store: SessionStorePort = Depends(get_session_store),
) -> InferenceSessionService:
    return InferenceSessionService(session_store)


def _phase3_service(db: Session) -> AegisPhase3RuntimeService:
    return AegisPhase3RuntimeService(AegisEventLedgerRepository(db))


def _trigger_policy_service(
    db: Session,
    session_service: InferenceSessionService,
    platform_db: Session | None = None,
) -> AegisTriggerPolicyService:
    return AegisTriggerPolicyService(
        AegisTriggerPolicyRepository(db),
        _rule_service(db),
        session_service,
        _phase3_service(db),
        (
            (lambda: _optional_llm_configuration_snapshot("aegis", platform_db))
            if platform_db is not None
            else None
        ),
    )


def _optional_llm_configuration_snapshot(
    product_id: str,
    db: Session,
) -> dict[str, Any]:
    """Keep deterministic AEGIS workflows available if optional LLM state is unavailable."""
    try:
        return _llm_configuration_snapshot(product_id, db)
    except Exception as exc:
        _logger.warning(
            "aegis_llm_configuration_unavailable",
            product_id=product_id,
            error_type=type(exc).__name__,
        )
        return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_synthetic_workflow(workflow_id: str) -> bool:
    return workflow_id in {ROBOT_WORKFLOW_ID, INSURANCE_WORKFLOW_ID}


def _assign_autonomy_payload(body: dict[str, Any]) -> dict[str, Any]:
    rules = body.get("rules")
    if not isinstance(rules, list):
        return assign_autonomy_level(body)

    result = list_autonomy_levels()
    last_assignment: dict[str, Any] | None = None
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("autonomy rules must be objects")
        result = assign_autonomy_level(_autonomy_rule_assignment_payload(rule))
        last_assignment = result.get("assignment")
    if last_assignment is not None:
        result["assignment"] = last_assignment
    return result


def _autonomy_rule_assignment_payload(rule: dict[str, Any]) -> dict[str, Any]:
    subject_type = str(rule.get("subjectType") or "agent").strip().lower()
    subject_id = str(rule.get("subjectId") or rule.get("id") or "").strip()
    if subject_type == "global":
        agent_id = "global"
    elif subject_type == "workflow":
        if not subject_id:
            raise ValueError("workflow autonomy rules require subjectId")
        agent_id = f"workflow:{subject_id}"
    else:
        agent_id = subject_id
    return {
        "agentId": agent_id,
        "level": rule.get("level"),
        "assignedBy": rule.get("updatedBy") or rule.get("assignedBy") or "aegis-policy-admin",
        "rationale": rule.get("comment") or "Autonomy rule updated from API contract.",
        "constraints": {
            "minConfidenceThreshold": rule.get("minConfidenceThreshold"),
            "requiresEvidence": rule.get("requiresEvidence"),
            "requiresAuthority": rule.get("requiresAuthority"),
        },
    }


def _autonomy_levels_contract(data: dict[str, Any]) -> dict[str, Any]:
    generated_at = _utc_now()
    threshold = float(data.get("certifiedConfidenceThreshold") or 0.85)
    response = dict(data)
    response["generatedAt"] = generated_at
    response["source"] = "platform_live"
    response["rules"] = [
        _autonomy_rule_contract(assignment, threshold, generated_at)
        for assignment in data.get("assignments", [])
        if isinstance(assignment, dict)
    ]
    return response


def _autonomy_rule_contract(assignment: dict[str, Any], threshold: float, generated_at: str) -> dict[str, Any]:
    agent_id = str(assignment.get("agentId") or "unknown-agent")
    constraints = assignment.get("constraints") if isinstance(assignment.get("constraints"), dict) else {}
    subject_type = "agent"
    subject_id = agent_id
    if agent_id == "global":
        subject_type = "global"
        subject_id = None
    elif agent_id.startswith("workflow:"):
        subject_type = "workflow"
        subject_id = agent_id.split(":", 1)[1]
    level = str(assignment.get("assignedLevel") or "supervised_autonomy")
    min_confidence = constraints.get("minConfidenceThreshold")
    try:
        min_confidence_threshold = float(min_confidence)
    except (TypeError, ValueError):
        min_confidence_threshold = threshold
    rule = {
        "id": f"{subject_type}:{subject_id or 'default'}",
        "subjectType": subject_type,
        "level": level,
        "status": "active",
        "minConfidenceThreshold": min_confidence_threshold,
        "requiresEvidence": bool(
            constraints.get(
                "requiresEvidence",
                level in {"supervised_autonomy", "certified_autonomy"},
            )
        ),
        "requiresAuthority": bool(constraints.get("requiresAuthority", True)),
        "updatedAt": generated_at,
        "updatedBy": str(assignment.get("assignedBy") or "aegis-policy-admin"),
        "comment": str(assignment.get("rationale") or ""),
    }
    if subject_id is not None:
        rule["subjectId"] = subject_id
    rule["policyVersionHash"] = stable_hash({"contract": "aegis-autonomy-level-rule-v1", "rule": rule})
    return rule


@router.get("/autonomy-levels")
async def get_autonomy_levels() -> dict[str, Any]:
    return _autonomy_levels_contract(list_autonomy_levels())


@router.post("/autonomy-levels", dependencies=[Depends(require_scope("aegis:write"))])
async def update_autonomy_level(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _autonomy_levels_contract(_assign_autonomy_payload(body or {}))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/agents/risk-heatmap")
async def get_agent_risk_heatmap(
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        data = _phase3_service(db).get_agent_risk_heatmap()
        data["rows"].append(_synthetic_risk_heatmap_row())
        data["ledgerSource"] = data.get("source")
        data["source"] = "platform_live"
        data["generatedAt"] = _utc_now()
        data["rows"] = sorted(
            [_risk_heatmap_contract_row(row) for row in data["rows"]],
            key=lambda row: (-row["riskScore"], row["agentId"], row["runId"]),
        )
        data["summary"] = {
            "rowCount": len(data["rows"]),
            "highRiskCount": sum(1 for row in data["rows"] if row["riskBand"] == "high"),
            "breachCount": sum(1 for row in data["rows"] if row.get("slaState") in {"breached", "escalated"}),
        }
        return data
    except Exception as exc:
        raise _map_error(exc) from exc


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(
        exc,
        (
            AegisRuntimeAuthorizationError,
            AegisTriggerAuthorizationError,
            InsuranceFraudAuthorizationError,
        ),
    ):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (AegisWorkflowConcurrencyError, AegisTriggerConflictError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AegisWorkflowActivationError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(
        exc,
        (
            EventSequenceError,
            AegisEventSequenceError,
            AegisIdempotencyConflictError,
            AegisTriggerIdempotencyConflictError,
            InsuranceFraudEventSequenceError,
            InsuranceFraudIdempotencyConflictError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AegisRuntimeStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (AegisTriggerValidationError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Unexpected AEGIS workflow runtime error")


@router.get("/workflows")
async def list_workflows() -> dict[str, Any]:
    try:
        persisted = _with_authoring_service(lambda service: service.list_workflows())
        return {"workflows": [*persisted, *_runtime().list_workflows()["workflows"]]}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows", dependencies=[Depends(require_scope("aegis:write"))])
async def create_workflow(body: dict[str, Any]) -> dict[str, Any]:
    try:
        workflow_id = body.get("id")
        if _is_synthetic_workflow(str(workflow_id)):
            return _runtime().get_workflow(str(workflow_id))
        return _with_authoring_service(lambda service: service.create_workflow(body))
    except Exception as exc:  # pragma: no cover - mapped for API clients
        raise _map_error(exc) from exc


@router.post("/workflows/generate", dependencies=[Depends(require_scope("aegis:write"))])
async def generate_workflow(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _with_authoring_service(lambda service: service.generate_workflow(body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/regenerate", dependencies=[Depends(require_scope("aegis:write"))])
async def regenerate_workflow(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _with_authoring_service(lambda service: service.regenerate_workflow(body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/extend", dependencies=[Depends(require_scope("aegis:write"))])
async def extend_workflow(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _with_authoring_service(lambda service: service.extend_workflow(body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            return _runtime().get_workflow(workflow_id)
        return _with_authoring_service(lambda service: service.get_workflow(workflow_id))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/workflows/{workflow_id}", dependencies=[Depends(require_scope("aegis:write"))])
async def update_workflow(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            raise ValueError("Synthetic workflows cannot be updated through authoring contracts")
        return _with_authoring_service(lambda service: service.update_workflow(workflow_id, body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/{workflow_id}/activation-approval", dependencies=[Depends(require_scope("aegis:write"))])
async def approve_workflow_activation(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            raise ValueError("Synthetic workflows do not support generated activation approval")
        return _with_authoring_service(lambda service: service.record_activation_approval(workflow_id, body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/{workflow_id}/activate", dependencies=[Depends(require_scope("aegis:write"))])
async def activate_workflow(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            raise ValueError("Synthetic workflow activation is managed by the runtime fixture")
        return _with_authoring_service(lambda service: service.activate_workflow(workflow_id, body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflows/{workflow_id}/versions")
async def list_workflow_versions(workflow_id: str) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            return {"workflowId": workflow_id, "versions": [_runtime().get_workflow(workflow_id)]}
        return _with_authoring_service(lambda service: service.list_versions(workflow_id))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/{workflow_id}/versions", dependencies=[Depends(require_scope("aegis:write"))])
async def create_workflow_version(workflow_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            raise ValueError("Synthetic workflows do not support persisted authoring versions")
        return _with_authoring_service(lambda service: service.update_workflow(workflow_id, body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflows/{workflow_id}/versions/{version_id}")
async def get_workflow_version(workflow_id: str, version_id: str) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            workflow = _runtime().get_workflow(workflow_id)
            if version_id not in {workflow["version"], workflow_id}:
                raise LookupError(f"Workflow version '{version_id}' was not found")
            return workflow
        return _with_authoring_service(lambda service: service.get_version(workflow_id, version_id))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/{workflow_id}/validate", dependencies=[Depends(require_scope("aegis:write"))])
async def validate_workflow(workflow_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            return _runtime().validate_workflow(workflow_id)
        return _with_authoring_service(lambda service: service.validate_workflow(workflow_id, body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflows/{workflow_id}/compile", dependencies=[Depends(require_scope("aegis:write"))])
async def compile_workflow(workflow_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        if _is_synthetic_workflow(workflow_id):
            return _runtime().compile_workflow(workflow_id)
        return _with_authoring_service(lambda service: service.compile_workflow(workflow_id, body))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflow-runs", dependencies=[Depends(require_scope("aegis:write"))])
async def create_workflow_run(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _runtime().create_run(body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-proposals", dependencies=[Depends(require_scope("aegis:write"))])
async def create_action_proposal(
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).create_action_proposal(body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/trigger-policies")
async def list_trigger_policies(
    status: str | None = Query("active"),
    db: Session = Depends(get_aegis_db_session),
    session_service: InferenceSessionService = Depends(_session_service),
) -> dict[str, Any]:
    try:
        normalized_status = status.strip().lower() if isinstance(status, str) and status else None
        return _trigger_policy_service(db, session_service).list_policies(status=normalized_status)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/trigger-policies", dependencies=[Depends(require_scope("aegis:write"))])
async def create_trigger_policy(
    body: dict[str, Any],
    fastapi_request: Request,
    db: Session = Depends(get_aegis_db_session),
    session_service: InferenceSessionService = Depends(_session_service),
) -> dict[str, Any]:
    try:
        return _trigger_policy_service(db, session_service).create_policy(
            body,
            owner_id=_request_user_id(fastapi_request),
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/triggers/outcome", dependencies=[Depends(require_scope("aegis:write"))])
async def trigger_from_outcome(
    body: dict[str, Any],
    fastapi_request: Request,
    db: Session = Depends(get_aegis_db_session),
    platform_db: Session = Depends(get_db_session),
    session_service: InferenceSessionService = Depends(_session_service),
) -> dict[str, Any]:
    try:
        return _trigger_policy_service(db, session_service, platform_db).trigger_from_outcome(
            body,
            owner_id=_request_user_id(fastapi_request),
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/triggers/direct", dependencies=[Depends(require_scope("aegis:write"))])
async def trigger_direct(
    body: dict[str, Any],
    fastapi_request: Request,
    db: Session = Depends(get_aegis_db_session),
    platform_db: Session = Depends(get_db_session),
    session_service: InferenceSessionService = Depends(_session_service),
) -> dict[str, Any]:
    try:
        return _trigger_policy_service(db, session_service, platform_db).trigger_direct(
            body,
            owner_id=_request_user_id(fastapi_request),
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}")
async def get_action_run(
    run_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).get_action_run(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/preflight", dependencies=[Depends(require_scope("aegis:write"))])
async def evaluate_action_preflight(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).evaluate_preflight(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/gate", dependencies=[Depends(require_scope("aegis:write"))])
async def evaluate_action_gate(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).evaluate_gate(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/options")
async def get_action_options(
    run_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        state = _phase3_service(db).get_action_run(run_id)
        snapshot = _phase3_service(db).export_passport(run_id)["snapshot"]["snapshot"]
        return {
            "runId": run_id,
            "options": snapshot.get("options", {}),
            "allowedActions": state["allowedActions"],
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post(
    "/action-runs/{run_id}/options/{option_id}/select",
    dependencies=[Depends(require_scope("aegis:write"))],
)
async def select_action_option(
    run_id: str,
    option_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).select_option(run_id, option_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post(
    "/action-runs/{run_id}/approvals/{approval_id}/decision",
    dependencies=[Depends(require_scope("aegis:write"))],
)
async def decide_action_approval(
    run_id: str,
    approval_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).decide_approval(run_id, approval_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/evidence-requests", dependencies=[Depends(require_scope("aegis:write"))])
async def request_action_evidence(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).request_evidence(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/evidence-facts", dependencies=[Depends(require_scope("aegis:write"))])
async def ingest_action_evidence_facts(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).ingest_evidence_facts(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/evidence-facts")
async def get_action_evidence_facts(
    run_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        snapshot = _phase3_service(db).export_passport(run_id)["snapshot"]
        return {
            "runId": run_id,
            "snapshotId": snapshot["snapshotId"],
            "snapshotHash": snapshot["snapshotHash"],
            "facts": snapshot["snapshot"].get("facts", {}),
            "factProvenance": snapshot["snapshot"].get("factProvenance", {}),
            "authorityBoundary": {
                "authoritativeClasses": ["asserted", "inferred"],
                "advisoryClasses": ["advisory", "learned", "retrieval_advisory", "similar_case_advisory"],
            },
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/overrides", dependencies=[Depends(require_scope("aegis:write"))])
async def request_action_override(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).request_override(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post(
    "/action-runs/{run_id}/overrides/{override_id}/decision",
    dependencies=[Depends(require_scope("aegis:write"))],
)
async def decide_action_override(
    run_id: str,
    override_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).decide_override(run_id, override_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/fallback", dependencies=[Depends(require_scope("aegis:write"))])
async def trigger_action_fallback(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).trigger_fallback(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/receipt", dependencies=[Depends(require_scope("aegis:write"))])
async def seal_action_receipt(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).seal_receipt(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/receipt")
async def get_action_receipt(
    run_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).get_receipt(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/passport")
async def export_action_passport(
    run_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).export_passport(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/dossier")
async def get_action_dossier(
    run_id: str,
    format: str = Query("json"),
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).get_dossier(run_id, format)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/action-runs/{run_id}/sla/tick", dependencies=[Depends(require_scope("aegis:write"))])
async def evaluate_action_sla(
    run_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).evaluate_sla(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/counterfactuals")
async def get_action_counterfactuals(
    run_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).get_counterfactuals(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-proposals/{proposal_id}/counterfactuals")
async def get_action_proposal_counterfactuals(
    proposal_id: str,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).get_counterfactuals_for_proposal(proposal_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/policies/{policy_id}/replay", dependencies=[Depends(require_scope("aegis:write"))])
async def replay_policy(
    policy_id: str,
    body: dict[str, Any] | None = None,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _policy_replay_contract(_phase3_service(db).replay_policy(policy_id, body or {}))
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/action-runs/{run_id}/similar-cases")
async def get_action_similar_cases(
    run_id: str,
    limit: int = 5,
    db: Session = Depends(get_aegis_db_session),
) -> dict[str, Any]:
    try:
        return _phase3_service(db).find_similar_cases(run_id, limit)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflow-runs/{run_id}")
async def get_workflow_run(run_id: str) -> dict[str, Any]:
    try:
        return _runtime().get_run(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflow-runs/{run_id}/events", dependencies=[Depends(require_scope("aegis:write"))])
async def append_workflow_event(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _runtime().append_event(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/workflow-runs/{run_id}/transition", dependencies=[Depends(require_scope("aegis:write"))])
async def transition_workflow_run(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _runtime().transition(run_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflow-runs/{run_id}/timeline")
async def get_workflow_timeline(run_id: str) -> dict[str, Any]:
    try:
        return _runtime().get_timeline(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflow-runs/{run_id}/options")
async def get_workflow_options(run_id: str) -> dict[str, Any]:
    try:
        return _runtime().get_options(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post(
    "/workflow-runs/{run_id}/options/{option_id}/select",
    dependencies=[Depends(require_scope("aegis:write"))],
)
async def select_workflow_option(run_id: str, option_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _runtime().select_option(run_id, option_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post(
    "/workflow-runs/{run_id}/approvals/{approval_id}/decision",
    dependencies=[Depends(require_scope("aegis:write"))],
)
async def decide_workflow_approval(
    run_id: str,
    approval_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    try:
        return _runtime().decide_approval(run_id, approval_id, body)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflow-runs/{run_id}/receipt")
async def get_workflow_receipt(run_id: str) -> dict[str, Any]:
    try:
        return _runtime().get_receipt(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/workflow-runs/{run_id}/dossier")
async def get_workflow_dossier(run_id: str) -> dict[str, Any]:
    try:
        return _runtime().get_dossier(run_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/gates/evaluate", dependencies=[Depends(require_scope("aegis:write"))])
async def evaluate_aegis_gate(
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        requested_rule_name = (body or {}).get("ruleName") or (body or {}).get("rule_name")
        if not requested_rule_name:
            return _runtime().evaluate_gate(body)

        db_context = get_aegis_db()
        db = next(db_context)
        try:
            return _runtime().evaluate_gate(body, _rule_service(db))
        finally:
            db_context.close()
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/policy-modules")
async def list_policy_modules() -> dict[str, Any]:
    db_context = get_aegis_db()
    db = next(db_context)
    try:
        service = _rule_service(db)
        modules: list[dict[str, Any]] = []
        for rule in service.list_rules():
            name = rule.get("name") if isinstance(rule, dict) else getattr(rule, "name", None)
            if not name:
                continue
            category = rule.get("category") if isinstance(rule, dict) else getattr(rule, "category", None)
            description = rule.get("description") if isinstance(rule, dict) else getattr(rule, "description", None)
            try:
                latest_file = service.get_latest_rule_file(name)
                rule_text = service.decode_rule_file(latest_file)
                integrity = build_policy_integrity(service, name, rule_text, latest_file.file_id)
                import_tree = build_import_tree(service, name, rule_text)
                compatible = (
                    integrity["validationStatus"] == "valid"
                    and not integrity["missingImports"]
                    and not integrity["hasImportCycles"]
                )
                modules.append(
                    {
                        "moduleId": f"{AEGIS_RULE_STORE}:{name}",
                        "ruleName": name,
                        "owner": category or "INFERRA Policy Mesh",
                        "description": description or "",
                        "product": AEGIS_PRODUCT,
                        "store": AEGIS_RULE_STORE,
                        "latestFileId": latest_file.file_id,
                        "versionHash": integrity["ruleVersionHash"],
                        "importTreeHash": integrity["importTreeHash"],
                        "expiry": None,
                        "dependencies": [
                            {
                                "ruleName": entry.name,
                                "versionHash": entry.content_hash,
                                "depth": entry.depth,
                                "directImports": entry.direct_imports,
                            }
                            for entry in import_tree.imports
                        ],
                        "compatibility": {
                            "contract": "aegis-policy-module-v1",
                            "compatible": compatible,
                            "validationStatus": integrity["validationStatus"],
                            "missingImports": integrity["missingImports"],
                            "hasImportCycles": integrity["hasImportCycles"],
                        },
                        "activationStatus": "active" if compatible else "blocked",
                    }
                )
            except LookupError:
                modules.append(
                    {
                        "moduleId": f"{AEGIS_RULE_STORE}:{name}",
                        "ruleName": name,
                        "owner": category or "INFERRA Policy Mesh",
                        "description": description or "",
                        "product": AEGIS_PRODUCT,
                        "store": AEGIS_RULE_STORE,
                        "latestFileId": None,
                        "versionHash": None,
                        "importTreeHash": None,
                        "expiry": None,
                        "dependencies": [],
                        "compatibility": {
                            "contract": "aegis-policy-module-v1",
                            "compatible": False,
                            "validationStatus": "missing_rule_file",
                            "missingImports": [],
                            "hasImportCycles": False,
                        },
                        "activationStatus": "blocked",
                    }
                )
        return {
            "product": AEGIS_PRODUCT,
            "store": AEGIS_RULE_STORE,
            "modules": modules,
            "registryHash": _policy_registry_hash(modules),
        }
    except Exception as exc:
        raise _map_error(exc) from exc
    finally:
        db_context.close()


def _policy_registry_hash(modules: list[dict[str, Any]]) -> str:
    return stable_hash(
        {
            "contract": "aegis-policy-mesh-registry-v1",
            "modules": [
                {
                    "moduleId": module["moduleId"],
                    "versionHash": module["versionHash"],
                    "importTreeHash": module["importTreeHash"],
                    "activationStatus": module["activationStatus"],
                }
                for module in modules
            ],
        }
    )


def _risk_heatmap_contract_row(row: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(row.get("agentId") or "unknown-agent")
    run_id = str(row.get("runId") or agent_id)
    status = str(row.get("status") or "unknown")
    latest_event_type = str(row.get("latestEventType") or "")
    evidence = row.get("evidenceCompleteness") if isinstance(row.get("evidenceCompleteness"), dict) else {}
    missing_evidence = max(0, int(evidence.get("requiredRefs") or 0) - int(evidence.get("hashedRefs") or 0))
    receipt_failures = 1 if status == "receipt_failed" or latest_event_type == "receipt.seal.failed" else 0
    fallback_count = (
        1
        if status in {"fallback_ready", "fallback_triggered"} or latest_event_type == "fallback.trigger"
        else 0
    )
    events = 1
    blocks = 1 if status in {"denied", "evidence_required", "approval_required", "receipt_failed"} else 0
    escalations = 1 if status in {"escalated", "approval_required"} or row.get("slaState") == "escalated" else 0
    overrides = 1 if latest_event_type.startswith("override.") else 0
    replay_drift = 1 if row.get("riskBand") == "high" and status in {"denied", "approval_required"} else 0
    contract = {
        "id": f"{agent_id}:{run_id}",
        "label": agent_id,
        "groupBy": "agent",
        "events": events,
        "blocks": blocks,
        "escalations": escalations,
        "overrides": overrides,
        "missingEvidence": missing_evidence,
        "fallbackRate": fallback_count * 100,
        "receiptFailures": receipt_failures,
        "replayDrift": replay_drift,
        "averageLatencyMs": int(row.get("averageLatencyMs") or 0),
        "topDriver": _risk_heatmap_top_driver(
            blocks=blocks,
            escalations=escalations,
            overrides=overrides,
            missing_evidence=missing_evidence,
            receipt_failures=receipt_failures,
            replay_drift=replay_drift,
            risk_score=int(row.get("riskScore") or 0),
        ),
        "eventWindowLabel": "Live ledger snapshot UTC",
    }
    contract["reviewAction"] = _risk_heatmap_review_action(contract)
    return {**row, **contract}


def _risk_heatmap_top_driver(
    *,
    blocks: int,
    escalations: int,
    overrides: int,
    missing_evidence: int,
    receipt_failures: int,
    replay_drift: int,
    risk_score: int,
) -> str:
    if missing_evidence:
        return "Missing evidence"
    if receipt_failures:
        return "Receipt signer failures"
    if replay_drift:
        return "Replay drift"
    if blocks:
        return "Policy blocks"
    if escalations:
        return "Escalations"
    if overrides:
        return "Operator overrides"
    if risk_score >= 70:
        return "High residual risk"
    return "No review driver"


def _risk_heatmap_review_action(row: dict[str, Any]) -> dict[str, Any]:
    if row["missingEvidence"] > 0:
        return {
            "ownerRole": "operator",
            "actionType": "repair_evidence",
            "label": "Repair evidence",
            "reason": "Required evidence references are missing hashes before certified autonomy review.",
            "requiredEvidenceRefs": [],
            "auditEventType": "certification.evidence_repair_requested",
        }
    if row["receiptFailures"] > 0:
        return {
            "ownerRole": "signer",
            "actionType": "retry_signer",
            "label": "Retry receipt signer",
            "reason": "Receipt sealing failed and must be retried before review export.",
            "requiredEvidenceRefs": [],
            "auditEventType": "certification.signer_retry_requested",
        }
    if row["replayDrift"] > 0 or row["blocks"] > 0:
        return {
            "ownerRole": "regulator",
            "actionType": "route_regulator_review",
            "label": "Route to regulator review",
            "reason": "The live policy outcome changed or blocked an action under replay.",
            "requiredEvidenceRefs": [],
            "auditEventType": "certification.regulator_review_routed",
        }
    return {
        "ownerRole": "insurer",
        "actionType": "inspect_hash",
        "label": "Inspect action history",
        "reason": "Low-risk review can verify immutable passport and receipt hashes.",
        "requiredEvidenceRefs": [],
        "auditEventType": "certification.hash_inspected",
    }


def _policy_replay_contract(result: dict[str, Any]) -> dict[str, Any]:
    policy = result.get("policy") if isinstance(result.get("policy"), dict) else {}
    policy_version_hash = str(policy.get("newPolicyVersionHash") or stable_hash({"policy": policy}))
    rows = [
        _policy_replay_contract_row(item, group, policy_version_hash)
        for group, items in result.get("groups", {}).items()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict)
    ]
    return {
        **result,
        "source": "platform_live",
        "policyGraphSource": result.get("source"),
        "policyVersionHash": policy_version_hash,
        "generatedAt": _utc_now(),
        "rows": rows,
    }


def _policy_replay_contract_row(item: dict[str, Any], group: str, replay_policy_hash: str) -> dict[str, Any]:
    snapshot_id = str(item.get("snapshotId") or "snapshot")
    run_id = str(item.get("runId") or snapshot_id.replace("snapshot", "run", 1))
    decision = str(item.get("decision") or "unknown")
    previous_decision = str(item.get("previousDecision") or "unknown")
    missing_evidence_refs = [] if decision != "evidence_insufficient" else ["ev-dock-clearance"]
    snake_group = _policy_replay_group_contract(group)
    recovery = _policy_replay_recovery_action(snake_group, missing_evidence_refs)
    return {
        "snapshotId": snapshot_id,
        "runId": run_id,
        "title": _title_from_identifier(snapshot_id),
        "workflowRunId": run_id,
        "previousOutcome": _gate_decision_contract(previous_decision),
        "replayedOutcome": (
            "EVIDENCE_INSUFFICIENT"
            if decision == "evidence_insufficient"
            else _gate_decision_contract(decision)
        ),
        "group": snake_group,
        "reason": "; ".join(item.get("reasons") or []) or "Replay outcome is unchanged under the selected policy.",
        "evidenceRefs": item.get("evidenceRefs") if isinstance(item.get("evidenceRefs"), list) else [],
        "missingEvidenceRefs": missing_evidence_refs,
        "sourcePolicyVersionHash": str(item.get("sourcePolicyVersionHash") or "sha256:policy-baseline-route-release"),
        "replayPolicyVersionHash": replay_policy_hash,
        "evidenceSufficiency": "insufficient" if missing_evidence_refs else "sufficient",
        "nextReviewRoute": "regulator" if snake_group in {"newly_denied", "evidence_insufficient"} else "insurer",
        "recoveryActionLabel": recovery["label"],
        "recoveryActionType": recovery["actionType"],
        "priority": recovery["priority"],
    }


def _policy_replay_group_contract(group: str) -> str:
    return {
        "newlyAllowed": "newly_allowed",
        "newlyDenied": "newly_denied",
        "newlyEscalated": "newly_escalated",
        "evidenceInsufficient": "evidence_insufficient",
    }.get(group, "unchanged")


def _gate_decision_contract(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    return {
        "allow": "ALLOW",
        "allowed": "ALLOW",
        "deny": "DENY",
        "denied": "DENY",
        "modify": "MODIFY",
        "modified": "MODIFY",
        "escalate": "ESCALATE",
        "escalated": "ESCALATE",
        "fallback": "FALLBACK",
        "require_approval": "REQUIRE_APPROVAL",
        "approval_required": "REQUIRE_APPROVAL",
        "require_evidence": "REQUIRE_EVIDENCE",
        "evidence_required": "REQUIRE_EVIDENCE",
    }.get(normalized, "REQUIRE_APPROVAL")


def _title_from_identifier(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title() or "Policy Replay Snapshot"


def _policy_replay_recovery_action(group: str, missing_evidence_refs: list[str]) -> dict[str, str]:
    if missing_evidence_refs:
        return {
            "label": "Repair evidence",
            "actionType": "repair_evidence",
            "priority": "high",
        }
    if group == "newly_denied":
        return {
            "label": "Route to regulator review",
            "actionType": "route_regulator_review",
            "priority": "high",
        }
    if group == "newly_escalated":
        return {
            "label": "Route to insurer review",
            "actionType": "route_insurer_review",
            "priority": "medium",
        }
    return {
        "label": "Inspect passport/receipt hashes",
        "actionType": "inspect_hash",
        "priority": "low",
    }


def _synthetic_risk_heatmap_row() -> dict[str, Any]:
    run = _runtime().get_run(ROBOT_RUN_ID)["run"]
    risk_score = int(run.get("riskScore") or 0)
    return {
        "agentId": "fleet-planner.alpha",
        "agentRole": "AI planner",
        "runId": run["id"],
        "workflowId": run["definitionId"],
        "status": run["status"],
        "requestedAutonomyLevel": run["autonomyLevel"],
        "riskScore": risk_score,
        "riskBand": "high" if risk_score >= 70 else "medium" if risk_score >= 40 else "low",
        "confidence": float(run.get("confidence", 0)) / 100,
        "slaState": run.get("slaState"),
        "latestEventType": run["events"][-1]["type"] if run.get("events") else None,
        "latestEventHash": run["eventCursor"].get("latestHash"),
        "evidenceCompleteness": {
            "requiredRefs": len(run.get("evidence") or []),
            "hashedRefs": len([evidence for evidence in run.get("evidence") or [] if evidence.get("contentHash")]),
            "complete": True,
        },
    }


@router.post(
    "/inference/sessions",
    dependencies=[Depends(require_scope("aegis:write"))],
    response_model=SessionCreateResponse,
)
async def create_aegis_inference_session(
    request: SessionCreateRequest,
    fastapi_request: Request,
    db: Session = Depends(get_aegis_db_session),
    platform_db: Session = Depends(get_db_session),
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionCreateResponse:
    try:
        return _create_session_impl(
            request.rule_name,
            request.target_node_name,
            False,
            _rule_service(db),
            session_service,
            _request_user_id(fastapi_request),
            request.ontology_profile,
            request.ontology_flags,
            _optional_llm_configuration_snapshot("aegis", platform_db),
        )
    except Exception as exc:
        raise _map_error(exc) from exc
