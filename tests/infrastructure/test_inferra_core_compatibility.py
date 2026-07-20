"""Contract tests for the temporary Platform-to-Core compatibility layer."""

import pickle

import inferra_core
import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.dependency_group import DependencyGroup
from src.domain.graph.dependency_type import DependencyType
from src.domain.nodes.record import HistoryRecord
from src.domain.state.fact_source import FactSource
from src.ports.dependency_graph_port import DependencyGraphPort
from src.ports.fact_store_port import FactStorePort
from src.ports.history_record_store_port import HistoryRecordStorePort
from src.ports.iteration_port import IterationPort
from src.ports.question_strategy_port import QuestionStrategyPort
from src.services.declaration_validator import DeclarationValidator
from src.services.rule_validation_service import (
    OntologyReviewQueueItem,
    ValidationEntry,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    RuleValidationService,
)
from inferra_core._internal.services.declaration_validator import (
    DeclarationValidator as CoreDeclarationValidator,
)
from inferra_core._internal.services.rule_validation_service import (
    RuleValidationService as CoreRuleValidationService,
)


def test_legacy_platform_paths_reexport_exact_core_classes() -> None:
    compatibility_pairs = (
        (FactValue, inferra_core.FactValue),
        (FactValueType, inferra_core.FactValueType),
        (FactSource, inferra_core.FactSource),
        (DependencyType, inferra_core.DependencyType),
        (DependencyGroup, inferra_core.DependencyGroup),
        (HistoryRecord, inferra_core.HistoryRecord),
        (DependencyGraphPort, inferra_core.DependencyGraphPort),
        (FactStorePort, inferra_core.FactStorePort),
        (HistoryRecordStorePort, inferra_core.HistoryRecordStorePort),
        (IterationPort, inferra_core.IterationPort),
        (QuestionStrategyPort, inferra_core.QuestionStrategyPort),
        (ValidationEntry, inferra_core.ValidationEntry),
        (ValidationError, inferra_core.ValidationError),
        (ValidationWarning, inferra_core.ValidationWarning),
        (OntologyReviewQueueItem, inferra_core.OntologyReviewQueueItem),
        (ValidationResult, inferra_core.ValidationResult),
    )

    assert all(legacy is core for legacy, core in compatibility_pairs)
    assert all(item.__module__.startswith("inferra_core.") for item, _ in compatibility_pairs)


def test_platform_hosts_core_validation_without_moving_clock_policy_into_core() -> None:
    assert DeclarationValidator is CoreDeclarationValidator
    assert issubclass(RuleValidationService, CoreRuleValidationService)
    assert CoreRuleValidationService()._clock is None
    assert RuleValidationService()._clock is not None


@pytest.mark.parametrize(
    ("legacy_global", "expected"),
    (
        (b"csrc.domain.fact_values.fact_value\nFactValue\n.", inferra_core.FactValue),
        (
            b"csrc.domain.fact_values.fact_value_type\nFactValueType\n.",
            inferra_core.FactValueType,
        ),
        (b"csrc.domain.state.fact_source\nFactSource\n.", inferra_core.FactSource),
        (
            b"csrc.domain.graph.dependency_type\nDependencyType\n.",
            inferra_core.DependencyType,
        ),
        (
            b"csrc.domain.graph.dependency_group\nDependencyGroup\n.",
            inferra_core.DependencyGroup,
        ),
        (b"csrc.domain.nodes.record\nHistoryRecord\n.", inferra_core.HistoryRecord),
        (
            b"csrc.services.rule_validation_service\nValidationResult\n.",
            inferra_core.ValidationResult,
        ),
    ),
)
def test_legacy_pickle_globals_resolve_to_core_classes(
    legacy_global: bytes,
    expected: type,
) -> None:
    assert pickle.loads(legacy_global) is expected
