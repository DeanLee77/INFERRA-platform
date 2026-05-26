from unittest.mock import MagicMock

from src.domain.inference.topo_sort import TopologicalSort
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.nodes.node_id_utils import canonical_node_key
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.nodes.record import HistoryRecord
from src.domain.graph.dependency_type import DependencyType
from src.domain.fact_values import FactValue


def _make_node(node_id=0, node_name="node0"):
    node = MagicMock(spec=Node)
    node.get_node_id.return_value = node_id
    node.get_node_name.return_value = node_name
    node.get_line_type.return_value = LineType.VALUE_CONCLUSION
    return node


class TestBfsTopologicalSort:
    def test_single_node_no_deps(self):
        node = _make_node(0, "A")
        node_dict = {"A": node}
        id_dict = {0: "A"}
        matrix = [[-1]]
        result = TopologicalSort.bfs_topological_sort(node_dict, id_dict, matrix)
        assert len(result) == 1
        assert result[0].get_node_name() == "A"

    def test_two_nodes_linear(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        node_dict = {"A": n0, "B": n1}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_and()], [-1, -1]]
        result = TopologicalSort.bfs_topological_sort(node_dict, id_dict, matrix)
        assert len(result) == 2
        assert result[0].get_node_name() == "A"
        assert result[1].get_node_name() == "B"

    def test_cycle_returns_empty(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        node_dict = {"A": n0, "B": n1}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_and()], [DependencyType.get_and(), -1]]
        result = TopologicalSort.bfs_topological_sort(node_dict, id_dict, matrix)
        assert result == []

    def test_three_nodes_dag(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        n2 = _make_node(2, "C")
        node_dict = {"A": n0, "B": n1, "C": n2}
        id_dict = {0: "A", 1: "B", 2: "C"}
        matrix = [
            [-1, DependencyType.get_and(), DependencyType.get_and()],
            [-1, -1, DependencyType.get_and()],
            [-1, -1, -1],
        ]
        result = TopologicalSort.bfs_topological_sort(node_dict, id_dict, matrix)
        assert len(result) == 3
        names = [n.get_node_name() for n in result]
        assert names.index("A") < names.index("B")
        assert names.index("A") < names.index("C")

    def test_preserves_original_matrix(self):
        node_dict = {"A": _make_node(0, "A"), "B": _make_node(1, "B")}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_and()], [-1, -1]]
        import copy
        original = copy.deepcopy(matrix)
        TopologicalSort.bfs_topological_sort(node_dict, id_dict, matrix)
        assert matrix == original

    def test_legacy_entrypoint_does_not_call_runtime_node_id(self):
        node_a = _make_node(0, "A")
        node_b = _make_node(1, "B")
        node_a.get_node_id.side_effect = AssertionError("node_id should not be used")
        node_b.get_node_id.side_effect = AssertionError("node_id should not be used")
        node_dict = {"A": node_a, "B": node_b}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_and()], [-1, -1]]

        result = TopologicalSort.bfs_topological_sort(node_dict, id_dict, matrix)

        assert [node.get_node_name() for node in result] == ["A", "B"]


class TestGraphTopologicalSort:
    def test_graph_sort_uses_canonical_imported_keys(self):
        imported = canonical_node_key("eligibility", "common_rules@2.1.0")
        graph = HyperAdjacencyGraph()
        graph.register_node(imported, {"import_namespace": "common_rules@2.1.0"})
        graph.register_node("local_goal")
        graph.add_dependency_group("local_goal", DependencyType.get_and(), {imported})
        node_dict = {
            "local_goal": _make_node(0, "local_goal"),
            imported: _make_node(1, imported),
        }

        result = TopologicalSort.bfs_graph_topological_sort(node_dict, graph)

        assert [node.get_node_name() for node in result] == ["local_goal", imported]

    def test_graph_sort_can_bridge_qualified_key_to_raw_node_dictionary(self):
        imported = canonical_node_key("eligibility", "common_rules@2.1.0")
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("local_goal", DependencyType.get_and(), {imported})
        node_dict = {
            "local_goal": _make_node(0, "local_goal"),
            "eligibility": _make_node(1, "eligibility"),
        }

        result = TopologicalSort.bfs_graph_topological_sort(node_dict, graph)

        assert [node.get_node_name() for node in result] == ["local_goal", "eligibility"]


class TestDfsTopologicalSort:
    def test_single_node(self):
        node = _make_node(0, "A")
        node_dict = {"A": node}
        id_dict = {0: "A"}
        matrix = [[-1]]
        result = TopologicalSort.dfs_topological_sort(node_dict, id_dict, matrix)
        assert len(result) >= 1
        assert result[0].get_node_name() == "A"

    def test_two_nodes_linear(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        node_dict = {"A": n0, "B": n1}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_and()], [-1, -1]]
        result = TopologicalSort.dfs_topological_sort(node_dict, id_dict, matrix)
        assert len(result) == 2

    def test_three_nodes_with_branching(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        n2 = _make_node(2, "C")
        node_dict = {"A": n0, "B": n1, "C": n2}
        id_dict = {0: "A", 1: "B", 2: "C"}
        matrix = [
            [-1, DependencyType.get_and(), DependencyType.get_and()],
            [-1, -1, -1],
            [-1, -1, -1],
        ]
        result = TopologicalSort.dfs_topological_sort(node_dict, id_dict, matrix)
        assert len(result) == 3
        assert result[0].get_node_name() == "A"

    def test_recurses_before_next_sibling_without_records(self):
        n0 = _make_node(0, "root")
        n1 = _make_node(1, "mid")
        n2 = _make_node(2, "sibling")
        n3 = _make_node(3, "leaf")
        node_dict = {"root": n0, "mid": n1, "sibling": n2, "leaf": n3}
        id_dict = {0: "root", 1: "mid", 2: "sibling", 3: "leaf"}
        matrix = [
            [-1, DependencyType.get_or(), DependencyType.get_or(), -1],
            [-1, -1, -1, DependencyType.get_or()],
            [-1, -1, -1, -1],
            [-1, -1, -1, -1],
        ]

        result = TopologicalSort.dfs_topological_sort(node_dict, id_dict, matrix)

        assert [node.get_node_name() for node in result] == ["root", "mid", "leaf", "sibling"]


class TestDfsTopologicalSortWithRecordFallback:
    def test_empty_records_falls_back_to_deterministic_dfs(self):
        n0 = _make_node(0, "A")
        node_dict = {"A": n0}
        id_dict = {0: "A"}
        matrix = [[-1]]
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, {}
        )
        assert len(result) == 1
        assert result[0].get_node_name() == "A"

    def test_with_records(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        node_dict = {"A": n0, "B": n1}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_and()], [-1, -1]]
        records = {"B": HistoryRecord(name="B", true_count=5, false_count=1)}
        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )
        assert len(result) >= 1

    def test_with_records_does_not_call_runtime_node_id(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        n0.get_node_id.side_effect = AssertionError("node_id should not be used")
        n1.get_node_id.side_effect = AssertionError("node_id should not be used")
        node_dict = {"A": n0, "B": n1}
        id_dict = {0: "A", 1: "B"}
        matrix = [[-1, DependencyType.get_or()], [-1, -1]]
        records = {"B": HistoryRecord(name="B", true_count=5, false_count=1)}

        result = TopologicalSort.dfs_topological_sort_with_record(
            node_dict, id_dict, matrix, records
        )

        assert [node.get_node_name() for node in result] == ["A", "B"]

