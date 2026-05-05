import pytest
import re
from unittest.mock import MagicMock, patch

from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.meta_data import MetaData
from src.domain.nodes.meta_type import MetaType
from src.domain.nodes.line_type import LineType
from src.domain.nodes.dependency_type import DependencyType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes import node_id_utils
from src.shared.constants.tokenizer_matcher_constant import TokenizerMatcherConstant


_VALID_ENUM_NAMES = [
    "SPACE_MATCHER", "RULE_SET_MATCHER", "ITERATE_MATCHER", "CALCULATION_MATCHER",
    "QUOTED_MATCHER", "URL_MATCHER", "GUID_MATCHER", "HASH_MATCHER",
    "DATE_MATCHER", "DECIMAL_NUMBER_MATCHER", "OPERATOR_MATCHER", "NUMBER_MATCHER",
    "PARAGRAPH_MATCHER", "SECTION_MATCHER", "FUNCTION_MATCHER", "UPPER_MATCHER",
    "MIXED_MATCHER", "LOWER_MATCHER",
]

_pattern_cache = {}


def _mock_get_all_matcher():
    return [TokenizerMatcherConstant[name].value for name in _VALID_ENUM_NAMES]


def _mock_get_all_enums():
    return [TokenizerMatcherConstant[name] for name in _VALID_ENUM_NAMES]


def _mock_get_compiled_matcher(name):
    if name not in _VALID_ENUM_NAMES:
        return None
    if name in _pattern_cache:
        return _pattern_cache[name]
    try:
        pattern = re.compile(TokenizerMatcherConstant[name].value)
        _pattern_cache[name] = pattern
        return pattern
    except (re.error, KeyError):
        return None


class _ConcreteRuleSetParser(RuleSetParser):
    pass


@pytest.fixture(autouse=True)
def _reset_parse_context():
    node_id_utils.reset_parse_context()
    _pattern_cache.clear()
    with patch(
        "src.domain.tokens.tokenizer.TokenizerMatcherConstant.get_all_matcher",
        _mock_get_all_matcher,
    ), patch(
        "src.domain.tokens.tokenizer.TokenizerMatcherConstant.get_all_enums",
        _mock_get_all_enums,
    ), patch(
        "src.domain.tokens.tokenizer.TokenizerMatcherConstant.get_compiled_matcher",
        _mock_get_compiled_matcher,
    ):
        yield
    node_id_utils.reset_parse_context()


@pytest.fixture
def parser():
    p = _ConcreteRuleSetParser()
    p.create()
    return p


class TestRuleSetParserInit:
    def test_init_creates_node_set(self):
        p = _ConcreteRuleSetParser()
        ns = p.get_node_set()
        assert isinstance(ns, NodeSet)

    def test_init_default_source_name(self):
        p = _ConcreteRuleSetParser()
        assert p.get_source_name() == "__unknown_module__"


class TestRuleSetParserCreate:
    def test_create_resets_node_set(self, parser):
        old_ns = parser.get_node_set()
        parser.create()
        new_ns = parser.get_node_set()
        assert new_ns is not old_ns

    def test_create_resets_match_types(self, parser):
        parser.create()
        expected = LineType.get_all_values()
        assert parser._RuleSetParser__match_types == expected


class TestRuleSetParserSourceName:
    def test_set_source_name_valid(self, parser):
        parser.set_source_name("MyModule")
        assert parser.get_source_name() == "MyModule"

    def test_set_source_name_empty(self, parser):
        parser.set_source_name("")
        assert parser.get_source_name() == "__unknown_module__"

    def test_set_source_name_none(self, parser):
        parser.set_source_name(None)
        assert parser.get_source_name() == "__unknown_module__"


class TestRuleSetParserNodeSet:
    def test_set_node_set(self, parser):
        ns = NodeSet()
        parser.set_node_set(ns)
        assert parser.get_node_set() is ns


class TestRuleSetParserHandleWarning:
    def test_handle_warning_returns_message(self, parser):
        result = parser.handle_warning("bad_rule")
        assert "bad_rule" in result
        assert "not matched" in result

    def test_handle_warning_format(self, parser):
        result = parser.handle_warning("xyz")
        assert result == "xyz: rule format is not matched. Please check the format again"


