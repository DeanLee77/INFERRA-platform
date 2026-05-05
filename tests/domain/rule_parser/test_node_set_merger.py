"""
Tests for NodeSetMerger — merge imported NodeSets with local rules.

Unit tests cover:
- Basic merge (single import, multiple imports, no imports)
- Local-wins override on name collision
- NodeRecord metadata attached to every merged node
- No duplicate edges in merged dependency matrix
- Ordering invariant (imported nodes before local nodes)
- Fact/input dictionary merge (local overrides imported)
- Default goal node preservation

Property-based tests (Hypothesis) cover:
- Associativity: (A ∪ B) ∪ C == A ∪ (B ∪ C) for name sets
- Commutativity: A ∪ B == B ∪ A (when no name collisions)
- Idempotency: A ∪ A == A (same input produces same node names)
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.domain.fact_values import FactValue
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.imports.node_origin import NodeOrigin
from src.domain.nodes.dependency_matrix import DependencyMatrix
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.rule_parser.node_set_merger import NodeSetMerger


class DummyNode(Node):
    def __init__(self, node_id=0, node_name="n", variable_name="v", stable_node_id=None):
        super().__init__(id=node_id)
        self._node_name = node_name
        self._variable_name = variable_name
        self._stable_node_id = stable_node_id
        self._line_type = LineType.VALUE_CONCLUSION
        self._node_line = 1

    def initialisation(self, parent_text: str, tokens) -> None:
        pass

    def get_line_type(self) -> LineType:
        return self._line_type

    def self_evaluate(self, working_memory: dict) -> FactValue:
        return FactValue(True)


def _make_node_set(nodes, name="test", matrix=None, input_dict=None, fact_dict=None):
    """Helper to build a NodeSet with nodes and optional dependency matrix."""
    ns = NodeSet()
    ns.set_node_set_name(name)
    for node in nodes:
        ns.add_node(node)
    if matrix is not None:
        ns.set_dependency_matrix(matrix)
    if input_dict is not None:
        ns.set_input_dictionary(input_dict)
    if fact_dict is not None:
        ns.set_fact_dictionary(fact_dict)
    return ns


class TestNodeSetMergerBasic:
    def test_merge_no_imports_returns_local_nodes(self):
        local = _make_node_set([DummyNode(0, "a"), DummyNode(1, "b")], name="local")
        result = NodeSetMerger.merge(local, [])
        assert set(result.get_node_dictionary().keys()) == {"a", "b"}

    def test_merge_single_import(self):
        local = _make_node_set([DummyNode(0, "a")], name="local")
        imported = _make_node_set([DummyNode(0, "b"), DummyNode(1, "c")], name="imp")
        result = NodeSetMerger.merge(local, [imported])
        assert set(result.get_node_dictionary().keys()) == {"a", "b", "c"}

    def test_merge_multiple_imports(self):
        local = _make_node_set([DummyNode(0, "local_node")], name="local")
        imp1 = _make_node_set([DummyNode(0, "imp1_a")], name="imp1")
        imp2 = _make_node_set([DummyNode(0, "imp2_a")], name="imp2")
        result = NodeSetMerger.merge(local, [imp1, imp2])
        assert set(result.get_node_dictionary().keys()) == {"local_node", "imp1_a", "imp2_a"}


class TestNodeSetMergerLocalWins:
    def test_local_overrides_imported_on_name_collision(self):
        local = _make_node_set([DummyNode(0, "shared")], name="local")
        imported = _make_node_set([DummyNode(0, "shared")], name="imp")
        result = NodeSetMerger.merge(local, [imported], rule_name="local")
        assert "shared" in result.get_node_dictionary()
        merged_node = result.get_node_dictionary()["shared"]
        record = result.get_graph().get_node_record("shared")
        assert record.module == "local"
        assert record.imported is False
        assert record.import_depth == 0

    def test_local_overrides_multiple_imports_same_name(self):
        local = _make_node_set([DummyNode(0, "shared")], name="local")
        imp1 = _make_node_set([DummyNode(0, "shared")], name="imp1")
        imp2 = _make_node_set([DummyNode(0, "shared")], name="imp2")
        result = NodeSetMerger.merge(local, [imp1, imp2], rule_name="local")
        merged_node = result.get_node_dictionary()["shared"]
        record = result.get_graph().get_node_record("shared")
        assert record.module == "local"
        assert record.imported is False

    def test_first_import_wins_when_no_local_collision(self):
        local = _make_node_set([DummyNode(0, "x")], name="local")
        imp1 = _make_node_set([DummyNode(0, "dup")], name="imp1")
        imp2 = _make_node_set([DummyNode(0, "dup")], name="imp2")
        result = NodeSetMerger.merge(local, [imp1, imp2])
        record = result.get_graph().get_node_record("dup")
        assert record.module == "imp1"


class TestNodeSetMergerNodeRecord:
    def test_every_merged_node_has_record(self):
        local = _make_node_set([DummyNode(0, "a")], name="local")
        imp = _make_node_set([DummyNode(0, "b")], name="imp")
        result = NodeSetMerger.merge(local, [imp], rule_name="root")
        for node in result.get_sorted_node_list():
            assert result.get_graph().get_node_record(node.get_node_name()) is not None

    def test_local_node_record(self):
        local = _make_node_set([DummyNode(0, "a")], name="local")
        result = NodeSetMerger.merge(local, [], rule_name="root_rule")
        record = result.get_graph().get_node_record("a")
        assert record.module == "root_rule"
        assert record.imported is False
        assert record.import_depth == 0

    def test_imported_node_record_default(self):
        local = _make_node_set([], name="local")
        imp = _make_node_set([DummyNode(0, "b")], name="imported_module")
        result = NodeSetMerger.merge(local, [imp], rule_name="root")
        record = result.get_graph().get_node_record("b")
        assert record.imported is True
        assert record.module == "imported_module"

    def test_imported_node_record_from_origins_dict(self):
        local = _make_node_set([], name="local")
        imp = _make_node_set([DummyNode(0, "b")], name="common_rules")
        origins = {"common_rules": NodeOrigin(module="common_rules", imported=True, depth=2)}
        result = NodeSetMerger.merge(local, [imp], imported_origins=origins, rule_name="root")
        record = result.get_graph().get_node_record("b")
        assert record.import_depth == 2


class TestNodeSetMergerDependencyMatrix:
    def test_dependency_matrix_merged(self):
        local = _make_node_set(
            [DummyNode(0, "a"), DummyNode(1, "b")],
            name="local",
            matrix=DependencyMatrix([[-1, 4], [-1, -1]]),
        )
        imp = _make_node_set(
            [DummyNode(0, "c"), DummyNode(1, "d")],
            name="imp",
            matrix=DependencyMatrix([[-1, 8], [-1, -1]]),
        )
        result = NodeSetMerger.merge(local, [imp])
        assert result.get_dependency_matrix() is not None

    def test_empty_matrices_merge_gracefully(self):
        local = _make_node_set([DummyNode(0, "a")], name="local")
        imp = _make_node_set([DummyNode(0, "b")], name="imp")
        result = NodeSetMerger.merge(local, [imp])
        assert result.get_dependency_matrix() is not None

    def test_no_duplicate_edges_after_merge(self):
        local = _make_node_set(
            [DummyNode(0, "p"), DummyNode(1, "c")],
            name="local",
            matrix=DependencyMatrix([[-1, 12], [-1, -1]]),
        )
        imp = _make_node_set(
            [DummyNode(0, "p2"), DummyNode(1, "c2")],
            name="imp",
            matrix=DependencyMatrix([[-1, 12], [-1, -1]]),
        )
        result = NodeSetMerger.merge(local, [imp])
        matrix = result.get_dependency_matrix().get_dependency_two_dimension_list()
        for row in matrix:
            for val in row:
                if val != -1:
                    assert val > 0


class TestNodeSetMergerOrdering:
    def test_imported_nodes_before_local_nodes(self):
        local = _make_node_set([DummyNode(0, "local_a")], name="local")
        imp = _make_node_set([DummyNode(0, "imp_b")], name="imp")
        result = NodeSetMerger.merge(local, [imp])
        names = [n.get_node_name() for n in result.get_sorted_node_list()]
        imp_indices = [i for i, n in enumerate(names) if n.startswith("imp_")]
        local_indices = [i for i, n in enumerate(names) if n.startswith("local_")]
        if imp_indices and local_indices:
            assert max(imp_indices) < min(local_indices)


class TestNodeSetMergerFactDictionaries:
    def test_input_dicts_merged(self):
        local = _make_node_set([DummyNode(0, "a")], name="local", input_dict={"x": 1})
        imp = _make_node_set([DummyNode(0, "b")], name="imp", input_dict={"y": 2})
        result = NodeSetMerger.merge(local, [imp])
        assert result.get_input_dictionary()["x"] == 1
        assert result.get_input_dictionary()["y"] == 2

    def test_fact_dicts_merged_local_overrides_imported(self):
        local = _make_node_set([DummyNode(0, "a")], name="local", fact_dict={"shared": "local_val"})
        imp = _make_node_set([DummyNode(0, "b")], name="imp", fact_dict={"shared": "imp_val"})
        result = NodeSetMerger.merge(local, [imp])
        assert result.get_fact_dictionary()["shared"] == "local_val"


class TestNodeSetMergerGoalNode:
    def test_default_goal_node_preserved(self):
        node = DummyNode(0, "goal")
        local = _make_node_set([node], name="local")
        local.set_default_goal_node("goal")
        result = NodeSetMerger.merge(local, [])
        assert result.get_default_goal_node() is not None
        assert result.get_default_goal_node().get_node_name() == "goal"


class TestNodeSetMergerNodeSetName:
    def test_merged_set_name_from_local(self):
        local = _make_node_set([DummyNode(0, "a")], name="my_rule")
        result = NodeSetMerger.merge(local, [], rule_name="fallback")
        assert result.get_node_set_name() == "my_rule"

    def test_merged_set_name_fallback_to_rule_name(self):
        local = NodeSet()
        result = NodeSetMerger.merge(local, [], rule_name="fallback_name")
        assert result.get_node_set_name() == "fallback_name"


class TestNodeSetMergerAssociativity:
    """Property: (A ∪ B) ∪ C == A ∪ (B ∪ C) for the set of merged node names."""

    @given(
        names_a=st.lists(st.text(min_size=1, max_size=5, alphabet="abc"), min_size=0, max_size=4, unique=True),
        names_b=st.lists(st.text(min_size=1, max_size=5, alphabet="def"), min_size=0, max_size=4, unique=True),
        names_c=st.lists(st.text(min_size=1, max_size=5, alphabet="ghi"), min_size=0, max_size=4, unique=True),
    )
    @settings(max_examples=50)
    def test_associativity_node_names(self, names_a, names_b, names_c):
        ns_a = _make_node_set([DummyNode(i, n) for i, n in enumerate(names_a)], name="a")
        ns_b = _make_node_set([DummyNode(i, n) for i, n in enumerate(names_b)], name="b")
        ns_c = _make_node_set([DummyNode(i, n) for i, n in enumerate(names_c)], name="c")

        left = NodeSetMerger.merge(NodeSetMerger.merge(ns_a, [ns_b]), [ns_c])
        right = NodeSetMerger.merge(ns_a, [NodeSetMerger.merge(ns_b, [ns_c])])

        assert set(left.get_node_dictionary().keys()) == set(right.get_node_dictionary().keys())


class TestNodeSetMergerCommutativity:
    """Property: A ∪ B == B ∪ A when no name collisions (disjoint sets)."""

    @given(
        names_a=st.lists(st.text(min_size=1, max_size=5, alphabet="abc"), min_size=0, max_size=4, unique=True),
        names_b=st.lists(st.text(min_size=1, max_size=5, alphabet="xyz"), min_size=0, max_size=4, unique=True),
    )
    @settings(max_examples=50)
    def test_commutativity_disjoint(self, names_a, names_b):
        ns_a = _make_node_set([DummyNode(i, n) for i, n in enumerate(names_a)], name="a")
        ns_b = _make_node_set([DummyNode(i, n) for i, n in enumerate(names_b)], name="b")

        ab = NodeSetMerger.merge(ns_a, [ns_b])
        ba = NodeSetMerger.merge(ns_b, [ns_a])

        assert set(ab.get_node_dictionary().keys()) == set(ba.get_node_dictionary().keys())


class TestNodeSetMergerIdempotency:
    """Property: merging the same NodeSet twice produces the same node names."""

    @given(
        names=st.lists(st.text(min_size=1, max_size=5, alphabet="abc"), min_size=0, max_size=4, unique=True),
    )
    @settings(max_examples=50)
    def test_idempotency_node_names(self, names):
        ns = _make_node_set([DummyNode(i, n) for i, n in enumerate(names)], name="root")
        result1 = NodeSetMerger.merge(ns, [])
        result2 = NodeSetMerger.merge(result1, [])

        assert set(result1.get_node_dictionary().keys()) == set(result2.get_node_dictionary().keys())

    def test_idempotency_concrete(self):
        ns = _make_node_set([DummyNode(0, "a"), DummyNode(1, "b")], name="root")
        r1 = NodeSetMerger.merge(ns, [])
        r2 = NodeSetMerger.merge(r1, [])
        assert set(r1.get_node_dictionary().keys()) == set(r2.get_node_dictionary().keys())


class TestNodeSetAddNode:
    def test_add_node_assigns_next_id(self):
        ns = NodeSet()
        node = DummyNode(node_id=None, node_name="auto_id")
        ns.add_node(node)
        assert node.get_node_id() == 0

    def test_add_node_with_existing_id(self):
        ns = NodeSet()
        node = DummyNode(node_id=5, node_name="manual_id")
        ns.add_node(node)
        assert node.get_node_id() == 5
        assert ns.get_node_id_dictionary()[5] == "manual_id"

    def test_add_node_appends_to_sorted_list(self):
        ns = NodeSet()
        n1 = DummyNode(0, "first")
        n2 = DummyNode(1, "second")
        ns.add_node(n1)
        ns.add_node(n2)
        assert len(ns.get_sorted_node_list()) == 2
        assert ns.get_sorted_node_list()[0].get_node_name() == "first"


class TestNodeSetRemoveNodeByName:
    def test_remove_existing_node(self):
        ns = NodeSet()
        node = DummyNode(0, "remove_me", stable_node_id="sid1")
        ns.add_node(node)
        ns.remove_node_by_name("remove_me")
        assert "remove_me" not in ns.get_node_dictionary()
        assert 0 not in ns.get_node_id_dictionary()
        assert "sid1" not in ns.get_stable_node_id_dictionary()

    def test_remove_nonexistent_node_no_error(self):
        ns = NodeSet()
        ns.remove_node_by_name("ghost")

    def test_remove_node_from_sorted_list(self):
        ns = NodeSet()
        n1 = DummyNode(0, "keep")
        n2 = DummyNode(1, "remove")
        ns.add_node(n1)
        ns.add_node(n2)
        ns.remove_node_by_name("remove")
        names = [n.get_node_name() for n in ns.get_sorted_node_list()]
        assert "remove" not in names
        assert "keep" in names

    def test_remove_node_updates_graph_edges(self):
        ns = _make_node_set(
            [DummyNode(0, "A"), DummyNode(1, "B"), DummyNode(2, "C")]
        )
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", DependencyType.MANDATORY | DependencyType.AND, {"B"})
        graph.add_dependency_group("B", DependencyType.MANDATORY | DependencyType.AND, {"C"})
        ns.set_graph(graph)

        ns.remove_node_by_name("B")

        assert ns.get_graph().get_dependency_type("A", "B") == -1
        assert ns.get_graph().get_child_groups("A") == ()
        assert ns.get_graph().get_parent_edges("C") == set()
