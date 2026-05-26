from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes.metadata_line import MetadataLine
from src.domain.tokens.token import Token


def test_fact_value_exposes_default_value_accessor():
    fact_value = FactValue("seed", FactValueType.STRING)

    assert fact_value.get_default_value() == "seed"

    fact_value.set_default_value("fallback")

    assert fact_value.get_default_value() == "fallback"


def test_metadata_line_sets_default_value_for_input_list_defaults():
    token = Token(
        tokens_list=["INPUT", "service history", "AS", "LIST", "IS", "true"],
        tokens_string_list=["U", "M", "AS", "L", "IS", "Bo"],
        tokens_string="U M AS L IS Bo",
    )

    metadata_line = MetadataLine("INPUT service history AS LIST IS true", token)
    fact_value = metadata_line.get_fact_value()

    assert fact_value.get_value_type() == FactValueType.LIST
    assert len(fact_value.get_value()) == 1
    assert fact_value.get_default_value() is fact_value.get_value()[0]
    assert fact_value.get_default_value().get_value() == "true"
