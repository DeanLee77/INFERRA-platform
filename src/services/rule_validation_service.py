"""Platform host wrapper for deterministic Core rule validation.

The validation algorithm and diagnostics are Core-owned. Platform supplies the
system clock solely for its process-local TTL/LRU optimisation; the same Core
class runs without a clock (and therefore without a cache) in deterministic
embedded use.
"""

import time
from typing import Iterable, Optional

from inferra_core import (
    OntologyReviewQueueItem,
    ValidationEntry,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from inferra_core._internal.services.rule_validation_service import (
    RuleValidationService as _CoreRuleValidationService,
)
from inferra_core._internal._logging import get_logger


# Temporary compatibility hook for benchmark/test logger patching. Validation
# itself runs in Core and emits no operational logs.
_logger = get_logger("inferra.rule_validation")


class RuleValidationService(_CoreRuleValidationService):
    """Configure the Core validator with Platform's operational clock."""

    def __init__(
        self,
        cache_maxsize: int = 512,
        cache_ttl_seconds: int = 300,
        enable_node_set_validation: bool = True,
        enable_ontology_advisory_validation: bool = True,
        ontology_blocking_warning_codes: Optional[Iterable[str]] = None,
    ) -> None:
        super().__init__(
            cache_maxsize=cache_maxsize,
            cache_ttl_seconds=cache_ttl_seconds,
            enable_node_set_validation=enable_node_set_validation,
            enable_ontology_advisory_validation=enable_ontology_advisory_validation,
            ontology_blocking_warning_codes=ontology_blocking_warning_codes,
            clock=time.time,
        )


__all__ = [
    "OntologyReviewQueueItem",
    "RuleValidationService",
    "ValidationEntry",
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
]
