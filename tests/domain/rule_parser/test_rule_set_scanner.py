import pytest
from unittest.mock import MagicMock, patch
from collections import deque

from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.domain.rule_parser.i_line_reader import ILineReader
from src.domain.rule_parser.i_scan_feeder import IScanFeeder
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.meta_data import MetaData
from src.domain.nodes.record import HistoryRecord
from src.domain.nodes.dependency_matrix import DependencyMatrix
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph


class _MockLineReader(ILineReader):
    def __init__(self, lines):
        self._lines = lines
        self._index = 0

    def get_next_line(self):
        if self._index >= len(self._lines):
            return ""
        line = self._lines[self._index]
        self._index += 1
        return line


class _MockScanFeeder(IScanFeeder):
    def __init__(self):
        self._node_set = NodeSet()
        self._warnings = []
        self._parents = []
        self._children = []

    def handle_parent(self, parent_text, line_number, meta_data):
        self._parents.append((parent_text, line_number, meta_data))
        node = MagicMock()
        node.get_node_name.return_value = parent_text
        node.get_node_id.return_value = len(self._parents)
        self._node_set.get_node_dictionary()[parent_text] = node

    def handle_child(self, parent_text, child_text, first_keywords_group, line_number):
        self._children.append((parent_text, child_text, first_keywords_group, line_number))
        node = MagicMock()
        node.get_node_name.return_value = child_text
        node.get_node_id.return_value = len(self._children) + 100
        self._node_set.get_node_dictionary()[child_text] = node

    def handle_list_item(self, parent_text, item_text, meta_type):
        pass

    def handle_warning(self, parent_text):
        self._warnings.append(parent_text)
        return parent_text

    def get_node_set(self):
        return self._node_set

    def set_node_set(self, ns):
        self._node_set = ns

    def create_dependency_matrix(self):
        return DependencyMatrix([[]])


