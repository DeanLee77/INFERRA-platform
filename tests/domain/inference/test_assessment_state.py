import json
from unittest.mock import MagicMock, patch

from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.assessment_state import AssessmentState
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.state import FactSource
from src.domain.state.layered_fact_store import LayeredFactStore
from src.domain.tokens.token import Token


class DummyNode(Node):
    def __init__(self, line_type=LineType.VALUE_CONCLUSION, tokens_list=None,
                 node_id=0, variable_name="dummy", node_name="dummy"):
        super().__init__(id=node_id)
        self._line_type = line_type
        self._tokens = Token(tokens_list or [], [], "")
        self._node_name = node_name
        self._variable_name = variable_name

    def initialisation(self, parent_text, tokens):
        pass

    def get_line_type(self):
        return self._line_type

    def self_evaluate(self, working_memory):
        return FactValue(True)


class DummyComparisonLine(ComparisonLine):
    def __init__(self, operator="=="):
        Node.__init__(self, id=1)
        self._line_type = LineType.COMPARISON
        self._tokens = Token([], [], "")
        self._node_name = "comparison"
        self._variable_name = "comparison"
        self._ComparisonLine__operator_string = operator

    def initialisation(self, child_text, tokens):
        pass


class TestAssessmentStateInit:
    def test_default_init_creates_layered_store(self):
        state = AssessmentState()
        assert isinstance(state.get_fact_store(), LayeredFactStore)

    def test_custom_fact_store(self):
        mock_store = MagicMock()
        state = AssessmentState(fact_store=mock_store)
        assert state.get_fact_store() is mock_store

    def test_default_lists_empty(self):
        state = AssessmentState()
        assert state.get_inclusive_list() == []
        assert state.get_exclusive_list() == []
        assert state.get_summary_list() == []
        assert state.get_mandatory_list() == []


class TestSetFactMergeLogic:
    def test_set_fact_empty_name_ignored(self):
        state = AssessmentState()
        state.set_fact("", FactValue(1))
        assert state.get_working_memory() == {}

    def test_set_fact_new_key(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(10))
        assert state.get_fact("x").get_value() == 10

    def test_set_fact_overwrite_non_list(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(1))
        state.set_fact("x", FactValue(2))
        assert state.get_fact("x").get_value() == 2

    def test_set_fact_append_to_existing_list(self):
        state = AssessmentState()
        state.set_fact("x", FactValue([FactValue(1)], FactValueType.LIST))
        state.set_fact("x", FactValue(2))
        assert state.get_fact("x").get_value_type() == FactValueType.LIST
        assert len(state.get_fact("x").get_value()) == 2

    def test_set_fact_with_node_creates_list_when_is_token(self):
        state = AssessmentState()
        node = DummyNode(tokens_list=["IS"])
        state.set_fact("x", FactValue("first"))
        state.set_fact("x", FactValue("second"), node=node)
        assert state.get_fact("x").get_value_type() == FactValueType.LIST
        assert len(state.get_fact("x").get_value()) == 2

    def test_set_fact_with_comparison_eq_node_creates_list(self):
        state = AssessmentState()
        node = DummyComparisonLine("==")
        state.set_fact("x", FactValue("first"))
        state.set_fact("x", FactValue("second"), node=node)
        assert state.get_fact("x").get_value_type() == FactValueType.LIST

    def test_set_fact_with_non_eq_comparison_no_list(self):
        state = AssessmentState()
        node = DummyComparisonLine(">")
        state.set_fact("x", FactValue("first"))
        state.set_fact("x", FactValue("second"), node=node)
        assert state.get_fact("x").get_value() == "second"

    def test_set_fact_to_inferred_layer(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(1), source=FactSource.INFERRED)
        assert state.get_fact_sources("x") == {FactSource.INFERRED}

    def test_set_fact_to_semantic_layer(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(1), source=FactSource.SEMANTIC)
        assert state.get_fact_sources("x") == {FactSource.SEMANTIC}


class TestLookupWorkingMemory:
    def test_lookup_empty_key_returns_none(self):
        state = AssessmentState()
        assert state.lookup_working_memory("") is None

    def test_lookup_missing_key_returns_none(self):
        state = AssessmentState()
        assert state.lookup_working_memory("missing") is None

    def test_lookup_returns_asserted_first(self):
        state = AssessmentState()
        state.set_fact("k", FactValue("A"), source=FactSource.ASSERTED)
        state.set_fact("k", FactValue("I"), source=FactSource.INFERRED)
        assert state.lookup_working_memory("k").get_value() == "A"

    def test_lookup_returns_inferred_over_semantic(self):
        state = AssessmentState()
        state.set_fact("k", FactValue("I"), source=FactSource.INFERRED)
        state.set_fact("k", FactValue("S"), source=FactSource.SEMANTIC)
        assert state.lookup_working_memory("k").get_value() == "I"

    def test_lookup_semantic_only(self):
        state = AssessmentState()
        state.set_fact("k", FactValue("S"), source=FactSource.SEMANTIC)
        assert state.lookup_working_memory("k").get_value() == "S"


