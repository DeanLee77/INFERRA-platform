"""
HyperAdjacencyGraph and MatrixToHyperGraphAdapter contract tests.

Tests core graph operations (add, query, back-propagate, topological sort),
cycle detection, DependencyGroup immutability, and the legacy matrix adapter
with sparse iteration and memoization guard.
"""

import pytest

from src.domain.graph import (
    CyclicGraphError,
    DependencyGroup,
    DependencyType,
    HyperAdjacencyGraph,
    MatrixToHyperGraphAdapter,
)
from src.domain.nodes.dependency_matrix import DependencyMatrix


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def graph() -> HyperAdjacencyGraph:
    return HyperAdjacencyGraph()


def _build_linear_graph() -> HyperAdjacencyGraph:
    """A → B → C (simple linear chain)."""
    g = HyperAdjacencyGraph()
    g.add_dependency_group("A", DependencyType.AND, {"B"})
    g.add_dependency_group("B", DependencyType.AND, {"C"})
    return g


def _build_diamond_graph() -> HyperAdjacencyGraph:
    """A → B, A → C, B → D, C → D (diamond)."""
    g = HyperAdjacencyGraph()
    g.add_dependency_group("A", DependencyType.AND, {"B", "C"})
    g.add_dependency_group("B", DependencyType.AND, {"D"})
    g.add_dependency_group("C", DependencyType.OR, {"D"})
    return g


# ===================================================================
# 1. DependencyGroup — immutability & hashing
# ===================================================================


def test_dependency_group_is_immutable_namedtuple():
    g = DependencyGroup(DependencyType.AND, frozenset({"B", "C"}))
    assert g.dep_type == DependencyType.AND
    assert g.children == frozenset({"B", "C"})


def test_dependency_group_is_hashable():
    g1 = DependencyGroup(DependencyType.AND, frozenset({"B", "C"}))
    g2 = DependencyGroup(DependencyType.AND, frozenset({"B", "C"}))
    assert g1 == g2
    assert hash(g1) == hash(g2)
    assert len({g1, g2}) == 1


def test_dependency_group_different_types_are_not_equal():
    g1 = DependencyGroup(DependencyType.AND, frozenset({"B"}))
    g2 = DependencyGroup(DependencyType.OR, frozenset({"B"}))
    assert g1 != g2


# ===================================================================
# 2. add_dependency_group & queries
# ===================================================================


