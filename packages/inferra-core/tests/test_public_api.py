"""Package-only tests for the first internal Core distribution slice."""

from abc import ABCMeta
from importlib.metadata import version

import inferra_core
from inferra_core import (
    CORE_VERSION,
    DependencyGraphPort,
    DependencyGroup,
    DependencyType,
    FactSource,
    FactStorePort,
    FactValue,
    FactValueType,
    HistoryRecord,
    HistoryRecordStorePort,
    IterationPort,
    OntologyReviewQueueItem,
    QuestionStrategyPort,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)


EXPECTED_PUBLIC_API = {
    "CORE_VERSION",
    "DependencyGraphPort",
    "DependencyGroup",
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
}


def test_public_facade_and_distribution_version_are_explicit() -> None:
    assert set(inferra_core.__all__) == EXPECTED_PUBLIC_API
    assert inferra_core.__version__ == CORE_VERSION == "0.1.1"
    assert version("inferra-core") == CORE_VERSION


def test_fact_value_inference_and_mutation_match_frozen_behavior() -> None:
    assert FactValue(True).get_value_type() is FactValueType.BOOLEAN
    assert FactValue(1).get_value_type() is FactValueType.INTEGER
    assert FactValue(1.5).get_value_type() is FactValueType.DOUBLE
    assert FactValue([]).get_value_type() is FactValueType.LIST
    assert FactValue("x").get_value_type() is FactValueType.STRING
    assert FactValue(None).get_value_type() is FactValueType.UNKNOWN

    fact = FactValue("current", FactValueType.TEXT)
    fact.set_value("changed")
    fact.set_default_value("default")
    assert fact.get_value() == "changed"
    assert fact.get_default_value() == "default"
    assert fact.get_value_type() is FactValueType.TEXT


def test_fact_source_parses_known_and_unknown_persisted_values() -> None:
    assert FactSource.from_value(FactSource.ASSERTED) is FactSource.ASSERTED
    assert FactSource.from_value("SEMANTIC") is FactSource.SEMANTIC
    assert FactSource.from_value("FUTURE_SOURCE") is FactSource.INFERRED


def test_dependency_values_remain_hashable_and_bit_compatible() -> None:
    combined = DependencyType.MANDATORY | DependencyType.AND
    group = DependencyGroup(combined, frozenset({"a", "b"}))

    assert int(combined) == 72
    assert group in {group}
    assert DependencyType.get_dependency_array() == [8, 4, 2, 1, 64, 32, 16]


def test_history_record_is_pure_and_immutable() -> None:
    record = HistoryRecord("eligible", true_count=2, false_count=1)

    assert record.total == 3
    assert record.true_rate == 2 / 3
    assert record.false_rate == 1 / 3
    assert record.with_increment(True) == HistoryRecord("eligible", 3, 1)
    assert record.with_increment(False) == HistoryRecord("eligible", 2, 2)
    assert repr(record) == '{"name": "eligible", "true": 2, "false": 1}'


def test_diagnostics_retain_stable_serialization() -> None:
    error = ValidationError("INVALID", "invalid rule", line=4, node_name="age")
    warning = ValidationWarning("REVIEW", "review this")
    proposal = OntologyReviewQueueItem(
        proposal_id="proposal-1",
        warning_code="REVIEW",
        action="map",
        target="age",
        rationale="candidate mapping",
    )
    result = ValidationResult(
        valid=False,
        errors=(error,),
        warnings=(warning,),
        review_queue=(proposal,),
    )

    assert error.waiver_id == "INVALID:age"
    assert result.to_dict() == {
        "valid": False,
        "errors": [error.to_dict()],
        "warnings": [warning.to_dict()],
        "review_queue": [proposal.to_dict()],
    }


def test_core_ports_preserve_the_abcmeta_contract() -> None:
    ports = (
        DependencyGraphPort,
        FactStorePort,
        HistoryRecordStorePort,
        IterationPort,
        QuestionStrategyPort,
    )

    assert all(isinstance(port, ABCMeta) for port in ports)
    assert all(port.__abstractmethods__ for port in ports)
