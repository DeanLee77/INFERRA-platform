from src.adapters.outbound.reasoning.mock_abduction_adapter import MockAbductionAdapter
from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.graph.dependency_type import DependencyType
from src.domain.reasoning.hypothesis import Hypothesis
from src.ports.abduction_port import AbductionPort


def test_null_abduction_adapter_implements_port():
    adapter = NullAbductionAdapter()

    assert isinstance(adapter, AbductionPort)
    assert adapter.propose_hypotheses("goal", {}, {}) == []


def test_mock_abduction_adapter_returns_primitive_hypotheses():
    adapter = MockAbductionAdapter(
        [Hypothesis("missing_fact", "true", 0.9, ["goal", "missing_fact"])]
    )

    result = adapter.propose_hypotheses("goal", {}, {})

    assert isinstance(adapter, AbductionPort)
    assert result == [
        {
            "fact_name": "missing_fact",
            "suggested_value": "true",
            "confidence": 0.9,
            "dependency_path": ["goal", "missing_fact"],
            "ontology_consistent": True,
        }
    ]


def test_z3_abduction_adapter_implements_port():
    adapter = Z3AbductionAdapter(timeout_ms=200, max_models=5)

    result = adapter.propose_hypotheses(
        "goal",
        {"known": True},
        {"child_groups": {"goal": ((int(DependencyType.AND), ("known", "missing")),)}},
    )

    assert isinstance(adapter, AbductionPort)
    assert result[0]["fact_name"] == "missing"
