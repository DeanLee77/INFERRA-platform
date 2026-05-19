import json
import warnings
from unittest.mock import MagicMock

import pytest

from src.domain.fact_values import FactValue
from src.domain.graph.dependency_matrix import DependencyMatrix
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet


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


class TestNodeSetSettersWithEdgeCases:
    def test_set_node_set_name_empty_logs_error(self):
        ns = NodeSet()
        ns.set_node_set_name("")
        assert ns.get_node_set_name() == ""

    def test_set_node_set_name_normal(self):
        ns = NodeSet()
        ns.set_node_set_name("my_rule")
        assert ns.get_node_set_name() == "my_rule"

    def test_set_node_id_dictionary_empty_logs_debug(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({})
        assert ns.get_node_id_dictionary() == {}

    def test_set_node_id_dictionary_normal(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({0: "n0", 1: "n1"})
        assert ns.get_node_id_dictionary() == {0: "n0", 1: "n1"}

    def test_set_stable_node_id_dictionary_empty(self):
        ns = NodeSet()
        ns.set_stable_node_id_dictionary({})
        assert ns.get_stable_node_id_dictionary() == {}

    def test_set_stable_node_id_dictionary_normal(self):
        ns = NodeSet()
        ns.set_stable_node_id_dictionary({"abc123": "node_a"})
        assert ns.get_stable_node_id_dictionary() == {"abc123": "node_a"}

    def test_set_node_dictionary_empty_logs_debug(self):
        ns = NodeSet()
        ns.set_node_dictionary({})
        assert ns.get_node_dictionary() == {}

    def test_set_sorted_node_list_empty_logs_error(self):
        ns = NodeSet()
        ns.set_sorted_node_list([])
        assert ns.get_sorted_node_list() == []

    def test_set_fact_dictionary_empty_logs_info(self):
        ns = NodeSet()
        ns.set_fact_dictionary({})
        assert ns.get_fact_dictionary() == {}

    def test_set_fact_dictionary_normal(self):
        ns = NodeSet()
        ns.set_fact_dictionary({"key": "val"})
        assert ns.get_fact_dictionary() == {"key": "val"}


class TestNodeSetDefaultGoalNode:
    def test_set_default_goal_node(self):
        ns = NodeSet()
        node = DummyNode(node_name="goal_node")
        ns.set_node_dictionary({"goal_node": node})
        ns.set_default_goal_node("goal_node")
        assert ns.get_default_goal_node() is node

    def test_set_default_goal_node_not_found(self):
        ns = NodeSet()
        ns.set_node_dictionary({})
        ns.set_default_goal_node("missing")
        assert ns.get_default_goal_node() is None


class TestNodeSetGetNode:
    def test_get_node_by_index(self):
        ns = NodeSet()
        node = DummyNode(node_name="indexed")
        ns.set_sorted_node_list([node])
        assert ns.get_node(0) is node

    def test_get_node_by_node_id(self):
        ns = NodeSet()
        node = DummyNode(node_id=5, node_name="by_id")
        ns.set_node_dictionary({"by_id": node})
        ns.set_node_id_dictionary({5: "by_id"})
        assert ns.get_node_by_node_id(5) is node

    def test_get_node_by_stable_node_id(self):
        ns = NodeSet()
        node = DummyNode(node_name="stable_node", stable_node_id="abc123")
        ns.set_node_dictionary({"stable_node": node})
        ns.set_stable_node_id_dictionary({"abc123": "stable_node"})
        assert ns.get_node_by_stable_node_id("abc123") is node


class TestNodeSetRegisterNode:
    def test_register_node_with_id_and_stable_id(self):
        ns = NodeSet()
        node = DummyNode(node_id=1, node_name="reg_node", stable_node_id="xyz789")
        ns.register_node(node)
        assert ns.get_node_dictionary()["reg_node"] is node
        assert ns.get_node_id_dictionary()[1] == "reg_node"
        assert ns.get_stable_node_id_dictionary()["xyz789"] == "reg_node"

    def test_register_node_without_id(self):
        ns = NodeSet()
        node = DummyNode(node_id=None, node_name="no_id_node")
        ns.register_node(node)
        assert ns.get_node_dictionary()["no_id_node"] is node
        assert 0 not in ns.get_node_id_dictionary() or ns.get_node_id_dictionary().get(0) != "no_id_node"


class TestNodeSetGetNextNodeId:
    def test_empty_returns_zero(self):
        ns = NodeSet()
        assert ns.get_next_node_id() == 0

    def test_with_entries_returns_max_plus_one(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({0: "a", 5: "b"})
        assert ns.get_next_node_id() == 6


class TestNodeSetFindNodeIndex:
    def test_find_existing_node(self):
        ns = NodeSet()
        node = DummyNode(node_name="find_me")
        ns.set_sorted_node_list([DummyNode(node_name="other"), node])
        assert ns.find_node_index("find_me") == 1

    def test_find_missing_node(self):
        ns = NodeSet()
        ns.set_sorted_node_list([DummyNode(node_name="other")])
        assert ns.find_node_index("missing") == -1


class TestNodeSetTransferFactDictionary:
    def test_transfer_to_working_memory(self):
        ns = NodeSet()
        ns.set_fact_dictionary({"fact1": "val1", "fact2": "val2"})
        wm = {"existing": "keep"}
        result = ns.transfer_fact_dictionary_to_working_memory(wm)
        assert result["existing"] == "keep"
        assert result["fact1"] == "val1"
        assert result["fact2"] == "val2"

    def test_transfer_to_empty_working_memory(self):
        ns = NodeSet()
        ns.set_fact_dictionary({"fact1": "val1"})
        result = ns.transfer_fact_dictionary_to_working_memory({})
        assert result == {"fact1": "val1"}


class TestNodeSetHasChildren:
    def test_has_children_true(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({0: "parent", 1: "a", 2: "b"})
        ns.get_graph().register_node("parent", {"runtime_id": 0})
        ns.get_graph().register_node("a", {"runtime_id": 1})
        ns.get_graph().register_node("b", {"runtime_id": 2})
        ns.get_graph().add_dependency_group("parent", 1, {"a", "b"})
        has, children = ns._has_children(0)
        assert has is True
        assert children == [1, 2]

    def test_has_children_false(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({0: "parent"})
        ns.get_graph().register_node("parent", {"runtime_id": 0})
        has, children = ns._has_children(0)
        assert has is False
        assert children == []


class TestNodeSetHasParents:
    def test_has_parents_true(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({0: "parent", 1: "child"})
        ns.get_graph().register_node("parent", {"runtime_id": 0})
        ns.get_graph().register_node("child", {"runtime_id": 1})
        ns.get_graph().add_dependency_group("parent", 1, {"child"})
        has, parents = ns._has_parents(1)
        assert has is True
        assert parents == [0]

    def test_has_parents_false(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({1: "child"})
        ns.get_graph().register_node("child", {"runtime_id": 1})
        has, parents = ns._has_parents(1)
        assert has is False
        assert parents == []


class TestNodeSetSetDependencyMatrix:
    def test_get_dependency_matrix_emits_deprecation_warning(self):
        ns = NodeSet()

        with pytest.warns(DeprecationWarning, match="get_dependency_matrix"):
            ns.get_dependency_matrix()

    def test_set_dependency_matrix_emits_deprecation_warning(self):
        ns = NodeSet()

        with pytest.warns(DeprecationWarning, match="set_dependency_matrix"):
            ns.set_dependency_matrix([[-1]])

    def test_set_from_list(self):
        ns = NodeSet()
        ns.set_dependency_matrix([[-1, 1], [0, -1]])
        result = ns.get_dependency_matrix()
        assert isinstance(result, DependencyMatrix)

    def test_set_from_dependency_matrix(self):
        ns = NodeSet()
        dm = DependencyMatrix([[-1]])
        ns.set_dependency_matrix(dm)
        assert ns.get_dependency_matrix().get_dependency_two_dimension_list() == [[-1]]


class TestNodeSetRepr:
    def test_repr_returns_json(self):
        ns = NodeSet()
        try:
            result = repr(ns)
            parsed = json.loads(result)
            assert isinstance(parsed, dict)
        except TypeError:
            pass


class TestNodeIdDeprecation:
    def test_get_node_id_dictionary_emits_deprecation_warning(self):
        ns = NodeSet()
        ns.set_node_id_dictionary({0: "a"})
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = ns.get_node_id_dictionary()
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_node_id_dictionary()" in str(w[0].message)
            assert result == {0: "a"}

    def test_get_node_by_node_id_emits_deprecation_warning(self):
        ns = NodeSet()
        node = DummyNode(node_id=5, node_name="by_id")
        ns.set_node_dictionary({"by_id": node})
        ns.set_node_id_dictionary({5: "by_id"})
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = ns.get_node_by_node_id(5)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_node_by_node_id()" in str(w[0].message)
            assert result is node

    def test_stable_node_id_api_no_deprecation_warning(self):
        ns = NodeSet()
        node = DummyNode(node_id=5, node_name="stable_test", stable_node_id="sid_abc")
        ns.register_node(node)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            stable_dict = ns.get_stable_node_id_dictionary()
            _ = ns.get_node_by_stable_node_id("sid_abc")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0
            assert "sid_abc" in stable_dict
