import json
from unittest.mock import MagicMock

from src.domain.inference.assessment import Assessment
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue


def _make_node_set(goal_node_name="goal_node", node_index=0, node_name="Goal Node"):
    node = MagicMock(spec=Node)
    node.get_node_name.return_value = node_name
    node.get_variable_name.return_value = goal_node_name
    node.get_node_id.return_value = 0
    node.get_line_type.return_value = LineType.VALUE_CONCLUSION

    node_set = MagicMock()
    node_set.get_node_dictionary.return_value = {goal_node_name: node}
    node_set.find_node_index.return_value = node_index
    return node_set, node


class TestAssessmentInit:
    def test_default_init(self):
        a = Assessment()
        assert a.get_assessment_name() is None
        assert a.get_goal_node() is None
        assert a.get_goal_node_index() == -1
        assert a.get_mandatory_list() == []
        assert a.get_summary_list() == []
        assert a.get_inclusive_list() == []
        assert a.get_exclusive_list() == []
        assert a.get_node_to_be_asked() is None
        assert a.get_aux_node_to_be_asked() is None

    def test_init_with_node_set_and_goal(self):
        ns, node = _make_node_set()
        a = Assessment(node_set=ns, goal_node_name="goal_node")
        assert a.get_goal_node() is node
        assert a.get_goal_node_index() == 0
        assert a.get_assessment_name() == "Goal Node"

    def test_init_with_none_node_set(self):
        a = Assessment(node_set=None, goal_node_name="x")
        assert a.get_goal_node() is None

    def test_init_with_none_goal_name(self):
        ns, _ = _make_node_set()
        a = Assessment(node_set=ns, goal_node_name=None)
        assert a.get_goal_node() is None

    def test_init_with_missing_goal_in_dict(self):
        ns, _ = _make_node_set()
        a = Assessment(node_set=ns, goal_node_name="nonexistent")
        assert a.get_goal_node() is None


class TestAssessmentGoalNode:
    def test_set_goal_node(self):
        ns, node = _make_node_set(node_name="New Goal")
        a = Assessment()
        a.set_goal_node(ns, "goal_node")
        assert a.get_goal_node() is node
        assert a.get_goal_node_index() == 0

    def test_set_assessment_resets_node_to_be_asked(self):
        ns, _ = _make_node_set()
        a = Assessment()
        a.set_node_to_be_asked(MagicMock())
        a.set_assessment(ns, "goal_node")
        assert a.get_node_to_be_asked() is None


class TestAssessmentName:
    def test_name_from_goal_node(self):
        ns, _ = _make_node_set(node_name="My Rule")
        a = Assessment(node_set=ns, goal_node_name="goal_node")
        assert a.get_assessment_name() == "My Rule"

    def test_name_fallback_when_goal_node_none(self):
        ns, _ = _make_node_set()
        ns.get_node_dictionary.return_value = {}
        a = Assessment(node_set=ns, goal_node_name="fallback_name")
        assert a.get_assessment_name() == "fallback_name"


class TestMandatoryList:
    def test_get_set_mandatory_list(self):
        a = Assessment()
        a.set_mandatory_list(["n1", "n2"])
        assert a.get_mandatory_list() == ["n1", "n2"]

    def test_is_in_mandatory_list(self):
        a = Assessment()
        a.set_mandatory_list(["n1", "n2"])
        assert a.is_in_mandatory_list("n1") is True
        assert a.is_in_mandatory_list("n3") is False

    def test_add_item_into_mandatory_list(self):
        a = Assessment()
        a.add_item_into_mandatory_list("n1")
        assert "n1" in a.get_mandatory_list()

    def test_is_all_mandatory_item_determined_true(self):
        a = Assessment()
        a.set_mandatory_list(["x", "y"])
        assert a.is_all_mandatory_item_determined({"x": 1, "y": 2}) is True

    def test_is_all_mandatory_item_determined_false(self):
        a = Assessment()
        a.set_mandatory_list(["x", "y"])
        assert a.is_all_mandatory_item_determined({"x": 1}) is False

    def test_is_all_mandatory_item_determined_empty(self):
        a = Assessment()
        assert a.is_all_mandatory_item_determined({}) is True