def test_add_dependency_group_registers_parent_and_children(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B", "C"})

    assert graph.has_node("A")
    assert graph.has_node("B")
    assert graph.has_node("C")


def test_get_parent_edges_returns_parents(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B"})
    graph.add_dependency_group("C", DependencyType.AND, {"B"})

    parents = graph.get_parent_edges("B")
    assert parents == {"A", "C"}


def test_get_parent_edges_empty_for_root(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B"})

    assert graph.get_parent_edges("A") == set()


def test_get_child_groups_returns_primitive_tuples(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B", "C"})

    groups = graph.get_child_groups("A")
    assert len(groups) == 1
    dep_type, children = groups[0]
    assert dep_type == int(DependencyType.AND)
    assert set(children) == {"B", "C"}


def test_get_typed_child_groups_returns_namedtuples(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B"})

    groups = graph.get_typed_child_groups("A")
    assert len(groups) == 1
    assert isinstance(groups[0], DependencyGroup)
    assert groups[0].dep_type == DependencyType.AND


def test_add_dependency_group_accepts_raw_int(graph):
    graph.add_dependency_group("A", int(DependencyType.OR), {"B"})

    groups = graph.get_typed_child_groups("A")
    assert groups[0].dep_type == DependencyType.OR


def test_all_node_names(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B", "C"})

    assert graph.all_node_names() == {"A", "B", "C"}


def test_has_node_false_for_unknown(graph):
    assert graph.has_node("Z") is False


# ===================================================================
# 3. back_propagate — BFS traversal
# ===================================================================


def test_back_propagate_linear_chain():
    g = _build_linear_graph()

    result = g.back_propagate("C")

    # C → B → A
    assert list(result) == ["B", "A"]


def test_back_propagate_diamond():
    g = _build_diamond_graph()

    result = g.back_propagate("D")

    # D → {B, C} → A
    assert set(result) == {"B", "C", "A"}


def test_back_propagate_root_node(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B"})

    result = graph.back_propagate("A")
    assert list(result) == []


def test_back_propagate_no_duplicates_in_diamond():
    g = _build_diamond_graph()

    result = g.back_propagate("D")

    # No node visited more than once
    assert len(result) == len(set(result))


def test_back_propagate_max_steps_guard():
    g = HyperAdjacencyGraph()
    # Build a cycle: A → B → A
    g.add_dependency_group("A", DependencyType.AND, {"B"})
    g.add_dependency_group("B", DependencyType.AND, {"A"})

    # With max_steps=1, the traversal should exceed it and raise
    with pytest.raises(CyclicGraphError):
        g.back_propagate("A", max_steps=1)


def test_back_propagate_auto_max_steps():
    g = _build_linear_graph()
    # Should not raise — auto max_steps should be large enough
    result = g.back_propagate("C")
    assert len(result) == 2


def test_back_propagate_isolated_node(graph):
    result = graph.back_propagate("nonexistent")
    assert list(result) == []


# ===================================================================
# 4. topological_sort — Kahn's algorithm
# ===================================================================


def test_topological_sort_linear():
    g = _build_linear_graph()

    order = g.topological_sort()
    assert order.index("A") < order.index("B") < order.index("C")


def test_topological_sort_diamond():
    g = _build_diamond_graph()

    order = g.topological_sort()
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")


def test_topological_sort_cyclic_returns_empty():
    g = HyperAdjacencyGraph()
    g.add_dependency_group("A", DependencyType.AND, {"B"})
    g.add_dependency_group("B", DependencyType.AND, {"A"})

    assert g.topological_sort() == ()


def test_topological_sort_cached():
    g = _build_linear_graph()
    first = g.topological_sort()
    second = g.topological_sort()

    assert first is second  # same tuple object — cached


def test_topological_sort_cache_invalidated_on_mutation():
    g = _build_linear_graph()
    first = g.topological_sort()

    g.add_dependency_group("C", DependencyType.AND, {"D"})

    second = g.topological_sort()
    assert first is not second
    assert "D" in second


# ===================================================================
# 5. clear & len
# ===================================================================


def test_clear_empties_graph(graph):
    graph.add_dependency_group("A", DependencyType.AND, {"B"})
    assert len(graph) == 2

    graph.clear()

    assert len(graph) == 0
    assert graph.has_node("A") is False


def test_len_counts_all_nodes():
    g = _build_diamond_graph()
    assert len(g) == 4


# ===================================================================
# 6. DependencyType enum
# ===================================================================


def test_dependency_type_values_match_legacy():
    from src.domain.nodes.dependency_type import DependencyType as LegacyDT

    assert int(DependencyType.AND) == LegacyDT.get_and()
    assert int(DependencyType.OR) == LegacyDT.get_or()
    assert int(DependencyType.MANDATORY) == LegacyDT.get_mandatory()
    assert int(DependencyType.OPTIONAL) == LegacyDT.get_optional()


# ===================================================================
# 7. MatrixToHyperGraphAdapter
# ===================================================================


def _make_legacy_matrix() -> tuple:
    """Build a simple 4-node legacy matrix: A→B, A→C, B→D, C→D."""
    # Index: 0=A, 1=B, 2=C, 3=D
    # DependencyType.AND = 8, OR = 4
    matrix = [
        [-1, 8, 8, -1],   # A → B (AND), A → C (AND)
        [-1, -1, -1, 8],  # B → D (AND)
        [-1, -1, -1, 4],  # C → D (OR)
        [-1, -1, -1, -1], # D (leaf)
    ]
    node_dict = {0: "A", 1: "B", 2: "C", 3: "D"}
    return DependencyMatrix(matrix), node_dict


def test_adapter_builds_graph_from_legacy_matrix():
    matrix, node_dict = _make_legacy_matrix()
    adapter = MatrixToHyperGraphAdapter(matrix, node_dict)

    assert adapter.has_node("A")
    assert adapter.has_node("D")
    assert "A" in adapter.get_parent_edges("B")
    assert "A" in adapter.get_parent_edges("C")
    assert "B" in adapter.get_parent_edges("D")
    assert "C" in adapter.get_parent_edges("D")


def test_adapter_back_propagate_matches_graph():
    matrix, node_dict = _make_legacy_matrix()
    adapter = MatrixToHyperGraphAdapter(matrix, node_dict)

    result = adapter.back_propagate("D")
    assert set(result) == {"B", "C", "A"}


def test_adapter_topological_sort():
    matrix, node_dict = _make_legacy_matrix()
    adapter = MatrixToHyperGraphAdapter(matrix, node_dict)

    order = adapter.topological_sort()
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")


def test_adapter_memoization_guard_skips_rebuild():
    matrix, node_dict = _make_legacy_matrix()
    adapter = MatrixToHyperGraphAdapter(matrix, node_dict)

    first_hash = adapter._matrix_hash
    adapter.rebuild()  # should be no-op

    assert adapter._matrix_hash == first_hash


def test_adapter_empty_matrix():
    matrix = DependencyMatrix([[]])
    adapter = MatrixToHyperGraphAdapter(matrix, {})

    assert len(adapter) == 0


def test_adapter_preserves_runtime_ids_from_legacy_map():
    matrix = DependencyMatrix([[-1 for _ in range(6)] for _ in range(6)])
    adapter = MatrixToHyperGraphAdapter(matrix, {2: "C", 5: "F"})

    assert adapter.lookup_by_name("C") == 2
    assert adapter.lookup_by_name("F") == 5
    assert adapter.lookup_by_id(2) == "C"
    assert adapter.lookup_by_id(5) == "F"


def test_adapter_sparse_iteration_no_cross_contamination():
    """Verify that a node with no children doesn't get spurious edges."""
    matrix_2d = [
        [-1, 8, -1],   # A → B only
        [-1, -1, -1],  # B (leaf)
        [-1, -1, -1],  # C (isolated leaf)
    ]
    node_dict = {0: "A", 1: "B", 2: "C"}
    adapter = MatrixToHyperGraphAdapter(DependencyMatrix(matrix_2d), node_dict)

    assert adapter.get_parent_edges("B") == {"A"}
    assert adapter.get_parent_edges("C") == set()


def test_adapter_preserves_dependency_types():
    matrix, node_dict = _make_legacy_matrix()
    adapter = MatrixToHyperGraphAdapter(matrix, node_dict)

    groups = adapter.get_child_groups("A")
    # A has AND edges to B and C
    assert len(groups) == 1
    dep_type, children = groups[0]
    assert dep_type == int(DependencyType.AND)

    groups_d = adapter.get_child_groups("D")
    assert len(groups_d) == 0


# ===================================================================
# 8. Matrix parity — adapter output matches graph built manually
# ===================================================================


def test_adapter_parity_with_manual_graph():
    """The adapter should produce the same topology as a manually-built graph."""
    matrix, node_dict = _make_legacy_matrix()
    adapter = MatrixToHyperGraphAdapter(matrix, node_dict)

    manual = _build_diamond_graph()

    # Same parent edges for all nodes
    for name in ["A", "B", "C", "D"]:
        assert adapter.get_parent_edges(name) == manual.get_parent_edges(name)

    # Same topological order
    assert adapter.topological_sort() == manual.topological_sort()

    # Same back-propagation result
    assert set(adapter.back_propagate("D")) == set(manual.back_propagate("D"))
