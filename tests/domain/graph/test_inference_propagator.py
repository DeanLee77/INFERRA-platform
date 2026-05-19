"""
Unit tests for IncrementalPropagator.

Validates:
- _compute_impacted_subgraph() delegates to graph.back_propagate()
- _topo_sort_subgraph() with graphlib.TopologicalSorter
- _can_evaluate_parent() AND/OR dependency checks
- forward_propagate_incremental() end-to-end
- Cache invalidation
"""

import pytest

from src.domain.fact_values import FactValue
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.inference_propagator import IncrementalPropagator
from src.domain.state import FactSource, LayeredFactStore


def _build_graph_with_chain():
    graph = HyperAdjacencyGraph()
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    graph.add_dependency_group("B", int(DependencyType.AND), {"C"})
    return graph


def _build_graph_with_diamond():
    graph = HyperAdjacencyGraph()
    graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
    graph.add_dependency_group("B", int(DependencyType.AND), {"D"})
    graph.add_dependency_group("C", int(DependencyType.AND), {"D"})
    return graph


def _build_graph_with_or():
    graph = HyperAdjacencyGraph()
    graph.add_dependency_group("A", int(DependencyType.OR), {"B", "C"})
    return graph


class TestComputeImpactedSubgraph:
    def test_single_change_finds_parents(self):
        graph = _build_graph_with_chain()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        result = prop._compute_impacted_subgraph({"C"})
        assert "B" in result
        assert "A" in result

    def test_diamond_deduplicates(self):
        graph = _build_graph_with_diamond()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        result = prop._compute_impacted_subgraph({"D"})
        assert result.count("A") <= 1

    def test_unknown_node_returns_empty(self):
        graph = HyperAdjacencyGraph()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        result = prop._compute_impacted_subgraph({"nonexistent"})
        assert len(result) == 0

    def test_empty_input_returns_empty(self):
        graph = _build_graph_with_chain()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        result = prop._compute_impacted_subgraph(set())
        assert len(result) == 0


class TestTopoSortSubgraph:
    def test_empty_subgraph(self):
        graph = HyperAdjacencyGraph()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        result = prop._topo_sort_subgraph(set(), {})
        assert result == []

    def test_single_node(self):
        graph = HyperAdjacencyGraph()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        result = prop._topo_sort_subgraph({"A"}, {})
        assert result == ["A"]

    def test_diamond_dependency(self):
        graph = _build_graph_with_diamond()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        nodes = {"A", "B", "C", "D"}
        child_map = {n: graph.get_child_groups(n) for n in nodes}
        result = prop._topo_sort_subgraph(nodes, child_map)
        assert result.index("B") < result.index("A")
        assert result.index("C") < result.index("A")
        assert result.index("D") < result.index("B")
        assert result.index("D") < result.index("C")

    def test_disconnected_components(self):
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        nodes = {"A", "B", "C", "D"}
        child_map = {n: graph.get_child_groups(n) for n in nodes}
        result = prop._topo_sort_subgraph(nodes, child_map)
        assert set(result) == nodes
        assert result.index("B") < result.index("A")

    def test_cycle_raises(self):
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
        graph.add_dependency_group("B", int(DependencyType.AND), {"A"})
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        nodes = {"A", "B"}
        child_map = {n: graph.get_child_groups(n) for n in nodes}
        import graphlib as gl
        with pytest.raises(gl.CycleError):
            prop._topo_sort_subgraph(nodes, child_map)

    def test_cache_hit(self):
        graph = _build_graph_with_diamond()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        nodes = {"A", "B", "C", "D"}
        child_map = {n: graph.get_child_groups(n) for n in nodes}
        result1 = prop._topo_sort_subgraph(nodes, child_map)
        result2 = prop._topo_sort_subgraph(nodes, child_map)
        assert result1 == result2


class TestCanEvaluateParent:
    def test_and_all_children_present(self):
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        store = LayeredFactStore()
        store.set_fact("B", FactValue(True), FactSource.ASSERTED)
        store.set_fact("C", FactValue(True), FactSource.ASSERTED)
        prop = IncrementalPropagator(graph, store)
        assert prop._can_evaluate_parent("A") is True

    def test_and_missing_child(self):
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        store = LayeredFactStore()
        store.set_fact("B", FactValue(True), FactSource.ASSERTED)
        prop = IncrementalPropagator(graph, store)
        assert prop._can_evaluate_parent("A") is False

    def test_or_at_least_one_child(self):
        graph = _build_graph_with_or()
        store = LayeredFactStore()
        store.set_fact("B", FactValue(True), FactSource.ASSERTED)
        prop = IncrementalPropagator(graph, store)
        assert prop._can_evaluate_parent("A") is True

    def test_or_no_children(self):
        graph = _build_graph_with_or()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        assert prop._can_evaluate_parent("A") is False


class TestForwardPropagateIncremental:
    def test_propagates_change_through_chain(self):
        graph = _build_graph_with_chain()
        store = LayeredFactStore()
        store.set_fact("C", FactValue(True), FactSource.ASSERTED)
        prop = IncrementalPropagator(graph, store)
        prop.forward_propagate_incremental({"C"})
        assert store.get_unified_view().get("B") is not None

    def test_no_change_no_op(self):
        graph = _build_graph_with_chain()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        prop.forward_propagate_incremental(set())

    def test_and_propagation_true(self):
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        store = LayeredFactStore()
        store.set_fact("B", FactValue(True), FactSource.ASSERTED)
        store.set_fact("C", FactValue(True), FactSource.ASSERTED)
        prop = IncrementalPropagator(graph, store)
        prop.forward_propagate_incremental({"B", "C"})
        assert store.peek_in_layer("A", FactSource.INFERRED) is not None

    def test_or_propagation_one_true(self):
        graph = _build_graph_with_or()
        store = LayeredFactStore()
        store.set_fact("B", FactValue(True), FactSource.ASSERTED)
        prop = IncrementalPropagator(graph, store)
        prop.forward_propagate_incremental({"B"})
        assert store.peek_in_layer("A", FactSource.INFERRED) is not None


class TestCacheInvalidation:
    def test_invalidate_cache_clears(self):
        graph = _build_graph_with_diamond()
        store = LayeredFactStore()
        prop = IncrementalPropagator(graph, store)
        nodes = {"A", "B", "C", "D"}
        child_map = {n: graph.get_child_groups(n) for n in nodes}
        prop._topo_sort_subgraph(nodes, child_map)
        assert len(prop._topo_cache) == 1
        prop.invalidate_cache()
        assert len(prop._topo_cache) == 0
