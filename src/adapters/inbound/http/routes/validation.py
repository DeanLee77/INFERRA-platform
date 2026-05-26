"""
Validation API Router.
Handles rule validation endpoints.
"""

import structlog
from functools import lru_cache

from fastapi import APIRouter, Depends

from src.adapters.inbound.http.schemas.validation import (
    RuleValidateRequest,
    RuleValidateResponse,
    ValidationEntryDetail,
)
from src.services.rule_validation_service import RuleValidationService

router = APIRouter(prefix="/api/v1/rules", tags=["validation"])
logger = structlog.get_logger("inferra.fastapi.validation")


@lru_cache(maxsize=1)
def _get_validation_service() -> RuleValidationService:
    """Get the validation service singleton (overridable via dependency_overrides)."""
    return RuleValidationService()


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/validate",
    response_model=RuleValidateResponse,
)
async def validate_rule(
    request: RuleValidateRequest,
    service: RuleValidationService = Depends(_get_validation_service),
) -> RuleValidateResponse:
    """
    Validate rule text before persistence.

    This is a synchronous pre-save gate. If validation fails
    (valid=False), the rule must NOT be persisted.
    """
    logger.info("validating_rule", rule_name=request.rule_name or "<unnamed>")

    result = service.validate(
        rule_text=request.rule_text,
        rule_name=request.rule_name or "",
    )

    errors = [
        ValidationEntryDetail(
            code=e.code,
            message=e.message,
            waiver_id=e.waiver_id,
            line=e.line,
            node_name=e.node_name,
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
        )
        for w in result.warnings
    ]

    return RuleValidateResponse(
        valid=result.valid,
        errors=errors,
        warnings=warnings,
    )
