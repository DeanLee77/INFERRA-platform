"""Immutable, serializable Core validation diagnostics."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ValidationEntry:
    """Base for a single deterministic validation error or warning."""

    code: str
    message: str
    line: Optional[int] = None
    node_name: Optional[str] = None
    severity: str = "warning"
    category: Optional[str] = None
    source: str = "deterministic"
    blocking: bool = False
    reason: Optional[str] = None
    review_required: bool = False
    review_item_id: Optional[str] = None

    @property
    def waiver_id(self) -> str:
        if self.node_name:
            return f"{self.code}:{self.node_name}"
        if self.line is not None:
            return f"{self.code}:line_{self.line}"
        return self.code

    def to_dict(self) -> dict:
        result = {
            "code": self.code,
            "message": self.message,
            "waiver_id": self.waiver_id,
            "severity": self.severity,
            "source": self.source,
            "blocking": self.blocking,
            "review_required": self.review_required,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.node_name is not None:
            result["node_name"] = self.node_name
        if self.category is not None:
            result["category"] = self.category
        if self.reason is not None:
            result["reason"] = self.reason
        if self.review_item_id is not None:
            result["review_item_id"] = self.review_item_id
        return result


@dataclass(frozen=True)
class ValidationError(ValidationEntry):
    """A single validation error."""

    severity: str = "error"

    def __repr__(self) -> str:
        return (
            f"ValidationError(code={self.code!r}, message={self.message!r}, "
            f"line={self.line})"
        )


@dataclass(frozen=True)
class ValidationWarning(ValidationEntry):
    """A single validation warning."""

    severity: str = "warning"

    def __repr__(self) -> str:
        return (
            f"ValidationWarning(code={self.code!r}, message={self.message!r}, "
            f"line={self.line})"
        )


@dataclass(frozen=True)
class OntologyReviewQueueItem:
    """Value-only review proposal; review orchestration remains host-owned."""

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

    def to_dict(self) -> dict:
        result = {
            "proposal_id": self.proposal_id,
            "warning_code": self.warning_code,
            "action": self.action,
            "target": self.target,
            "rationale": self.rationale,
            "approval_state": self.approval_state,
            "requires_rule_approval": self.requires_rule_approval,
            "mutates_assets": self.mutates_assets,
            "alters_deterministic_outcome": self.alters_deterministic_outcome,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.node_name is not None:
            result["node_name"] = self.node_name
        if self.proposed_value is not None:
            result["proposed_value"] = self.proposed_value
        return result


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result of a deterministic validation run."""

    valid: bool
    errors: Tuple[ValidationError, ...] = ()
    warnings: Tuple[ValidationWarning, ...] = ()
    review_queue: Tuple[OntologyReviewQueueItem, ...] = ()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "review_queue": [item.to_dict() for item in self.review_queue],
        }

    def __repr__(self) -> str:
        return (
            f"ValidationResult(valid={self.valid}, errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )

