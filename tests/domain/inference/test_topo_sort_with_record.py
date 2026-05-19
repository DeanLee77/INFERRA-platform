"""
Tests for HistoryRecord, InMemoryHistoryRecordStore, and
TopologicalSort.dfs_topological_sort_with_record.
"""

from unittest.mock import MagicMock

import pytest

from src.domain.nodes.record import HistoryRecord
from src.domain.inference.topo_sort import TopologicalSort
from src.domain.graph.dependency_type import DependencyType
from src.ports.history_record_store_port import HistoryRecordStorePort
from src.adapters.outbound.persistence.in_memory_history_record_store import InMemoryHistoryRecordStore


class TestHistoryRecord:
    def test_default_counts_are_zero(self):
        r = HistoryRecord(name="age")
        assert r.true_count == 0
        assert r.false_count == 0
        assert r.total == 0

    def test_initial_counts(self):
        r = HistoryRecord(name="age", true_count=7, false_count=3)
        assert r.total == 10
        assert r.true_rate == pytest.approx(0.7)
        assert r.false_rate == pytest.approx(0.3)

    def test_zero_total_rate_is_zero(self):
        r = HistoryRecord(name="x")
        assert r.true_rate == 0.0
        assert r.false_rate == 0.0

    def test_with_increment_true(self):
        r = HistoryRecord(name="age", true_count=5, false_count=2)
        r2 = r.with_increment(is_true=True)
        assert r2.true_count == 6
        assert r2.false_count == 2
        assert r.true_count == 5  # original immutable

    def test_with_increment_false(self):
        r = HistoryRecord(name="age", true_count=5, false_count=2)
        r2 = r.with_increment(is_true=False)
        assert r2.true_count == 5
        assert r2.false_count == 3

    def test_frozen_dataclass(self):
        r = HistoryRecord(name="age", true_count=1)
        with pytest.raises(AttributeError):
            r.true_count = 99

    def test_repr(self):
        r = HistoryRecord(name="age", true_count=3, false_count=1)
        assert '"true": 3' in repr(r)
        assert '"false": 1' in repr(r)


class TestInMemoryHistoryRecordStore:
    def test_get_records_empty(self):
        store = InMemoryHistoryRecordStore()
        assert store.get_records("rule1") == {}

    def test_update_and_get_record(self):
        store = InMemoryHistoryRecordStore()
        r = HistoryRecord(name="age", true_count=5, false_count=2)
        store.update_record("rule1", r)
        assert store.get_record("rule1", "age") == r

    def test_get_records_returns_copy(self):
        store = InMemoryHistoryRecordStore()
        store.update_record("rule1", HistoryRecord(name="a", true_count=1))
        records = store.get_records("rule1")
        records["a"] = HistoryRecord(name="a", true_count=99)
        assert store.get_record("rule1", "a").true_count == 1

    def test_clear_specific_rule(self):
        store = InMemoryHistoryRecordStore()
        store.update_record("rule1", HistoryRecord(name="a"))
        store.update_record("rule2", HistoryRecord(name="b"))
        store.clear("rule1")
        assert store.get_record("rule1", "a") is None
        assert store.get_record("rule2", "b") is not None

    def test_clear_all(self):
        store = InMemoryHistoryRecordStore()
        store.update_record("rule1", HistoryRecord(name="a"))
        store.update_record("rule2", HistoryRecord(name="b"))
        store.clear()
        assert store.get_records("rule1") == {}
        assert store.get_records("rule2") == {}

    def test_is_instance_of_port(self):
        store = InMemoryHistoryRecordStore()
        assert isinstance(store, HistoryRecordStorePort)


def _make_node(name: str, node_id: int) -> MagicMock:
    node = MagicMock()
    node.get_node_name.return_value = name
    node.get_node_id.return_value = node_id
    node.__repr__ = lambda self: f"MockNode({name}, id={node_id})"
    return node


def _build_simple_or_graph():
    """
    root -> (OR) -> a, b
    a and b have no children.
    """
    root = _make_node("root", 0)
    a = _make_node("a", 1)
    b = _make_node("b", 2)

    node_dict = {"root": root, "a": a, "b": b}
    id_dict = {0: "root", 1: "a", 2: "b"}

    or_dep = DependencyType.get_or()
    matrix = [
        [-1, or_dep, or_dep],
        [-1, -1, -1],
        [-1, -1, -1],
    ]
    return node_dict, id_dict, matrix


def _build_simple_and_graph():
    """
    root -> (AND) -> a, b
    a and b have no children.
    """
    root = _make_node("root", 0)
    a = _make_node("a", 1)
    b = _make_node("b", 2)

    node_dict = {"root": root, "a": a, "b": b}
    id_dict = {0: "root", 1: "a", 2: "b"}

    and_dep = DependencyType.get_and()
    matrix = [
        [-1, and_dep, and_dep],
        [-1, -1, -1],
        [-1, -1, -1],
    ]
    return node_dict, id_dict, matrix