class TestGetFact:
    def test_get_fact_delegates_to_lookup(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(42))
        assert state.get_fact("x").get_value() == 42

    def test_get_fact_missing_returns_none(self):
        state = AssessmentState()
        assert state.get_fact("nope") is None


class TestRemoveFact:
    def test_remove_fact_empty_name_ignored(self):
        state = AssessmentState()
        state.remove_fact("")

    def test_remove_fact_all_layers(self):
        state = AssessmentState()
        state.set_fact("k", FactValue("A"), source=FactSource.ASSERTED)
        state.set_fact("k", FactValue("I"), source=FactSource.INFERRED)
        state.remove_fact("k")
        assert state.get_fact("k") is None

    def test_remove_fact_specific_layer(self):
        state = AssessmentState()
        state.set_fact("k", FactValue("A"), source=FactSource.ASSERTED)
        state.set_fact("k", FactValue("I"), source=FactSource.INFERRED)
        state.remove_fact("k", source=FactSource.INFERRED)
        assert state.get_fact("k").get_value() == "A"


class TestInvalidateLayer:
    def test_invalidate_inferred_layer(self):
        state = AssessmentState()
        state.set_fact("k", FactValue("A"), source=FactSource.ASSERTED)
        state.set_fact("k2", FactValue("I"), source=FactSource.INFERRED)
        state.invalidate_layer(FactSource.INFERRED)
        assert state.get_fact_sources("k2") == set()
        assert state.get_fact("k").get_value() == "A"


class TestInclusiveList:
    def test_set_get_inclusive_list(self):
        state = AssessmentState()
        state.set_inclusive_list(["a", "b"])
        assert state.get_inclusive_list() == ["a", "b"]

    def test_is_in_inclusive_list_true(self):
        state = AssessmentState()
        state.set_inclusive_list(["a"])
        assert state.is_in_inclusive_list("a") is True

    def test_is_in_inclusive_list_false(self):
        state = AssessmentState()
        assert state.is_in_inclusive_list("z") is False

    def test_is_in_inclusive_list_empty_name(self):
        state = AssessmentState()
        assert state.is_in_inclusive_list("") is False


class TestSummaryList:
    def test_set_get_summary_list(self):
        state = AssessmentState()
        state.set_summary_list(["s1"])
        assert state.get_summary_list() == ["s1"]

    def test_set_summary_list_empty(self):
        state = AssessmentState()
        state.set_summary_list([])
        assert state.get_summary_list() == []

    def test_add_item_to_summary_list(self):
        state = AssessmentState()
        state.add_item_to_summary_list("s1")
        assert "s1" in state.get_summary_list()

    def test_add_item_no_duplicate(self):
        state = AssessmentState()
        state.add_item_to_summary_list("s1")
        state.add_item_to_summary_list("s1")
        assert state.get_summary_list().count("s1") == 1

    def test_add_item_empty_name_ignored(self):
        state = AssessmentState()
        state.add_item_to_summary_list("")
        assert state.get_summary_list() == []


class TestExclusiveList:
    def test_set_get_exclusive_list(self):
        state = AssessmentState()
        state.set_exclusive_list(["e1"])
        assert state.get_exclusive_list() == ["e1"]

    def test_set_exclusive_list_empty(self):
        state = AssessmentState()
        state.set_exclusive_list([])
        assert state.get_exclusive_list() == []

    def test_is_in_exclusive_list_true(self):
        state = AssessmentState()
        state.set_exclusive_list(["e1"])
        assert state.is_in_exclusive_list("e1") is True

    def test_is_in_exclusive_list_false(self):
        state = AssessmentState()
        assert state.is_in_exclusive_list("z") is False

    def test_is_in_exclusive_list_empty_name(self):
        state = AssessmentState()
        assert state.is_in_exclusive_list("") is False


