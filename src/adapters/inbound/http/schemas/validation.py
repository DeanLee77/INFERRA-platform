"""
Pydantic schemas for rule validation API endpoints.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Validation Request / Response
# =============================================================================

class RuleValidateRequest(BaseModel):
    """Request to validate rule text."""
    rule_text: str = Field(..., max_length=1_000_000, description="The raw rule text to validate")
    rule_name: Optional[str] = Field(None, max_length=255, description="Optional rule name for import scope")


class ValidationEntryDetail(BaseModel):
    """Detail for a single validation error or warning."""
    code: str = Field(..., description="Machine-readable error/warning code")
    message: str = Field(..., description="Human-readable description")
    waiver_id: str = Field(..., description="Stable identifier for human-review waiver matching")
    line: Optional[int] = Field(None, description="Line number (if applicable)")
    node_name: Optional[str] = Field(None, description="Node/variable name (if applicable)")
    severity: str = Field("warning", description="Severity: info, warning, high-risk, or error")
    category: Optional[str] = Field(None, description="Validation category")
    source: str = Field("deterministic", description="Validation source")
    blocking: bool = Field(False, description="Whether configured policy makes this entry blocking")
    reason: Optional[str] = Field(None, description="Explainability/provenance reason")
    review_required: bool = Field(False, description="Whether this entry has a human review candidate")
    review_item_id: Optional[str] = Field(None, description="Linked human review queue item id")


class OntologyReviewQueueItemDetail(BaseModel):
    """Human-review candidate for an ontology-suggested correction."""
    proposal_id: str
    warning_code: str
    action: str
    target: str
    rationale: str
    line: Optional[int] = None
    node_name: Optional[str] = None
    proposed_value: Optional[str] = None
    approval_state: str = "candidate"
    requires_rule_approval: bool = True
    mutates_assets: bool = False
    alters_deterministic_outcome: bool = False


class RuleValidateResponse(BaseModel):
    """Response from rule validation."""
    valid: bool = Field(..., description="Whether the rule text is valid")
    errors: List[ValidationEntryDetail] = Field(default_factory=list, description="Validation errors")
    warnings: List[ValidationEntryDetail] = Field(default_factory=list, description="Validation warnings")
    review_queue: List[OntologyReviewQueueItemDetail] = Field(
        default_factory=list,
        description="Ontology-suggested corrections awaiting human approval",
    )
