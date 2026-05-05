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