def _build_chain_graph():
    """
    root -> (OR) -> mid -> (OR) -> leaf
    """
    root = _make_node("root", 0)
    mid = _make_node("mid", 1)
    leaf = _make_node("leaf", 2)

    node_dict = {"root": root, "mid": mid, "leaf": leaf}
    id_dict = {0: "root", 1: "mid", 2: "leaf"}

    or_dep = DependencyType.get_or()
    matrix = [
        [-1, or_dep, -1],
        [-1, -1, or_dep],
        [-1, -1, -1],
    ]
    return node_dict, id_dict, matrix


def _build_branching_chain_graph():
    """
    root -> (OR) -> mid, sibling
    mid -> (OR) -> leaf
    """
    root = _make_node("root", 0)
    mid = _make_node("mid", 1)
    sibling = _make_node("sibling", 2)
    leaf = _make_node("leaf", 3)

    node_dict = {"root": root, "mid": mid, "sibling": sibling, "leaf": leaf}
    id_dict = {0: "root", 1: "mid", 2: "sibling", 3: "leaf"}

    or_dep = DependencyType.get_or()
    matrix = [
        [-1, or_dep, or_dep, -1],
        [-1, -1, -1, or_dep],
        [-1, -1, -1, -1],
        [-1, -1, -1, -1],
    ]
    return node_dict, id_dict, matrix


class TestDfsTopologicalSortWithRecord:
    def test_falls_back_to_deterministic_dfs_when_no_records(self):
        node_dict, id_dict, matrix = _build_simple_or_graph()
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, {}
        )
        assert len(result) == 3
        names = [n.get_node_name() for n in result]
        assert "root" in names
        assert "a" in names
        assert "b" in names

    def test_or_rule_visits_most_positive_first(self):
        node_dict, id_dict, matrix = _build_simple_or_graph()
        records = {
            "a": HistoryRecord(name="a", true_count=9, false_count=1),
            "b": HistoryRecord(name="b", true_count=1, false_count=9),
        }
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        names = [n.get_node_name() for n in result]
        assert names[1] == "a"  # a has higher true_rate, visited first

    def test_and_rule_visits_most_negative_first(self):
        node_dict, id_dict, matrix = _build_simple_and_graph()
        records = {
            "a": HistoryRecord(name="a", true_count=9, false_count=1),
            "b": HistoryRecord(name="b", true_count=1, false_count=9),
        }
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        names = [n.get_node_name() for n in result]
        assert names[1] == "b"  # b has higher false_rate, visited first

    def test_chain_graph_with_records(self):
        node_dict, id_dict, matrix = _build_chain_graph()
        records = {
            "mid": HistoryRecord(name="mid", true_count=5, false_count=1),
            "leaf": HistoryRecord(name="leaf", true_count=1, false_count=5),
        }
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        assert len(result) == 3
        names = [n.get_node_name() for n in result]
        assert names == ["root", "mid", "leaf"]

    def test_branching_chain_uses_depth_first_history_path(self):
        node_dict, id_dict, matrix = _build_branching_chain_graph()
        records = {
            "mid": HistoryRecord(name="mid", true_count=9, false_count=1),
            "sibling": HistoryRecord(name="sibling", true_count=1, false_count=9),
            "leaf": HistoryRecord(name="leaf", true_count=5, false_count=5),
        }

        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )

        names = [n.get_node_name() for n in result]
        assert names == ["root", "mid", "leaf", "sibling"]

    def test_missing_record_treated_as_zero(self):
        node_dict, id_dict, matrix = _build_simple_or_graph()
        records = {
            "a": HistoryRecord(name="a", true_count=8, false_count=2),
        }
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        names = [n.get_node_name() for n in result]
        assert names[1] == "a"

    def test_all_zero_records_treats_equally(self):
        node_dict, id_dict, matrix = _build_simple_or_graph()
        records = {
            "a": HistoryRecord(name="a"),
            "b": HistoryRecord(name="b"),
        }
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        assert len(result) == 3

    def test_prefix_lookup_with_not_dependency(self):
        node_dict, id_dict, matrix = _build_simple_or_graph()
        not_dep = DependencyType.get_not()
        or_dep = DependencyType.get_or()
        matrix[0][1] = or_dep | not_dep
        matrix[0][2] = or_dep

        records = {
            "nota": HistoryRecord(name="nota", true_count=0, false_count=10),
            "b": HistoryRecord(name="b", true_count=5, false_count=5),
        }
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        assert len(result) == 3


class TestMlOptimizedDfsFeatureFlag:
    def test_default_is_false(self):
        from src.domain.state.feature_flags import FeatureFlags
        flags = FeatureFlags()
        assert flags.ml_optimized_dfs is False

    def test_can_enable(self):
        from src.domain.state.feature_flags import FeatureFlags
        flags = FeatureFlags(ml_optimized_dfs=True)
        assert flags.ml_optimized_dfs is True

    def test_env_var(self):
        import os
        from src.domain.state.feature_flags import FeatureFlags
        os.environ["INFERRA_ML_OPTIMIZED_DFS"] = "true"
        try:
            flags = FeatureFlags()
            assert flags.ml_optimized_dfs is True
        finally:
            del os.environ["INFERRA_ML_OPTIMIZED_DFS"]

    def test_snapshot_includes_flag(self):
        from src.domain.state.feature_flags import FeatureFlags
        flags = FeatureFlags(ml_optimized_dfs=True)
        assert flags.snapshot()["ml_optimized_dfs"] is True
