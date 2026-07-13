"""
Validation API Router.
Handles rule validation endpoints.
"""

import structlog
from functools import lru_cache

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.adapters.inbound.http.dependencies import get_db_session
from src.adapters.inbound.http.schemas.validation import (
    OntologyReviewQueueItemDetail,
    RuleValidateRequest,
    RuleValidateResponse,
    ValidationEntryDetail,
)
from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.services.rule_service import RuleService
from src.services.rule_validation_service import RuleValidationService, ValidationResult

router = APIRouter(prefix="/api/v1/rules", tags=["validation"])
logger = structlog.get_logger("inferra.fastapi.validation")


@lru_cache(maxsize=1)
def _get_validation_service() -> RuleValidationService:
    """Get the validation service singleton (overridable via dependency_overrides)."""
    return RuleValidationService()


def _get_rule_service(
    db: Session = Depends(get_db_session),
    validation_service: RuleValidationService = Depends(_get_validation_service),
) -> RuleService:
    """Build the rule service with a request-scoped repository."""
    return RuleService(RuleRepositoryImpl(db), validation_service=validation_service)


def _to_validate_response(result: ValidationResult) -> RuleValidateResponse:
    errors = [
        ValidationEntryDetail(
            code=e.code,
            message=e.message,
            waiver_id=e.waiver_id,
            line=e.line,
            node_name=e.node_name,
            severity=e.severity,
            category=e.category,
            source=e.source,
            blocking=e.blocking,
            reason=e.reason,
            review_required=e.review_required,
            review_item_id=e.review_item_id,
        )
        for e in result.errors
    ]

    warnings = [
        ValidationEntryDetail(
            code=w.code,
            message=w.message,
            waiver_id=w.waiver_id,
            line=w.line,
            node_name=w.node_name,
            severity=w.severity,
            category=w.category,
            source=w.source,
            blocking=w.blocking,
            reason=w.reason,
            review_required=w.review_required,
            review_item_id=w.review_item_id,
        )
        for w in result.warnings
    ]

    review_queue = [
        OntologyReviewQueueItemDetail(
            proposal_id=item.proposal_id,
            warning_code=item.warning_code,
            action=item.action,
            target=item.target,
            rationale=item.rationale,
            line=item.line,
            node_name=item.node_name,
            proposed_value=item.proposed_value,
            approval_state=item.approval_state,
            requires_rule_approval=item.requires_rule_approval,
            mutates_assets=item.mutates_assets,
            alters_deterministic_outcome=item.alters_deterministic_outcome,
        )
        for item in result.review_queue
    ]

    return RuleValidateResponse(
        valid=result.valid,
        errors=errors,
        warnings=warnings,
        review_queue=review_queue,
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/validate",
    response_model=RuleValidateResponse,
)
async def validate_rule(
    request: RuleValidateRequest,
    service: RuleService = Depends(_get_rule_service),
) -> RuleValidateResponse:
    """
    Validate rule text before persistence.

    This is a synchronous pre-save gate. If validation fails
    (valid=False), the rule must NOT be persisted.
    """
    logger.info("validating_rule", rule_name=request.rule_name or "<unnamed>")

    result = service.validate_draft_rule(
        rule_text=request.rule_text,
        rule_name=request.rule_name or "",
    )

    return _to_validate_response(result)
