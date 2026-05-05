from unittest.mock import MagicMock

from src.domain.inference.topo_sort import TopologicalSort
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.nodes.record import HistoryRecord
from src.domain.nodes.dependency_type import DependencyType
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


class TestDfsTopologicalSortWithRecordFallback:
    def test_empty_records_falls_back_to_bfs(self):
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


class TestFillingSList:
    def test_no_root_nodes(self):
        matrix = [[-1, DependencyType.get_and()], [DependencyType.get_and(), -1]]
        node_dict = {"A": _make_node(0, "A"), "B": _make_node(1, "B")}
        id_dict = {0: "A", 1: "B"}
        result = TopologicalSort._filling_s_list(node_dict, id_dict, [], matrix)
        assert len(result) == 0

    def test_with_root_node(self):
        node_dict = {"A": _make_node(0, "A")}
        id_dict = {0: "A"}
        matrix = [[-1]]
        result = TopologicalSort._filling_s_list(node_dict, id_dict, [], matrix)
        assert len(result) == 1
        assert result[0].get_node_name() == "A"


class TestCreateCopyOfDependencyMatrix:
    def test_creates_independent_copy(self):
        original = [[1, 2], [3, 4]]
        copy = TopologicalSort._create_copy_of_dependency_matrix(original, 2)
        assert copy == original
        copy[0][0] = 99
        assert original[0][0] == 1

    def test_empty_matrix(self):
        result = TopologicalSort._create_copy_of_dependency_matrix([], 0)
        assert result == []


class TestCountIncomingEdges:
    def test_no_incoming(self):
        matrix = [[-1, -1], [-1, -1]]
        result = TopologicalSort._count_incoming_edges(matrix, 0, 2)
        assert result == 0

    def test_one_incoming(self):
        matrix = [[-1, DependencyType.get_and()], [-1, -1]]
        result = TopologicalSort._count_incoming_edges(matrix, 1, 2)
        assert result == 1


class TestGetChildIds:
    def test_no_children(self):
        matrix = [[-1, -1], [-1, -1]]
        result = TopologicalSort._get_child_ids(matrix, 0)
        assert result == []

    def test_with_children(self):
        matrix = [[-1, DependencyType.get_and(), DependencyType.get_or()], [-1, -1, -1], [-1, -1, -1]]
        result = TopologicalSort._get_child_ids(matrix, 0)
        assert result == [1, 2]


class TestCheckForCycles:
    def test_no_cycle(self):
        matrix = [[-1, -1], [-1, -1]]
        result = TopologicalSort._check_for_cycles(matrix, 2)
        assert result is False

    def test_with_cycle(self):
        matrix = [[-1, DependencyType.get_and()], [DependencyType.get_and(), -1]]
        result = TopologicalSort._check_for_cycles(matrix, 2)
        assert result is True


class TestFindTheMostPositive:
    def test_picks_highest_true_rate(self):
        n1 = _make_node(1, "high_true")
        n2 = _make_node(2, "low_true")
        records = {
            "high_true": HistoryRecord(name="high_true", true_count=8, false_count=2),
            "low_true": HistoryRecord(name="low_true", true_count=2, false_count=8),
        }
        result = TopologicalSort._find_the_most_positive([n1, n2], records)
        assert result.get_node_name() == "high_true"

    def test_picks_by_total_when_rates_equal(self):
        n1 = _make_node(1, "more_data")
        n2 = _make_node(2, "less_data")
        records = {
            "more_data": HistoryRecord(name="more_data", true_count=6, false_count=4),
            "less_data": HistoryRecord(name="less_data", true_count=3, false_count=2),
        }
        result = TopologicalSort._find_the_most_positive([n1, n2], records)
        assert result.get_node_name() == "more_data"

    def test_no_records_picks_first(self):
        n1 = _make_node(1, "A")
        n2 = _make_node(2, "B")
        result = TopologicalSort._find_the_most_positive([n1, n2], {})
        assert result.get_node_name() == "A"

    def test_removes_from_list(self):
        n1 = _make_node(1, "A")
        n2 = _make_node(2, "B")
        child_list = [n1, n2]
        TopologicalSort._find_the_most_positive(child_list, {})
        assert len(child_list) == 1


class TestFindTheMostNegative:
    def test_picks_highest_false_rate(self):
        n1 = _make_node(1, "high_false")
        n2 = _make_node(2, "low_false")
        records = {
            "high_false": HistoryRecord(name="high_false", true_count=2, false_count=8),
            "low_false": HistoryRecord(name="low_false", true_count=8, false_count=2),
        }
        result = TopologicalSort._find_the_most_negative([n1, n2], records)
        assert result.get_node_name() == "high_false"

    def test_no_records_picks_first(self):
        n1 = _make_node(1, "A")
        n2 = _make_node(2, "B")
        result = TopologicalSort._find_the_most_negative([n1, n2], {})
        assert result.get_node_name() == "A"

    def test_removes_from_list(self):
        n1 = _make_node(1, "A")
        n2 = _make_node(2, "B")
        child_list = [n1, n2]
        TopologicalSort._find_the_most_negative(child_list, {})
        assert len(child_list) == 1


