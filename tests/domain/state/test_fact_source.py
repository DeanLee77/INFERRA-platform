from src.domain.state import FactSource


def test_fact_source_has_three_distinct_layers():
    assert {member.value for member in FactSource} == {
        "ASSERTED",
        "INFERRED",
        "LEARNED",
        "HYPOTHETICAL",
        "SEMANTIC",
    }


def test_fact_source_members_are_distinct():
    assert FactSource.ASSERTED != FactSource.INFERRED
    assert FactSource.INFERRED != FactSource.LEARNED
    assert FactSource.LEARNED != FactSource.HYPOTHETICAL
    assert FactSource.HYPOTHETICAL != FactSource.SEMANTIC
    assert FactSource.INFERRED != FactSource.SEMANTIC
    assert FactSource.ASSERTED != FactSource.SEMANTIC


def test_fact_source_from_value_accepts_enum_and_string_values():
    assert FactSource.from_value(FactSource.ASSERTED) is FactSource.ASSERTED
    assert FactSource.from_value("HYPOTHETICAL") is FactSource.HYPOTHETICAL


def test_fact_source_from_value_defaults_unknown_future_values_to_inferred():
    assert FactSource.from_value("FUTURE_SOURCE") is FactSource.INFERRED
    assert FactSource.from_value(None) is FactSource.INFERRED