class TestInclusiveList:
    def test_get_set_inclusive_list(self):
        a = Assessment()
        a.set_inclusive_list(["a", "b"])
        assert a.get_inclusive_list() == ["a", "b"]

    def test_add_item_into_inclusive_list(self):
        a = Assessment()
        a.add_item_into_inclusive_list("x")
        assert "x" in a.get_inclusive_list()

    def test_is_in_inclusive_list_true(self):
        a = Assessment()
        a.set_inclusive_list(["a"])
        assert a.is_in_inclusive_list("a") is True

    def test_is_in_inclusive_list_false(self):
        a = Assessment()
        assert a.is_in_inclusive_list("z") is False

    def test_is_in_inclusive_list_empty_name(self):
        a = Assessment()
        assert a.is_in_inclusive_list("") is False


class TestSummaryList:
    def test_get_set_summary_list(self):
        a = Assessment()
        a.set_summary_list(["s1"])
        assert a.get_summary_list() == ["s1"]

    def test_set_summary_list_empty(self):
        a = Assessment()
        a.set_summary_list([])
        assert a.get_summary_list() == []

    def test_add_item_to_summary_list(self):
        a = Assessment()
        a.add_item_to_summary_list("s1")
        assert "s1" in a.get_summary_list()

    def test_add_item_to_summary_list_no_duplicate(self):
        a = Assessment()
        a.add_item_to_summary_list("s1")
        a.add_item_to_summary_list("s1")
        assert a.get_summary_list().count("s1") == 1

    def test_add_item_to_summary_list_empty_node(self):
        a = Assessment()
        a.add_item_to_summary_list("")
        assert a.get_summary_list() == []


class TestExclusiveList:
    def test_get_set_exclusive_list(self):
        a = Assessment()
        a.set_exclusive_list(["e1"])
        assert a.get_exclusive_list() == ["e1"]

    def test_set_exclusive_list_empty(self):
        a = Assessment()
        a.set_exclusive_list([])
        assert a.get_exclusive_list() == []

    def test_is_in_exclusive_list_true(self):
        a = Assessment()
        a.set_exclusive_list(["e1"])
        assert a.is_in_exclusive_list("e1") is True

    def test_is_in_exclusive_list_false(self):
        a = Assessment()
        assert a.is_in_exclusive_list("nope") is False

    def test_is_in_exclusive_list_empty_name(self):
        a = Assessment()
        assert a.is_in_exclusive_list("") is False


class TestNodeToBeAsked:
    def test_set_get_node_to_be_asked(self):
        a = Assessment()
        node = MagicMock()
        a.set_node_to_be_asked(node)
        assert a.get_node_to_be_asked() is node

    def test_set_node_to_be_asked_none(self):
        a = Assessment()
        a.set_node_to_be_asked(MagicMock())
        a.set_node_to_be_asked(None)
        assert a.get_node_to_be_asked() is None

    def test_set_get_aux_node_to_be_asked(self):
        a = Assessment()
        node = MagicMock()
        a.set_aux_node_to_be_asked(node)
        assert a.get_aux_node_to_be_asked() is node

    def test_set_aux_node_to_be_asked_none(self):
        a = Assessment()
        a.set_aux_node_to_be_asked(MagicMock())
        a.set_aux_node_to_be_asked(None)
        assert a.get_aux_node_to_be_asked() is None


class TestAssessmentRepr:
    def test_repr_returns_valid_json(self):
        a = Assessment()
        a.set_mandatory_list(["m1"])
        a.set_summary_list(["s1"])
        a.set_inclusive_list(["i1"])
        a.set_exclusive_list(["e1"])
        result = json.loads(repr(a))
        assert result["mandatory_list"] == ["m1"]
        assert result["summary_list"] == ["s1"]
        assert result["inclusive_list"] == ["i1"]
        assert result["exclusive_list"] == ["e1"]

    def test_repr_default_values(self):
        a = Assessment()
        result = json.loads(repr(a))
        assert result["assessment_name"] is None
        assert result["goal_node_index"] == -1