class TestRuleSetParserHandleParent:
    def test_handle_parent_metadata_input(self, parser):
        parser.handle_parent("INPUT age AS STRING", 1, MetaData())
        assert parser.get_node_set() is not None

    def test_handle_parent_metadata_fixed(self, parser):
        parser.handle_parent("FIXED status IS True", 1, MetaData())
        assert parser.get_node_set() is not None

    def test_handle_parent_existing_node(self, parser):
        parser.handle_parent("applicant IS eligible", 1, MetaData())
        parser.handle_parent("applicant IS eligible", 2, MetaData())
        assert parser.get_node_set() is not None

    def test_handle_parent_value_conclusion(self, parser):
        parser.handle_parent("score IS 10", 1, MetaData())
        assert parser.get_node_set() is not None

    def test_handle_parent_with_metadata(self, parser):
        md = MetaData(reference="ref1", origin="orig1")
        parser.handle_parent("status IS active", 1, md)
        assert parser.get_node_set() is not None

    def test_handle_parent_expressions_conclusion(self, parser):
        parser.handle_parent("total IS CALC x + y", 1, MetaData())
        assert parser.get_node_set() is not None


class TestRuleSetParserHandleChild:
    def test_handle_child_item(self, parser):
        parser.handle_parent("INPUT colours AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        if "colours" in input_dict:
            parser.handle_child("INPUT colours AS LIST", "ITEM red", "", 2)

    def test_handle_child_statement_with_and(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_child("status IS active", "score IS 10", "AND", 2)

    def test_handle_child_statement_with_or(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_child("status IS active", "score IS 10", "OR", 2)

    def test_handle_child_statement_needs(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_child("status IS active", "score IS 10", "NEEDS", 2)

    def test_handle_child_statement_wants(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_child("status IS active", "score IS 10", "WANTS", 2)

    def test_handle_child_unknown_keyword(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_child("status IS active", "score IS 10", "UNKNOWN", 2)

    def test_handle_child_existing_node_in_dictionary(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_child("status IS active", "status IS active", "OR", 2)


class TestRuleSetParserHandleListItem:
    def test_handle_list_item_date(self, parser):
        parser.handle_parent("INPUT dates AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["dates"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT dates AS LIST", "01/01/2024", MetaType.INPUT)
        fv = input_dict["dates"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_double(self, parser):
        parser.handle_parent("FIXED prices AS LIST", 1, MetaData())
        fact_dict = parser.get_node_set().get_fact_dictionary()
        fact_dict["prices"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("FIXED prices AS LIST", "3.14", MetaType.FIXED)
        fv = fact_dict["prices"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_integer(self, parser):
        parser.handle_parent("INPUT nums AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["nums"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT nums AS LIST", "42", MetaType.INPUT)
        fv = input_dict["nums"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_boolean_true(self, parser):
        parser.handle_parent("INPUT flags AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["flags"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT flags AS LIST", "True", MetaType.INPUT)
        fv = input_dict["flags"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_boolean_false(self, parser):
        parser.handle_parent("INPUT flags AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["flags"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT flags AS LIST", "False", MetaType.INPUT)
        fv = input_dict["flags"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_hash(self, parser):
        parser.handle_parent("INPUT hashes AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["hashes"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT hashes AS LIST", "a1b2c3d4e5f6", MetaType.INPUT)
        fv = input_dict["hashes"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_url(self, parser):
        parser.handle_parent("INPUT urls AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["urls"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT urls AS LIST", "http://example.com", MetaType.INPUT)
        fv = input_dict["urls"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_guid(self, parser):
        parser.handle_parent("INPUT ids AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["ids"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT ids AS LIST", "12345678-1234-1234-1234-123456789012", MetaType.INPUT)
        fv = input_dict["ids"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_string_fallback(self, parser):
        parser.handle_parent("INPUT names AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["names"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT names AS LIST", "Alice", MetaType.INPUT)
        fv = input_dict["names"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_fixed_creates_list(self, parser):
        parser.handle_parent("FIXED items AS LIST", 1, MetaData())
        fact_dict = parser.get_node_set().get_fact_dictionary()
        fact_dict["items"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("FIXED items AS LIST", "test_item", MetaType.FIXED)
        fv = fact_dict["items"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_handle_list_item_non_list_becomes_list(self, parser):
        parser.handle_parent("INPUT vals AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        if "vals" in input_dict:
            input_dict["vals"] = FactValue("string_value", FactValueType.STRING)
            parser.handle_list_item("INPUT vals AS LIST", "42", MetaType.INPUT)
            fv = input_dict["vals"]
            assert fv.get_value_type() == FactValueType.LIST


class TestRuleSetParserCreateDependencyMatrix:
    def test_create_dependency_matrix_empty(self, parser):
        dm = parser.create_dependency_matrix()
        assert dm is not None

    def test_create_dependency_matrix_with_nodes(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        dm = parser.create_dependency_matrix()
        assert dm is not None

    def test_create_dependency_matrix_registers_isolated_nodes_on_graph(self, parser):
        parser.set_source_name("eligibility")
        node = MagicMock()
        node.get_node_name.return_value = "isolated"
        node.get_stable_node_id.return_value = "stable-isolated"
        node._node_id = 0
        parser.get_node_set().register_node(node)

        parser.create_dependency_matrix()

        graph = parser.get_node_set().get_graph()
        assert graph is not None
        assert graph.has_node("isolated") is True
        record = graph.get_node_record("isolated")
        assert record is not None
        assert record.module == "eligibility"
        assert record.stable_id == "stable-isolated"


class TestRuleSetParserParentNodeDataSet:
    def test_parent_node_data_set_with_metadata(self, parser):
        node = MagicMock()
        node.get_line_type.return_value = LineType.META
        node.get_meta_type.return_value = MetaType.INPUT
        node.get_variable_name.return_value = "age"
        node.get_fact_value.return_value = FactValue(25, FactValueType.INTEGER)
        parser._parent_node_data_set(node, 1, MetaData())
        assert "age" in parser.get_node_set().get_input_dictionary()

    def test_parent_node_data_set_with_fixed_metadata(self, parser):
        node = MagicMock()
        node.get_line_type.return_value = LineType.META
        node.get_meta_type.return_value = MetaType.FIXED
        node.get_variable_name.return_value = "status"
        node.get_fact_value.return_value = FactValue(True, FactValueType.BOOLEAN)
        parser._parent_node_data_set(node, 1, MetaData())
        assert "status" in parser.get_node_set().get_fact_dictionary()

    def test_parent_node_data_set_non_meta_registers_node(self, parser):
        node = MagicMock()
        node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        node.get_variable_name.return_value = "score"
        node.get_node_name.return_value = "score IS 10"
        node.get_node_line.return_value = None
        node.get_node_id.return_value = 0
        node.get_stable_node_id.return_value = "abc123"
        parser._parent_node_data_set(node, 1)
        assert "score IS 10" in parser.get_node_set().get_node_dictionary()

    def test_parent_node_data_set_without_meta_data(self, parser):
        node = MagicMock()
        node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        node.get_variable_name.return_value = "score"
        node.get_node_name.return_value = "score IS 10"
        node.get_node_line.return_value = 1
        node.get_node_id.return_value = 0
        node.get_stable_node_id.return_value = "abc123"
        parser._parent_node_data_set(node, 1, None)
        node.set_meta_data.assert_not_called()


class TestRuleSetParserDetermineDependencyType:
    def test_determine_and(self, parser):
        result = parser._determine_dependency_type("AND something")
        assert result & DependencyType.get_and() == DependencyType.get_and()

    def test_determine_or(self, parser):
        result = parser._determine_dependency_type("OR something")
        assert result & DependencyType.get_or() == DependencyType.get_or()

    def test_determine_wants(self, parser):
        result = parser._determine_dependency_type("WANTS something")
        assert result & DependencyType.get_or() == DependencyType.get_or()

    def test_determine_needs(self, parser):
        result = parser._determine_dependency_type("NEEDS something")
        assert result & DependencyType.get_mandatory() == DependencyType.get_mandatory()
        assert result & DependencyType.get_and() == DependencyType.get_and()

    def test_determine_unknown_returns_zero(self, parser):
        result = parser._determine_dependency_type("UNKNOWN something")
        assert result == 0


class TestRuleSetParserHandleItemChild:
    def test_handle_item_child_non_list_parent_warns(self, parser):
        parser._handle_item_child("status IS active", "ITEM value", "", 1)

    def test_handle_item_child_input_list(self, parser):
        parser.handle_parent("INPUT colours AS LIST", 1, MetaData())
        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["colours"] = FactValue(list(), FactValueType.LIST)
        parser._handle_item_child("INPUT colours AS LIST", "ITEM red", "", 2)

    def test_handle_item_child_fixed_list(self, parser):
        parser.handle_parent("FIXED items AS LIST", 1, MetaData())
        fact_dict = parser.get_node_set().get_fact_dictionary()
        fact_dict["items"] = FactValue(list(), FactValueType.LIST)
        parser._handle_item_child("FIXED items AS LIST", "ITEM value", "", 2)


class TestRuleSetParserHandleStatementChild:
    def test_handle_statement_child_value_conclusion(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser._handle_statement_child("status IS active", "score IS 10", DependencyType.get_or(), 2)

    def test_handle_statement_child_comparison(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser._handle_statement_child("status IS active", "age > 18", DependencyType.get_and(), 2)

    def test_handle_statement_child_existing_node(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_parent("score IS 10", 2, MetaData())
        parser._handle_statement_child("status IS active", "score IS 10", DependencyType.get_or(), 3)

    def test_handle_statement_child_warning_text(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser._handle_statement_child("status IS active", "WARNING", 0, 2)


class TestRuleSetParserApplyDebugLabel:
    def test_apply_debug_label_with_variable_name(self, parser):
        node = MagicMock()
        node.get_variable_name.return_value = "score"
        node.get_node_name.return_value = "score IS 10"
        node.get_node_line.return_value = 5
        parser._apply_debug_label(node)
        node.set_debug_label.assert_called_once()
        label = node.set_debug_label.call_args[0][0]
        assert "score" in label

    def test_apply_debug_label_fallback_to_node_name(self, parser):
        node = MagicMock()
        node.get_variable_name.return_value = None
        node.get_node_name.return_value = "status IS active"
        node.get_node_line.return_value = 3
        parser._apply_debug_label(node)
        label = node.set_debug_label.call_args[0][0]
        assert "status IS active" in label

    def test_apply_debug_label_no_line(self, parser):
        node = MagicMock()
        node.get_variable_name.return_value = "var"
        node.get_node_name.return_value = None
        node.get_node_line.return_value = None
        parser._apply_debug_label(node)
        label = node.set_debug_label.call_args[0][0]
        assert ":0:" in label

    def test_apply_debug_label_anonymous(self, parser):
        node = MagicMock()
        node.get_variable_name.return_value = None
        node.get_node_name.return_value = None
        node.get_node_line.return_value = 1
        parser._apply_debug_label(node)
        label = node.set_debug_label.call_args[0][0]
        assert "__anonymous__" in label


class TestRuleSetParserGetDependencyMatrixSize:
    def test_empty_returns_zero(self, parser):
        result = parser._get_dependency_matrix_size([])
        assert result == 0

    def test_with_dependencies(self, parser):
        parser.handle_parent("status IS active", 1, MetaData())
        parser.handle_parent("score IS 10", 2, MetaData())
        parser._handle_statement_child("status IS active", "score IS 10", DependencyType.get_or(), 3)
        dep_list = parser._RuleSetParser__dependencies
        assert len(dep_list) >= 0


class TestRuleSetParserHandleNotKnownManOptPos:
    def test_returns_base_when_no_modifier(self, parser):
        result = parser._handle_not_known_man_opt_pos("AND something", DependencyType.get_and())
        assert result & DependencyType.get_and() == DependencyType.get_and()

    def test_negative_dependency_type(self, parser):
        result = parser._handle_not_known_man_opt_pos("AND something", -1)
        assert result == -1

    def test_or_base_with_no_modifier(self, parser):
        result = parser._handle_not_known_man_opt_pos("OR something", DependencyType.get_or())
        assert result & DependencyType.get_or() == DependencyType.get_or()
