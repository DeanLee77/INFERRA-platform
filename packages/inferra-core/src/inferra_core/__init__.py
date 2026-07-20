"""Supported public facade for the internal INFERRA Core distribution."""

from ._version import CORE_VERSION, __version__
from .diagnostics import (
    OntologyReviewQueueItem,
    ValidationEntry,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from .graph import DependencyGroup, DependencyType
from .ports import (
    DependencyGraphPort,
    FactStorePort,
    HistoryRecordStorePort,
    IterationPort,
    QuestionStrategyPort,
)
from .records import HistoryRecord
from .values import FactSource, FactValue, FactValueType

__all__ = [
    "CORE_VERSION",
    "DependencyGroup",
    "DependencyGraphPort",
    "DependencyType",
    "FactSource",
    "FactStorePort",
    "FactValue",
    "FactValueType",
    "HistoryRecord",
    "HistoryRecordStorePort",
    "IterationPort",
    "OntologyReviewQueueItem",
    "QuestionStrategyPort",
    "ValidationEntry",
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
    "__version__",
]
