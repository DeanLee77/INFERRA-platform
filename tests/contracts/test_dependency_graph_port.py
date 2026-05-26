"""
DependencyGraphPort contract test suite.

Parametrised over every concrete implementation of DependencyGraphPort.
Any new implementation must pass every test in this file — this is the
behavioural contract that guarantees interchangeability across the port.

Add new implementations to the IMPLEMENTATIONS list below.

Phase 2 §4.9: Tests validate ABCMeta + primitive return types.
"""

from collections import deque
from typing import Type

import pytest

from src.domain.graph.hyper_adjacency_graph import CyclicGraphError, HyperAdjacencyGraph
from src.domain.graph.dependency_type import DependencyType
from src.ports.dependency_graph_port import DependencyGraphPort


IMPLEMENTATIONS: list[Type[DependencyGraphPort]] = [
    HyperAdjacencyGraph,
]


@pytest.fixture(params=IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def graph(request) -> DependencyGraphPort:
    """Provide a fresh DependencyGraphPort implementation for each test."""
    return request.param()


# ===================================================================
# 1. add_dependency_group — edge insertion
# ===================================================================


def test_add_dependency_group_adds_edges(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
    assert graph.has_node("A")
    assert graph.has_node("B")
    assert graph.has_node("C")


def test_add_dependency_group_empty_children(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), set())
    assert graph.has_node("A")


def test_add_dependency_group_multiple_groups_same_parent(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    graph.add_dependency_group("A", int(DependencyType.OR), {"C"})
    groups = graph.get_child_groups("A")
    assert len(groups) == 2


# ===================================================================
# 2. get_parent_edges — returns Set[str]
# ===================================================================


def test_get_parent_edges_returns_set(graph):
    graph.add_dependency_group("P", int(DependencyType.AND), {"C"})
    result = graph.get_parent_edges("C")
    assert isinstance(result, set)
    assert "P" in result


def test_get_parent_edges_no_parents(graph):
    graph.add_dependency_group("P", int(DependencyType.AND), {"C"})
    result = graph.get_parent_edges("P")
    assert isinstance(result, set)
    assert len(result) == 0


def test_get_parent_edges_multiple_parents(graph):
    graph.add_dependency_group("P1", int(DependencyType.AND), {"C"})
    graph.add_dependency_group("P2", int(DependencyType.OR), {"C"})
    result = graph.get_parent_edges("C")
    assert result == {"P1", "P2"}


def test_get_parent_edges_unknown_node(graph):
    result = graph.get_parent_edges("nonexistent")
    assert isinstance(result, set)
    assert len(result) == 0


# ===================================================================
# 3. get_child_groups — returns primitive tuples
# ===================================================================


def test_get_child_groups_returns_primitive_tuples(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
    groups = graph.get_child_groups("A")
    assert isinstance(groups, tuple)
    assert len(groups) == 1
    dep_type_int, children_tuple = groups[0]
    assert isinstance(dep_type_int, int)
    assert isinstance(children_tuple, tuple)
    assert set(children_tuple) == {"B", "C"}


def test_get_child_groups_multiple_groups(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    graph.add_dependency_group("A", int(DependencyType.OR), {"C"})
    groups = graph.get_child_groups("A")
    assert len(groups) == 2
    types = {g[0] for g in groups}
    assert int(DependencyType.AND) in types
    assert int(DependencyType.OR) in types


def test_get_child_groups_no_children(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), set())
    groups = graph.get_child_groups("A")
    assert isinstance(groups, tuple)
    assert len(groups) == 0


def test_get_child_groups_unknown_node(graph):
    groups = graph.get_child_groups("nonexistent")
    assert isinstance(groups, tuple)
    assert len(groups) == 0


# ===================================================================
# 4. back_propagate — returns Deque[str] with cycle guard
# ===================================================================


def test_back_propagate_returns_deque(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.back_propagate("B")
    assert isinstance(result, deque)


def test_back_propagate_finds_parents(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.back_propagate("B")
    assert "A" in result


def test_back_propagate_traverses_chain(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    graph.add_dependency_group("B", int(DependencyType.AND), {"C"})
    result = graph.back_propagate("C")
    assert "B" in result
    assert "A" in result


def test_back_propagate_no_parents(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.back_propagate("A")
    assert isinstance(result, deque)
    assert len(result) == 0


def test_back_propagate_raises_cyclic_graph_error(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    graph.add_dependency_group("B", int(DependencyType.AND), {"A"})
    with pytest.raises(CyclicGraphError):
        graph.back_propagate("A", max_steps=1)


def test_back_propagate_deduplicates(graph):
    graph.add_dependency_group("P1", int(DependencyType.AND), {"C"})
    graph.add_dependency_group("P2", int(DependencyType.OR), {"C"})
    graph.add_dependency_group("X", int(DependencyType.AND), {"P1", "P2"})
    result = graph.back_propagate("C")
    assert result.count("P1") <= 1
    assert result.count("P2") <= 1


# ===================================================================
# 5. all_node_names — returns Set[str]
# ===================================================================


def test_all_node_names_returns_set(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.all_node_names()
    assert isinstance(result, set)


def test_all_node_names_includes_parents_and_children(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.all_node_names()
    assert "A" in result
    assert "B" in result


def test_all_node_names_empty_graph(graph):
    result = graph.all_node_names()
    assert isinstance(result, set)
    assert len(result) == 0


# ===================================================================
# 6. has_node — returns bool
# ===================================================================


def test_has_node_returns_bool(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    assert isinstance(graph.has_node("A"), bool)
    assert isinstance(graph.has_node("Z"), bool)


def test_has_node_parent(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    assert graph.has_node("A") is True


def test_has_node_child(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    assert graph.has_node("B") is True


def test_has_node_absent(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    assert graph.has_node("Z") is False


# ===================================================================
# 7. topological_sort — returns Tuple[str, ...]
# ===================================================================


def test_topological_sort_returns_tuple(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.topological_sort()
    assert isinstance(result, tuple)


def test_topological_sort_empty_graph(graph):
    result = graph.topological_sort()
    assert isinstance(result, tuple)
    assert len(result) == 0


def test_topological_sort_parent_before_child(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    result = graph.topological_sort()
    assert result.index("A") < result.index("B")


def test_topological_sort_diamond(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
    graph.add_dependency_group("B", int(DependencyType.AND), {"D"})
    graph.add_dependency_group("C", int(DependencyType.AND), {"D"})
    result = graph.topological_sort()
    assert result.index("A") < result.index("B")
    assert result.index("A") < result.index("C")
    assert result.index("B") < result.index("D")
    assert result.index("C") < result.index("D")


def test_topological_sort_cyclic_returns_empty(graph):
    graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
    graph.add_dependency_group("B", int(DependencyType.AND), {"A"})
    result = graph.topological_sort()
    assert result == ()
