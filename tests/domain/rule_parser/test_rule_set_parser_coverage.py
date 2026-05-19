"""
Additional coverage tests for rule_set_parser.py — targeting MISSED lines:
133/147/155-167 (handle_parent branches), 183 (handle_child ITEM),
201-212/224/229 (handle_list_item type paths), 315-335 (_handle_value_conclusion_node),
345-365 (_handle_expr_conclusion_node), 433/451-471/474 (_handle_statement_child),
487-503 (_handle_child_value_conclusion), 512-541 (_handle_child_comparison),
571-573/578-609 (_handling_virtual_node AND/OR + creation).
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.meta_data import MetaData
from src.domain.nodes.meta_type import MetaType
from src.domain.nodes.line_type import LineType
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.dependency import Dependency
from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes import node_id_utils
from src.domain.tokens.tokenizer_matcher_constant import TokenizerMatcherConstant


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


class _SnapshotValuesDict(dict):
    def values(self):
        return list(super().values())

    def keys(self):
        return list(super().keys())

    def items(self):
        return list(super().items())


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


def _mock_tokens_for(tokens_list, string_list):
    t = MagicMock()
    t.get_tokens_list.return_value = tokens_list
    t.get_tokens_string_list.return_value = string_list
    t.get_tokens_string.return_value = "".join(string_list)
    return t


def _register_mock_vc(parser, node_name, variable_name, node_id, fact_value_str="val"):
    mock_node = MagicMock()
    mock_node.get_node_name.return_value = node_name
    mock_node.get_node_id.return_value = node_id
    mock_node._node_id = node_id
    mock_node.get_variable_name.return_value = variable_name
    mock_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
    mock_node.get_fact_value.return_value = FactValue(fact_value_str)
    mock_node.get_tokens.return_value = MagicMock()
    mock_node.get_node_line.return_value = 1
    mock_node.get_stable_node_id.return_value = "stable_" + str(node_id)
    parser.get_node_set().register_node(mock_node)
    return mock_node


# ===================================================================
# handle_parent — existing node path (133) + pattern matching (155-167)
# ===================================================================


class TestHandleParentBranches:
    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_handle_parent_existing_node_reuses(self, MockVC, parser):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "applicant IS eligible"
        mock_node.get_node_id.return_value = 0
        mock_node.get_variable_name.return_value = "applicant"
        mock_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        mock_node.get_fact_value.return_value = FactValue("eligible")
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 1
        mock_node.get_stable_node_id.return_value = "stable_0"
        MockVC.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["applicant", "IS", "eligible"], ["L", "U", "M"]
            )
            parser.handle_parent("applicant IS eligible", 1, MetaData())

        node_dict = parser.get_node_set().get_node_dictionary()
        if "applicant IS eligible" in node_dict:
            with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
                mock_tok.return_value = _mock_tokens_for(
                    ["applicant", "IS", "eligible"], ["L", "U", "M"]
                )
                parser.handle_parent("applicant IS eligible", 2, MetaData())
            assert "applicant IS eligible" in parser.get_node_set().get_node_dictionary()

    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_handle_parent_value_conclusion_pattern(self, MockVC, parser):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "score IS 10"
        mock_node.get_node_id.return_value = 0
        mock_node.get_variable_name.return_value = "score"
        mock_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        mock_node.get_fact_value.return_value = FactValue("10")
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 1
        mock_node.get_stable_node_id.return_value = "stable_0"
        MockVC.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["score", "IS", "10"], ["L", "U", "N"]
            )
            parser.handle_parent("score IS 10", 1, MetaData())

    @patch("src.domain.rule_parser.rule_set_parser.ExprConclusionLine")
    def test_handle_parent_expr_conclusion_pattern(self, MockEC, parser):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "total IS CALC x + y"
        mock_node.get_node_id.return_value = 0
        mock_node.get_variable_name.return_value = "total"
        mock_node.get_line_type.return_value = LineType.EXPR_CONCLUSION
        mock_node.get_fact_value.return_value = FactValue("x + y")
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 1
        mock_node.get_stable_node_id.return_value = "stable_0"
        MockEC.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["total", "IS CALC", "x", "+", "y"], ["L", "U", "L", "C"]
            )
            parser.handle_parent("total IS CALC x + y", 1, MetaData())

    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_handle_parent_warning_pattern(self, MockVC, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["SOME", "UNKNOWN", "TEXT"], ["U", "U", "M"]
            )
            with patch.object(parser, 'handle_warning', return_value="warned"):
                parser.handle_parent("SOME UNKNOWN TEXT", 1, MetaData())

    def test_handle_parent_metadata_warning_value(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "msg", "AS", "STRING"], ["U", "U", "S"]
            )
            with patch.object(parser, 'handle_warning') as mock_warn:
                parser.handle_parent("INPUT msg AS STRING", 1, MetaData())


# ===================================================================
# handle_child — ITEM path (183)
# ===================================================================


class TestHandleChildItemPath:
    def test_handle_child_item_pattern(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "colours", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT colours AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["colours"] = FactValue(list(), FactValueType.LIST)
        parser.handle_child("INPUT colours AS LIST", "ITEM red", "", 2)

    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_handle_child_non_item_statement(self, MockVC, parser):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "status IS active"
        mock_node.get_node_id.return_value = 0
        mock_node.get_variable_name.return_value = "status"
        mock_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        mock_node.get_fact_value.return_value = FactValue("active")
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 1
        mock_node.get_stable_node_id.return_value = "stable_0"
        MockVC.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["status", "IS", "active"], ["L", "U", "M"]
            )
            parser.handle_parent("status IS active", 1, MetaData())


# ===================================================================
# handle_list_item — type paths (201-212) and FIXED meta (224, 229)
# ===================================================================


class TestHandleListItemTypePaths:
    def test_handle_list_item_date_type(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "dates", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT dates AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["dates"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT dates AS LIST", "01/01/2024", MetaType.INPUT)
        fv = input_dict["dates"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_double_type(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["FIXED", "prices", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("FIXED prices AS LIST", 1, MetaData())

        fact_dict = parser.get_node_set().get_fact_dictionary()
        fact_dict["prices"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("FIXED prices AS LIST", "3.14", MetaType.FIXED)
        fv = fact_dict["prices"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_integer_type(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "nums", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT nums AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["nums"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT nums AS LIST", "42", MetaType.INPUT)
        fv = input_dict["nums"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_hash_type(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "hashes", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT hashes AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["hashes"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT hashes AS LIST", "a1b2c3d4e5f6", MetaType.INPUT)
        fv = input_dict["hashes"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_url_type(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "urls", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT urls AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["urls"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT urls AS LIST", "http://example.com", MetaType.INPUT)
        fv = input_dict["urls"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_guid_type(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "ids", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT ids AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["ids"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT ids AS LIST", "12345678-1234-1234-1234-123456789012", MetaType.INPUT)
        fv = input_dict["ids"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_boolean_true(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "flags", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT flags AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["flags"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT flags AS LIST", "True", MetaType.INPUT)
        fv = input_dict["flags"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_boolean_false(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "flags", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT flags AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["flags"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT flags AS LIST", "False", MetaType.INPUT)
        fv = input_dict["flags"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_string_fallback(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "names", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT names AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["names"] = FactValue(list(), FactValueType.LIST)
        parser.handle_list_item("INPUT names AS LIST", "Alice", MetaType.INPUT)
        fv = input_dict["names"]
        assert len(fv.get_value()) > 0

    def test_handle_list_item_fixed_non_list_converts(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["FIXED", "items", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("FIXED items AS LIST", 1, MetaData())

        fact_dict = parser.get_node_set().get_fact_dictionary()
        fact_dict["items"] = FactValue("some_string", FactValueType.STRING)
        parser.handle_list_item("FIXED items AS LIST", "test_item", MetaType.FIXED)

    def test_handle_list_item_input_non_list_converts(self, parser):
        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["INPUT", "vals", "AS", "LIST"], ["U", "U", "S"]
            )
            parser.handle_parent("INPUT vals AS LIST", 1, MetaData())

        input_dict = parser.get_node_set().get_input_dictionary()
        input_dict["vals"] = FactValue("string_value", FactValueType.STRING)
        parser.handle_list_item("INPUT vals AS LIST", "42", MetaType.INPUT)


# ===================================================================
# _handle_value_conclusion_node (315-335)
# ===================================================================


class TestHandleValueConclusionNode:
    def test_value_conclusion_with_existing_parent(self, parser):
        _register_mock_vc(parser, "age", "age", 0, "18")

        from src.domain.nodes.value_conclusion_line import ValueConclusionLine
        node = MagicMock(spec=ValueConclusionLine)
        node.get_variable_name.return_value = "age"
        node.get_fact_value.return_value = FactValue("18")
        with patch.object(parser, '_add_dependency') as mock_add:
            parser._handle_value_conclusion_node(node, "age IS 18")
        mock_add.assert_called()

    def test_value_conclusion_warning_value(self, parser):
        from src.domain.nodes.value_conclusion_line import ValueConclusionLine
        node = MagicMock(spec=ValueConclusionLine)
        node.get_variable_name.return_value = "msg"
        node.get_fact_value.return_value = FactValue("WARNING")
        with patch.object(parser, 'handle_warning') as mock_warn:
            parser._handle_value_conclusion_node(node, "msg IS WARNING")
        mock_warn.assert_called_once()

    def test_value_conclusion_no_matching_parent(self, parser):
        from src.domain.nodes.value_conclusion_line import ValueConclusionLine
        node = MagicMock(spec=ValueConclusionLine)
        node.get_variable_name.return_value = "unique_var"
        node.get_fact_value.return_value = FactValue("val")
        parser._handle_value_conclusion_node(node, "unique_var IS val")
        dep_list = parser._RuleSetParser__dependencies
        assert len(dep_list) == 0


# ===================================================================
# _handle_expr_conclusion_node (345-365)
# ===================================================================


class TestHandleExprConclusionNode:
    def test_expr_conclusion_with_existing_parent(self, parser):
        _register_mock_vc(parser, "total", "total", 0, "x + y")

        from src.domain.nodes.expression_conclusion_line import ExprConclusionLine
        node = MagicMock(spec=ExprConclusionLine)
        node.get_variable_name.return_value = "total"
        node.get_fact_value.return_value = FactValue("x + y")
        with patch.object(parser, '_add_dependency') as mock_add:
            parser._handle_expr_conclusion_node(node, "total IS CALC x + y")
        mock_add.assert_called()

    def test_expr_conclusion_warning_value(self, parser):
        from src.domain.nodes.expression_conclusion_line import ExprConclusionLine
        node = MagicMock(spec=ExprConclusionLine)
        node.get_variable_name.return_value = "msg"
        node.get_fact_value.return_value = FactValue("WARNING")
        with patch.object(parser, 'handle_warning') as mock_warn:
            parser._handle_expr_conclusion_node(node, "msg IS CALC WARNING")
        mock_warn.assert_called_once()

    def test_expr_conclusion_no_matching_parent(self, parser):
        from src.domain.nodes.expression_conclusion_line import ExprConclusionLine
        node = MagicMock(spec=ExprConclusionLine)
        node.get_variable_name.return_value = "unique_var"
        node.get_fact_value.return_value = FactValue("some_expr")
        parser._handle_expr_conclusion_node(node, "unique_var IS CALC x")
        dep_list = parser._RuleSetParser__dependencies
        assert len(dep_list) == 0


# ===================================================================
# _handle_statement_child — existing child (433) and pattern paths (451-471)
# ===================================================================


class TestHandleStatementChildPaths:
    def test_existing_child_in_dictionary(self, parser):
        parent_node = _register_mock_vc(parser, "status IS active", "status", 0, "active")
        child_node = _register_mock_vc(parser, "score IS 10", "score", 1, "10")

        with patch.object(parser.get_node_set(), 'get_node', return_value=parent_node):
            parser._handle_statement_child("status IS active", "score IS 10", DependencyType.get_or(), 3)
        dep_list = parser._RuleSetParser__dependencies
        assert len(dep_list) > 0

    @patch("src.domain.rule_parser.rule_set_parser.IterateLine")
    def test_statement_child_iterate_pattern(self, MockIL, parser):
        parent_node = _register_mock_vc(parser, "status IS active", "status", 0, "active")

        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "ALL services IN LIST"
        mock_node.get_node_id.return_value = 1
        mock_node.get_variable_name.return_value = "services"
        mock_node.get_line_type.return_value = LineType.ITERATE
        mock_node.get_fact_value.return_value = FactValue("LIST")
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 2
        mock_node.get_stable_node_id.return_value = "stable_1"
        MockIL.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok, \
             patch.object(parser.get_node_set(), 'get_node', return_value=parent_node):
            mock_tok.return_value = _mock_tokens_for(
                ["ALL", "services", "IN", "LIST"], ["D", "I", "U"]
            )
            parser._handle_statement_child("status IS active", "ALL services IN LIST", DependencyType.get_or(), 2)

    @patch("src.domain.rule_parser.rule_set_parser.ComparisonLine")
    def test_statement_child_comparison_pattern(self, MockCL, parser):
        parent_node = _register_mock_vc(parser, "status IS active", "status", 0, "active")

        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "age > 18"
        mock_node.get_node_id.return_value = 1
        mock_node.get_variable_name.return_value = "age"
        mock_node.get_line_type.return_value = LineType.COMPARISON
        mock_node.get_fact_value.return_value = FactValue("18")
        mock_node.get_rhs.return_value = FactValue(18, FactValueType.INTEGER)
        mock_node.get_lhs.return_value = "age"
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 2
        mock_node.get_stable_node_id.return_value = "stable_1"
        MockCL.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok, \
             patch.object(parser.get_node_set(), 'get_node', return_value=parent_node):
            mock_tok.return_value = _mock_tokens_for(
                ["age", ">", "18"], ["L", "O", "N"]
            )
            parser._handle_statement_child("status IS active", "age > 18", DependencyType.get_and(), 2)

    @patch("src.domain.rule_parser.rule_set_parser.ExprConclusionLine")
    def test_statement_child_expr_pattern(self, MockEC, parser):
        parent_node = _register_mock_vc(parser, "status IS active", "status", 0, "active")

        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "total IS CALC x + y"
        mock_node.get_node_id.return_value = 1
        mock_node.get_variable_name.return_value = "total"
        mock_node.get_line_type.return_value = LineType.EXPR_CONCLUSION
        mock_node.get_fact_value.return_value = FactValue("x + y")
        mock_node.get_tokens.return_value = MagicMock()
        mock_node.get_node_line.return_value = 2
        mock_node.get_stable_node_id.return_value = "stable_1"
        MockEC.return_value = mock_node

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok, \
             patch.object(parser.get_node_set(), 'get_node', return_value=parent_node):
            mock_tok.return_value = _mock_tokens_for(
                ["total", "IS CALC", "x", "+", "y"], ["L", "U", "L", "C"]
            )
            parser._handle_statement_child("status IS active", "total IS CALC x + y", DependencyType.get_or(), 2)

    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_statement_child_warning_text(self, MockVC, parser):
        parent_node = _register_mock_vc(parser, "status IS active", "status", 0, "active")

        mock_vc_node = MagicMock()
        mock_vc_node.get_node_name.return_value = "WARNING"
        mock_vc_node.get_node_id.return_value = 1
        mock_vc_node.get_variable_name.return_value = "WARNING"
        mock_vc_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        mock_vc_node.get_fact_value.return_value = FactValue("WARNING")
        mock_vc_node.get_tokens.return_value = MagicMock()
        mock_vc_node.get_node_line.return_value = 2
        mock_vc_node.get_stable_node_id.return_value = "stable_1"
        MockVC.return_value = mock_vc_node

        with patch.object(parser, 'handle_warning', return_value="warned"), \
             patch.object(parser.get_node_set(), 'get_node', return_value=parent_node):
            with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
                mock_tok.return_value = _mock_tokens_for(
                    ["WARNING"], ["U"]
                )
                parser._handle_statement_child("status IS active", "WARNING", 0, 2)


# ===================================================================
# _handle_child_value_conclusion (487-503)
# ===================================================================


class TestHandleChildValueConclusion:
    def test_child_value_conclusion_with_matching_parent(self, parser):
        _register_mock_vc(parser, "age IS 18", "age", 0, "18")

        from src.domain.nodes.value_conclusion_line import ValueConclusionLine
        node = MagicMock(spec=ValueConclusionLine)
        node.get_variable_name.return_value = "age"
        node.get_fact_value.return_value = FactValue("18")
        node.get_node_name.return_value = "age IS 18"
        node.get_node_id.return_value = 1
        parser._handle_child_value_conclusion(node)

    def test_child_value_conclusion_warning(self, parser):
        from src.domain.nodes.value_conclusion_line import ValueConclusionLine
        node = MagicMock(spec=ValueConclusionLine)
        node.get_variable_name.return_value = "msg"
        node.get_fact_value.return_value = FactValue("WARNING")
        node.get_node_name.return_value = "msg IS WARNING"
        with patch.object(parser, 'handle_warning') as mock_warn:
            parser._handle_child_value_conclusion(node)
        mock_warn.assert_called_once_with("msg IS WARNING")

    def test_child_value_conclusion_no_matching_children(self, parser):
        from src.domain.nodes.value_conclusion_line import ValueConclusionLine
        node = MagicMock(spec=ValueConclusionLine)
        node.get_variable_name.return_value = "unique_var"
        node.get_fact_value.return_value = FactValue("some_val")
        node.get_node_name.return_value = "unique_var IS some_val"
        parser._handle_child_value_conclusion(node)


# ===================================================================
# _handle_child_comparison (512-541)
# ===================================================================


class TestHandleChildComparison:
    def test_child_comparison_string_rhs(self, parser):
        _register_mock_vc(parser, "age IS eligible", "age", 0, "eligible")

        from src.domain.nodes.comparison_line import ComparisonLine
        node = MagicMock(spec=ComparisonLine)
        node.get_rhs.return_value = FactValue("eligible", FactValueType.STRING)
        node.get_lhs.return_value = "age"
        node.get_fact_value.return_value = FactValue("eligible")
        node.get_node_name.return_value = "age > eligible"
        node.get_node_id.return_value = 1
        parser._handle_child_comparison(node)

    def test_child_comparison_non_string_rhs(self, parser):
        _register_mock_vc(parser, "age IS 18", "age", 0, "18")

        from src.domain.nodes.comparison_line import ComparisonLine
        node = MagicMock(spec=ComparisonLine)
        node.get_rhs.return_value = FactValue(18, FactValueType.INTEGER)
        node.get_lhs.return_value = "age"
        node.get_fact_value.return_value = FactValue(18)
        node.get_node_name.return_value = "age > 18"
        node.get_node_id.return_value = 1
        parser._handle_child_comparison(node)

    def test_child_comparison_warning_type(self, parser):
        from src.domain.nodes.comparison_line import ComparisonLine
        node = MagicMock(spec=ComparisonLine)
        node.get_rhs.return_value = FactValue("bad")
        node.get_lhs.return_value = "x"
        node.get_fact_value.return_value = FactValue("bad", FactValueType.WARNING)
        node.get_node_name.return_value = "x > bad"
        with patch.object(parser, 'handle_warning') as mock_warn:
            parser._handle_child_comparison(node)
        mock_warn.assert_called_once_with("x > bad")

    def test_child_comparison_no_matching_children(self, parser):
        from src.domain.nodes.comparison_line import ComparisonLine
        node = MagicMock(spec=ComparisonLine)
        node.get_rhs.return_value = FactValue(100, FactValueType.INTEGER)
        node.get_lhs.return_value = "unique_var"
        node.get_fact_value.return_value = FactValue(100)
        node.get_node_name.return_value = "unique_var > 100"
        node.get_node_id.return_value = 1
        parser._handle_child_comparison(node)


# ===================================================================
# _handling_virtual_node — AND/OR detection (571-573) and creation (578-609)
# ===================================================================


class TestHandlingVirtualNode:
    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_virtual_node_and_or_mixed(self, MockVC, parser):
        mock_virtual = MagicMock()
        mock_virtual.get_node_name.return_value = "VirtualNode-parent_node"
        mock_virtual.get_node_id.return_value = 3
        mock_virtual.get_variable_name.return_value = "VirtualNode-parent_node"
        mock_virtual.get_line_type.return_value = LineType.VALUE_CONCLUSION
        mock_virtual.get_tokens.return_value = MagicMock()
        mock_virtual.get_node_line.return_value = 1
        mock_virtual.get_stable_node_id.return_value = "stable_3"
        MockVC.return_value = mock_virtual

        parent_node = MagicMock()
        parent_node.get_node_name.return_value = "parent_node"
        parent_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        parent_node.get_node_line.return_value = 1

        and_child = MagicMock()
        and_child.get_node_name.return_value = "and_child"
        and_child.get_node_id.return_value = 1

        or_child = MagicMock()
        or_child.get_node_name.return_value = "or_child"
        or_child.get_node_id.return_value = 2

        and_dep = Dependency(parent_node, and_child, DependencyType.get_and())
        or_dep = Dependency(parent_node, or_child, DependencyType.get_or())
        dep_list = [and_dep, or_dep]

        node_dict = _SnapshotValuesDict({
            "parent_node": parent_node,
            "and_child": and_child,
            "or_child": or_child,
        })
        parser.get_node_set()._NodeSet__node_dictionary = node_dict

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["VirtualNode-parent_node"], ["U"]
            )
            result = parser._handling_virtual_node(dep_list)

        assert "VirtualNode-parent_node" in result
        assert len(dep_list) > 2

    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_virtual_node_mandatory_and(self, MockVC, parser):
        mock_virtual = MagicMock()
        mock_virtual.get_node_name.return_value = "VirtualNode-parent_mandatory"
        mock_virtual.get_node_id.return_value = 3
        mock_virtual.get_variable_name.return_value = "VirtualNode-parent_mandatory"
        mock_virtual.get_tokens.return_value = MagicMock()
        mock_virtual.get_node_line.return_value = 1
        mock_virtual.get_stable_node_id.return_value = "stable_3"
        MockVC.return_value = mock_virtual

        parent_node = MagicMock()
        parent_node.get_node_name.return_value = "parent_mandatory"
        parent_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        parent_node.get_node_line.return_value = 1

        mand_and_child = MagicMock()
        mand_and_child.get_node_name.return_value = "mand_and_child"
        mand_and_child.get_node_id.return_value = 1

        or_child = MagicMock()
        or_child.get_node_name.return_value = "or_child_2"
        or_child.get_node_id.return_value = 2

        mand_and_dep = Dependency(parent_node, mand_and_child, DependencyType.get_mandatory() | DependencyType.get_and())
        or_dep = Dependency(parent_node, or_child, DependencyType.get_or())
        dep_list = [mand_and_dep, or_dep]

        node_dict = _SnapshotValuesDict({
            "parent_mandatory": parent_node,
            "mand_and_child": mand_and_child,
            "or_child_2": or_child,
        })
        parser.get_node_set()._NodeSet__node_dictionary = node_dict

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["VirtualNode-parent_mandatory"], ["U"]
            )
            result = parser._handling_virtual_node(dep_list)

        assert "VirtualNode-parent_mandatory" in result

    @patch("src.domain.rule_parser.rule_set_parser.ExprConclusionLine")
    def test_virtual_node_expr_conclusion_type(self, MockEC, parser):
        mock_virtual = MagicMock()
        mock_virtual.get_node_name.return_value = "VirtualNode-expr_parent"
        mock_virtual.get_node_id.return_value = 3
        mock_virtual.get_variable_name.return_value = "VirtualNode-expr_parent"
        mock_virtual.get_tokens.return_value = MagicMock()
        mock_virtual.get_node_line.return_value = 1
        mock_virtual.get_stable_node_id.return_value = "stable_3"
        MockEC.return_value = mock_virtual

        parent_node = MagicMock()
        parent_node.get_node_name.return_value = "expr_parent"
        parent_node.get_line_type.return_value = LineType.EXPR_CONCLUSION
        parent_node.get_node_line.return_value = 1

        and_child = MagicMock()
        and_child.get_node_name.return_value = "and_child_3"
        and_child.get_node_id.return_value = 1

        or_child = MagicMock()
        or_child.get_node_name.return_value = "or_child_3"
        or_child.get_node_id.return_value = 2

        and_dep = Dependency(parent_node, and_child, DependencyType.get_and())
        or_dep = Dependency(parent_node, or_child, DependencyType.get_or())
        dep_list = [and_dep, or_dep]

        node_dict = _SnapshotValuesDict({
            "expr_parent": parent_node,
            "and_child_3": and_child,
            "or_child_3": or_child,
        })
        parser.get_node_set()._NodeSet__node_dictionary = node_dict

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["VirtualNode-expr_parent"], ["U"]
            )
            result = parser._handling_virtual_node(dep_list)

        assert "VirtualNode-expr_parent" in result

    def test_virtual_node_no_mixed_deps(self, parser):
        parent_node = MagicMock()
        parent_node.get_node_name.return_value = "only_or_parent"
        parent_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        parent_node.get_node_line.return_value = 1

        or_child = MagicMock()
        or_child.get_node_name.return_value = "or_only_child"
        or_child.get_node_id.return_value = 1

        or_dep = Dependency(parent_node, or_child, DependencyType.get_or())
        dep_list = [or_dep]

        node_dict = _SnapshotValuesDict({
            "only_or_parent": parent_node,
            "or_only_child": or_child,
        })
        parser.get_node_set()._NodeSet__node_dictionary = node_dict

        result = parser._handling_virtual_node(dep_list)
        assert "VirtualNode-only_or_parent" not in result

    @patch("src.domain.rule_parser.rule_set_parser.ValueConclusionLine")
    def test_virtual_node_reparents_and_deps(self, MockVC, parser):
        mock_virtual = MagicMock()
        mock_virtual.get_node_name.return_value = "VirtualNode-reparent_test"
        mock_virtual.get_node_id.return_value = 3
        mock_virtual.get_variable_name.return_value = "VirtualNode-reparent_test"
        mock_virtual.get_tokens.return_value = MagicMock()
        mock_virtual.get_node_line.return_value = 1
        mock_virtual.get_stable_node_id.return_value = "stable_3"
        MockVC.return_value = mock_virtual

        parent_node = MagicMock()
        parent_node.get_node_name.return_value = "reparent_test"
        parent_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        parent_node.get_node_line.return_value = 1

        and_child = MagicMock()
        and_child.get_node_name.return_value = "and_reparent_child"
        and_child.get_node_id.return_value = 1

        or_child = MagicMock()
        or_child.get_node_name.return_value = "or_reparent_child"
        or_child.get_node_id.return_value = 2

        and_dep = Dependency(parent_node, and_child, DependencyType.get_and())
        or_dep = Dependency(parent_node, or_child, DependencyType.get_or())
        dep_list = [and_dep, or_dep]

        node_dict = _SnapshotValuesDict({
            "reparent_test": parent_node,
            "and_reparent_child": and_child,
            "or_reparent_child": or_child,
        })
        parser.get_node_set()._NodeSet__node_dictionary = node_dict

        with patch("src.domain.rule_parser.rule_set_parser.Tokenizer.get_tokens") as mock_tok:
            mock_tok.return_value = _mock_tokens_for(
                ["VirtualNode-reparent_test"], ["U"]
            )
            result = parser._handling_virtual_node(dep_list)

        assert and_dep.get_parent_node().get_node_name() == "VirtualNode-reparent_test"