class TestRuleSetScannerInit:
    def test_init_sets_feeder_and_reader(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        assert scanner._RuleSetScanner__scan_feeder is feeder
        assert scanner._RuleSetScanner__line_reader is reader

    def test_init_historical_data_defaults_false(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        assert scanner._RuleSetScanner__use_historical_data is False

    def test_init_record_dict_defaults_empty(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        assert scanner._RuleSetScanner__record_dict_of_nodes == {}


class TestRuleSetScannerScanRuleSet:
    def test_scan_empty_input(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 0

    def test_scan_single_parent(self):
        reader = _MockLineReader(["status IS active\n"])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 1
        assert feeder._parents[0][0] == "status IS active"

    def test_scan_parent_and_child(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 1
        assert len(feeder._children) == 1

    def test_scan_comment_line(self):
        reader = _MockLineReader(["# Reference: test\n"])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 0

    def test_scan_empty_line_clears_stack(self):
        reader = _MockLineReader([
            "status IS active\n",
            "\n",
            "score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 2

    def test_scan_multiple_children(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    score IS 10\n",
            "    age > 18\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._children) == 2

    def test_scan_child_with_and_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    AND score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._children) == 1

    def test_scan_child_with_or_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    OR score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._children) == 1

    def test_scan_child_with_mandatory_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    AND MANDATORY score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()

    def test_scan_child_with_optionally_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    OR OPTIONALLY score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()

    def test_scan_child_with_possibly_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    OR POSSIBLY score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()

    def test_scan_child_with_not_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    AND NOT score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()

    def test_scan_child_with_known_keyword(self):
        reader = _MockLineReader([
            "status IS active\n",
            "    AND KNOWN score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()

    def test_scan_invalid_indentation_triggers_warning(self):
        reader = _MockLineReader([
            "status IS active\n",
            "        score IS 10\n"
        ])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._warnings) > 0

    def test_scan_double_slash_comment(self):
        reader = _MockLineReader(["// this is a comment\n"])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 0

    def test_scan_hash_comment(self):
        reader = _MockLineReader(["# this is a comment\n"])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        scanner.scan_rule_set()
        assert len(feeder._parents) == 0


class TestRuleSetScannerEstablishNodeSet:
    def test_establish_node_set_without_records(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        node_set = scanner.establish_node_set()
        assert isinstance(node_set, NodeSet)

    def test_establish_node_set_with_records(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        records = {"node1": HistoryRecord(name="node1", true_count=1)}
        node_set = scanner.establish_node_set(record_node_dictionary=records)
        assert isinstance(node_set, NodeSet)

    def test_establish_node_set_with_graph_uses_graph_topological_sort(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
        feeder._node_set.set_graph(graph)
        node_a = MagicMock()
        node_a.get_node_name.return_value = "A"
        node_b = MagicMock()
        node_b.get_node_name.return_value = "B"
        feeder._node_set.get_node_dictionary()["A"] = node_a
        feeder._node_set.get_node_dictionary()["B"] = node_b

        node_set = scanner.establish_node_set()

        assert node_set.get_sorted_node_list() == [node_a, node_b]

    def test_establish_node_set_with_graph_and_records_uses_ml_strategy(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.OR), {"B"})
        feeder._node_set.set_graph(graph)
        node_a = MagicMock()
        node_a.get_node_name.return_value = "A"
        node_b = MagicMock()
        node_b.get_node_name.return_value = "B"
        feeder._node_set.get_node_dictionary()["A"] = node_a
        feeder._node_set.get_node_dictionary()["B"] = node_b
        records = {"A": HistoryRecord(name="A", true_count=1)}

        with patch(
            "src.domain.rule_parser.rule_set_scanner.MLTopologicalSortStrategy"
        ) as strategy_cls:
            strategy_cls.return_value.sort.return_value = ("B", "A")
            node_set = scanner.establish_node_set(record_node_dictionary=records)

        strategy_cls.assert_called_once_with(graph)
        strategy_cls.return_value.sort.assert_called_once_with(records)
        assert node_set.get_sorted_node_list() == [node_b, node_a]

    def test_establish_node_set_cyclic_triggers_warning(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("A", int(DependencyType.AND), {"B"})
        graph.add_dependency_group("B", int(DependencyType.AND), {"A"})
        feeder._node_set.set_graph(graph)
        scanner.establish_node_set()
        assert len(feeder._warnings) > 0


class TestRuleSetScannerHistoricalData:
    def test_set_historical_data_toggles(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        assert scanner._RuleSetScanner__use_historical_data is False
        scanner.set_historical_data()
        assert scanner._RuleSetScanner__use_historical_data is True
        scanner.set_historical_data()
        assert scanner._RuleSetScanner__use_historical_data is False


class TestRuleSetScannerRecordDictionary:
    def test_set_and_get_record_dictionary(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        records = {"node1": HistoryRecord(name="node1")}
        scanner.set_record_dictionary_of_nodes(records)
        assert scanner.get_record_dict_of_nodes() is records

    def test_get_record_dict_default_empty(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        assert scanner.get_record_dict_of_nodes() == {}


class TestRuleSetScannerHandlingStackPop:
    def test_handling_stack_pop_zero_diff(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        stack = deque(["a", "b", "c"])
        result = scanner._handling_stack_pop(stack, 0)
        assert len(result) == 2

    def test_handling_stack_pop_positive_diff(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        stack = deque(["a", "b", "c", "d"])
        result = scanner._handling_stack_pop(stack, 1)
        assert len(result) == 2

    def test_handling_stack_pop_empty_stack(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        stack = deque()
        result = scanner._handling_stack_pop(stack, 0)
        assert len(result) == 0

    def test_handling_stack_pop_negative_diff_no_change(self):
        reader = _MockLineReader([])
        feeder = _MockScanFeeder()
        scanner = RuleSetScanner(reader, feeder)
        stack = deque(["a", "b"])
        result = scanner._handling_stack_pop(stack, -1)
        assert len(result) == 2