class TestIsBetterChoice:
    def test_higher_rate_equal_total(self):
        assert TopologicalSort._is_better_choice(0.8, 0.5, 10, 10) is True

    def test_lower_rate(self):
        assert TopologicalSort._is_better_choice(0.3, 0.5, 10, 10) is False

    def test_equal_rate_more_total(self):
        assert TopologicalSort._is_better_choice(0.5, 0.5, 20, 10) is True

    def test_equal_rate_same_total(self):
        assert TopologicalSort._is_better_choice(0.5, 0.5, 10, 10) is False

    def test_rate_ge_best_rate_and_best_rate_negative(self):
        assert TopologicalSort._is_better_choice(0.0, -1.0, 0, -1) is True

    def test_rate_zero_best_rate_negative(self):
        assert TopologicalSort._is_better_choice(0.0, -0.5, 5, 10) is True


class TestLookupRecord:
    def test_simple_lookup(self):
        n = _make_node(0, "A")
        records = {"A": HistoryRecord(name="A", true_count=1)}
        result = TopologicalSort._lookup_record(n, records)
        assert result is not None
        assert result.true_count == 1

    def test_known_prefix(self):
        n = _make_node(0, "A")
        known = DependencyType.get_known()
        dep_list = [known]
        records = {"knownA": HistoryRecord(name="knownA", true_count=3)}
        result = TopologicalSort._lookup_record(n, records, dep_list)
        assert result is not None
        assert result.true_count == 3

    def test_not_prefix(self):
        n = _make_node(0, "A")
        not_dep = DependencyType.get_not()
        dep_list = [not_dep]
        records = {"notA": HistoryRecord(name="notA", false_count=5)}
        result = TopologicalSort._lookup_record(n, records, dep_list)
        assert result is not None
        assert result.false_count == 5

    def test_not_known_prefix(self):
        n = _make_node(0, "A")
        known = DependencyType.get_known()
        not_dep = DependencyType.get_not()
        dep_list = [known | not_dep]
        records = {"not knownA": HistoryRecord(name="not knownA", true_count=7)}
        result = TopologicalSort._lookup_record(n, records, dep_list)
        assert result is not None
        assert result.true_count == 7

    def test_no_dep_list_uses_simple_lookup(self):
        n = _make_node(0, "A")
        records = {"A": HistoryRecord(name="A", true_count=2)}
        result = TopologicalSort._lookup_record(n, records, None)
        assert result is not None

    def test_missing_record_returns_none(self):
        n = _make_node(0, "A")
        result = TopologicalSort._lookup_record(n, {})
        assert result is None


class TestDeepening:
    def test_deepening_with_children(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        n2 = _make_node(2, "C")
        node_dict = {"A": n0, "B": n1, "C": n2}
        id_dict = {0: "A", 1: "B", 2: "C"}
        matrix = [
            [-1, DependencyType.get_and(), -1],
            [-1, -1, DependencyType.get_and()],
            [-1, -1, -1],
        ]
        sorted_list = [n0]
        visited_list = [0]
        TopologicalSort._deepening(
            node_dict, id_dict, matrix, sorted_list, visited_list, 0
        )
        assert len(sorted_list) >= 2

    def test_deepening_no_children(self):
        n0 = _make_node(0, "A")
        node_dict = {"A": n0}
        id_dict = {0: "A"}
        matrix = [[-1]]
        sorted_list = [n0]
        visited_list = [0]
        TopologicalSort._deepening(
            node_dict, id_dict, matrix, sorted_list, visited_list, 0
        )
        assert len(sorted_list) == 1


class TestVisit:
    def test_visit_none_node(self):
        result = TopologicalSort._visit(
            None, [], {}, {}, {}, [], [[-1]]
        )
        assert result == []

    def test_visit_leaf_node(self):
        n0 = _make_node(0, "A")
        result = TopologicalSort._visit(
            n0, [], {}, {"A": n0}, {0: "A"}, [], [[-1]]
        )
        assert n0 in result

    def test_visit_or_only_children(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        n2 = _make_node(2, "C")
        node_dict = {"A": n0, "B": n1, "C": n2}
        id_dict = {0: "A", 1: "B", 2: "C"}
        or_dep = DependencyType.get_or()
        matrix = [[-1, or_dep, or_dep], [-1, -1, -1], [-1, -1, -1]]
        records = {
            "B": HistoryRecord(name="B", true_count=5, false_count=1),
            "C": HistoryRecord(name="C", true_count=1, false_count=5),
        }
        result = TopologicalSort._visit(
            n0, [], records, node_dict, id_dict, [], matrix
        )
        assert len(result) >= 2

    def test_visit_and_only_children(self):
        n0 = _make_node(0, "A")
        n1 = _make_node(1, "B")
        n2 = _make_node(2, "C")
        node_dict = {"A": n0, "B": n1, "C": n2}
        id_dict = {0: "A", 1: "B", 2: "C"}
        and_dep = DependencyType.get_and()
        matrix = [[-1, and_dep, and_dep], [-1, -1, -1], [-1, -1, -1]]
        records = {
            "B": HistoryRecord(name="B", true_count=5, false_count=1),
            "C": HistoryRecord(name="C", true_count=1, false_count=5),
        }
        result = TopologicalSort._visit(
            n0, [], records, node_dict, id_dict, [], matrix
        )
        assert len(result) >= 2
