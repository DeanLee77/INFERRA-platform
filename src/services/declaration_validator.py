"""Compatibility imports for Core-owned declaration validation."""

from inferra_core._internal.services.declaration_validator import (
    DECLARATION_VALIDATION_INTERNAL_ERROR,
    DUPLICATE_DECLARATION,
    NULL_NODESET,
    SELF_REFERENTIAL_RULE,
    UNDECLARED_REFERENCE,
    UNUSED_DECLARATION,
    DeclarationFinding,
    DeclarationValidationResult,
    DeclarationValidator,
    validate_declarations,
)

__all__ = [
    "DECLARATION_VALIDATION_INTERNAL_ERROR",
    "DUPLICATE_DECLARATION",
    "NULL_NODESET",
    "SELF_REFERENTIAL_RULE",
    "UNDECLARED_REFERENCE",
    "UNUSED_DECLARATION",
    "DeclarationFinding",
    "DeclarationValidationResult",
    "DeclarationValidator",
    "validate_declarations",
]
