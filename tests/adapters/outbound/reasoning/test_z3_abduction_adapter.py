import sys
from unittest.mock import MagicMock, patch

from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.fact_values import FactValue
from src.domain.graph.dependency_type import DependencyType
from src.ports.abduction_port import AbductionPort


def test_z3_abduction_adapter_implements_port_and_finds_missing_leaf():
    adapter = Z3AbductionAdapter(timeout_ms=200, max_models=10)
    snapshot = {
        "child_groups": {
            "goal": ((int(DependencyType.AND), ("known", "missing")),),
        }
    }

    hypotheses = adapter.propose_hypotheses(
        "goal",
        {"known": FactValue(True)},
        snapshot,
    )

    assert isinstance(adapter, AbductionPort)
    assert hypotheses[0]["fact_name"] == "missing"
    assert hypotheses[0]["suggested_value"] == "true"
    assert hypotheses[0]["dependency_path"] == ["goal", "missing"]


def test_z3_abduction_adapter_respects_max_models():
    adapter = Z3AbductionAdapter(timeout_ms=200, max_models=1)
    snapshot = {
        "child_groups": {
            "goal": ((int(DependencyType.OR), ("a", "b")),),
        }
    }

    hypotheses = adapter.propose_hypotheses("goal", {}, snapshot)

    assert len(hypotheses) == 1


def test_z3_abduction_adapter_returns_empty_when_goal_known():
    adapter = Z3AbductionAdapter(timeout_ms=200)

    assert adapter.propose_hypotheses("goal", {"goal": FactValue(True)}, {}) == []


def test_z3_abduction_adapter_returns_empty_when_z3_missing():
    adapter = Z3AbductionAdapter(timeout_ms=200)

    with patch.dict(sys.modules, {"z3": None}):
        assert adapter.propose_hypotheses("goal", {}, {}) == []


def test_z3_abduction_adapter_handles_depth_guard_and_cycles():
    adapter = Z3AbductionAdapter(timeout_ms=200, depth_guard=0)
    snapshot = {
        "child_groups": {
            "goal": ((int(DependencyType.AND), ("child",)),),
            "child": ((int(DependencyType.AND), ("goal",)),),
        }
    }

    assert adapter._candidate_leaves("goal", snapshot["child_groups"], {}) == []
    assert adapter._path_to("goal", "missing", snapshot["child_groups"]) == ["missing"]


def test_z3_abduction_adapter_known_bool_accepts_raw_bool_and_fact_value():
    assert Z3AbductionAdapter._known_bool(True) is True
    assert Z3AbductionAdapter._known_bool(FactValue(False)) is False
    assert Z3AbductionAdapter._known_bool("yes") is None


def test_z3_abduction_adapter_confidence_decreases_with_path_length():
    adapter = Z3AbductionAdapter(timeout_ms=200)
    snapshot = {
        "goal": ((int(DependencyType.AND), ("mid",)),),
        "mid": ((int(DependencyType.AND), ("leaf",)),),
    }

    assert adapter._confidence_for("leaf", "goal", snapshot) == 0.85
