import pytest

from src.domain.fact_values import FactValue
from src.domain.session import InferenceContext
from src.domain.state import FactSource, LayeredFactStore
from src.domain.trace import ProvOTraceGenerator

rdflib = pytest.importorskip("rdflib")


def test_prov_o_trace_generator_outputs_parseable_turtle():
    store = LayeredFactStore()
    store.set_fact("goal", FactValue(True), FactSource.INFERRED)
    ctx = InferenceContext(
        session_id="s1",
        rule_name="benefit_rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )

    turtle = ProvOTraceGenerator().generate(ctx, output_format="turtle")

    graph = rdflib.Graph()
    graph.parse(data=turtle, format="turtle")
    assert len(graph) > 0
    assert "benefit_rule" in turtle


def test_prov_o_trace_generator_supports_json_ld():
    store = LayeredFactStore()
    store.set_fact("goal", FactValue(True), FactSource.ASSERTED)
    ctx = InferenceContext(
        session_id="s1",
        rule_name="benefit_rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )

    payload = ProvOTraceGenerator().generate(ctx, output_format="json-ld")

    assert "ASSERTED" in payload
