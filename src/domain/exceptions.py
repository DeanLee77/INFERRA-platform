"""
INFERRA domain exceptions.

Custom exception classes for cross-cutting domain errors that don't belong
to a single module.
"""

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.services.rule_validation_service import ValidationError


class RuleValidationError(ValueError):
    """
    Raised when rule text fails validation and cannot be persisted.

    Carries the full list of ValidationErrors so callers (API layer,
    logging, CLI) can report structured error details without re-running
    validation.

    Inherits from ValueError for compatibility with the existing
    exception_handler(ValueError) in main.py, which returns 400.
    Callers that need 422 semantics should catch this type specifically
    before the generic ValueError handler.
    """

    def __init__(
        self,
        errors: List["ValidationError"],
        rule_name: str = "",
        unknown_waiver_ids: Optional[List[str]] = None,
    ) -> None:
        self.errors = errors
        self.rule_name = rule_name
        self.unknown_waiver_ids = unknown_waiver_ids or []
        summary_parts = []
        if self.unknown_waiver_ids:
            summary_parts.append(
                f"unknown waiver IDs: {', '.join(sorted(self.unknown_waiver_ids))}"
            )
        summary_parts.append("; ".join(f"[{e.code}] {e.message}" for e in errors))
        summary = " | ".join(part for part in summary_parts if part)
        super().__init__(
            f"Rule validation failed for '{rule_name}': {summary}"
            if rule_name
            else f"Rule validation failed: {summary}"
        )

    def to_dict(self) -> dict:
        """Structured representation for API responses."""
        result = {
            "success": False,
            "error": "Rule validation failed",
            "detail": {
                "rule_name": self.rule_name,
                "errors": [e.to_dict() for e in self.errors],
            },
        }
        if self.unknown_waiver_ids:
            result["detail"]["unknown_waiver_ids"] = sorted(self.unknown_waiver_ids)
        return result


class ConcurrentModificationError(RuntimeError):
    """
    Raised when a persisted session write is based on a stale version.

    Callers should re-read the session, re-apply their change to the fresh
    version, and retry the write.
    """