class TestMandatoryList:
    def test_set_get_mandatory_list(self):
        state = AssessmentState()
        state.set_mandatory_list(["m1", "m2"])
        assert state.get_mandatory_list() == ["m1", "m2"]

    def test_set_mandatory_list_empty(self):
        state = AssessmentState()
        state.set_mandatory_list([])
        assert state.get_mandatory_list() == []

    def test_add_item_to_mandatory_list(self):
        state = AssessmentState()
        state.add_item_to_mandatory_list("m1")
        assert "m1" in state.get_mandatory_list()

    def test_add_item_no_duplicate(self):
        state = AssessmentState()
        state.add_item_to_mandatory_list("m1")
        state.add_item_to_mandatory_list("m1")
        assert state.get_mandatory_list().count("m1") == 1

    def test_add_item_empty_name_ignored(self):
        state = AssessmentState()
        state.add_item_to_mandatory_list("")
        assert state.get_mandatory_list() == []

    def test_is_in_mandatory_list_true(self):
        state = AssessmentState()
        state.set_mandatory_list(["m1"])
        assert state.is_in_mandatory_list("m1") is True

    def test_is_in_mandatory_list_false(self):
        state = AssessmentState()
        assert state.is_in_mandatory_list("nope") is False

    def test_all_mandatory_node_determined_true(self):
        state = AssessmentState()
        state.set_mandatory_list(["a", "b"])
        state.set_fact("a", FactValue(1))
        state.set_fact("b", FactValue(2))
        assert state.all_mandatory_node_determined() is True

    def test_all_mandatory_node_determined_false(self):
        state = AssessmentState()
        state.set_mandatory_list(["a", "b"])
        state.set_fact("a", FactValue(1))
        assert state.all_mandatory_node_determined() is False

    def test_all_mandatory_node_determined_empty(self):
        state = AssessmentState()
        assert state.all_mandatory_node_determined() is True

    def test_all_mandatory_cross_layer(self):
        state = AssessmentState()
        state.set_mandatory_list(["a", "b"])
        state.set_fact("a", FactValue(1), source=FactSource.ASSERTED)
        state.set_fact("b", FactValue(2), source=FactSource.INFERRED)
        assert state.all_mandatory_node_determined() is True


class TestSetWorkingMemory:
    def test_set_working_memory_clears_other_layers(self):
        state = AssessmentState()
        state.set_fact("old", FactValue("I"), source=FactSource.INFERRED)
        state.set_working_memory({"new": FactValue("V")})
        assert state.get_fact_sources("old") == set()
        assert state.get_fact("new").get_value() == "V"

    def test_set_working_memory_empty(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(1))
        state.set_working_memory({})
        assert state.get_working_memory() == {}


class TestTransferFactMapToWorkingMemory:
    def test_transfer_from_node_set(self):
        node_set = MagicMock()
        node_set.get_fact_dictionary.return_value = {"k1": FactValue("v1"), "k2": FactValue("v2")}
        state = AssessmentState()
        state.transfer_fact_map_to_working_memory(node_set)
        assert state.get_fact("k1").get_value() == "v1"
        assert state.get_fact("k2").get_value() == "v2"

    def test_transfer_none_node_set(self):
        state = AssessmentState()
        state.transfer_fact_map_to_working_memory(None)
        assert state.get_working_memory() == {}

    def test_transfer_empty_fact_dictionary(self):
        node_set = MagicMock()
        node_set.get_fact_dictionary.return_value = {}
        state = AssessmentState()
        state.transfer_fact_map_to_working_memory(node_set)
        assert state.get_working_memory() == {}


class TestShouldCreateList:
    def test_is_token_returns_true(self):
        state = AssessmentState()
        node = DummyNode(tokens_list=["IS"])
        assert state._should_create_list(node) is True

    def test_no_is_token_no_comparison(self):
        state = AssessmentState()
        node = DummyNode(tokens_list=["AND"])
        assert state._should_create_list(node) is False

    def test_comparison_eq_returns_true(self):
        state = AssessmentState()
        node = DummyComparisonLine("==")
        assert state._should_create_list(node) is True

    def test_comparison_neq_returns_false(self):
        state = AssessmentState()
        node = DummyComparisonLine(">")
        assert state._should_create_list(node) is False


class TestMergeExistingFact:
    def test_merge_list_appends(self):
        state = AssessmentState()
        existing = FactValue([FactValue(1)], FactValueType.LIST)
        incoming = FactValue(2)
        result = state._merge_existing_fact(existing, incoming, None)
        assert result is None
        assert len(existing.get_value()) == 2

    def test_merge_with_is_node_creates_list(self):
        state = AssessmentState()
        existing = FactValue("a")
        incoming = FactValue("b")
        node = DummyNode(tokens_list=["IS"])
        result = state._merge_existing_fact(existing, incoming, node)
        assert result.get_value_type() == FactValueType.LIST
        assert len(result.get_value()) == 2

    def test_merge_overwrite_no_node(self):
        state = AssessmentState()
        existing = FactValue("a")
        incoming = FactValue("b")
        result = state._merge_existing_fact(existing, incoming, None)
        assert result.get_value() == "b"

    def test_merge_no_list_node_no_is(self):
        state = AssessmentState()
        existing = FactValue("a")
        incoming = FactValue("b")
        node = DummyNode(tokens_list=["AND"])
        result = state._merge_existing_fact(existing, incoming, node)
        assert result.get_value() == "b"


class TestRepr:
    def test_repr_returns_valid_json(self):
        state = AssessmentState()
        state.set_fact("x", FactValue(1))
        state.set_mandatory_list(["m1"])
        result = json.loads(repr(state))
        assert "working_memory" in result
        assert "mandatory_list" in result
        assert result["mandatory_list"] == ["m1"]
