import json
import pytest
from datetime import datetime
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.tokens import Token


class ConcreteComparisonLine(ComparisonLine):
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        pass


def _make_token(tokens_list, tokens_string_list):
    return Token(tokens_list=tokens_list, tokens_string_list=tokens_string_list)


def _make_cl(**kwargs):
    cl = ConcreteComparisonLine(**kwargs)
    cl._ComparisonLine__operator_string = None
    cl._ComparisonLine__lhs = None
    cl._ComparisonLine__rhs = None
    return cl


class TestComparisonLineInit:
    def test_default_init(self):
        cl = _make_cl()
        assert cl.get_rule_name() is None
        assert cl.get_lhs() is None
        assert cl.get_rhs() is None
        assert cl.get_operator() is None

    def test_init_with_id(self):
        cl = _make_cl(id=5)
        assert cl.get_node_id() == 5

    def test_line_type_is_comparison(self):
        cl = _make_cl()
        assert cl.get_line_type() == LineType.COMPARISON


class TestComparisonLineInitialisation:
    def test_initialisation_with_equals_operator(self):
        cl = _make_cl()
        tokens = _make_token(["x", "=", "5"], ["L", "O", "No"])
        cl._initialisation("x = 5", tokens)
        assert cl.get_operator() == "=="
        assert cl.get_lhs() == "x"

    def test_initialisation_with_gt_operator(self):
        cl = _make_cl()
        tokens = _make_token(["x", ">", "5"], ["L", "O", "No"])
        cl._initialisation("x > 5", tokens)
        assert cl.get_operator() == ">"

    def test_initialisation_with_lt_operator(self):
        cl = _make_cl()
        tokens = _make_token(["x", "<", "5"], ["L", "O", "No"])
        cl._initialisation("x < 5", tokens)
        assert cl.get_operator() == "<"

    def test_initialisation_with_gte_operator(self):
        cl = _make_cl()
        tokens = _make_token(["x", ">=", "5"], ["L", "O", "No"])
        cl._initialisation("x >= 5", tokens)
        assert cl.get_operator() == ">="

    def test_initialisation_with_lte_operator(self):
        cl = _make_cl()
        tokens = _make_token(["x", "<=", "5"], ["L", "O", "No"])
        cl._initialisation("x <= 5", tokens)
        assert cl.get_operator() == "<="

    def test_initialisation_sets_rhs(self):
        cl = _make_cl()
        tokens = _make_token(["x", ">", "5"], ["L", "O", "No"])
        cl._initialisation("x > 5", tokens)
        assert cl.get_rhs() is not None

    def test_initialisation_sets_node_name(self):
        cl = _make_cl()
        tokens = _make_token(["x", ">", "5"], ["L", "O", "No"])
        cl._initialisation("x > 5", tokens)
        assert cl.get_node_name() == "x > 5"


class TestCompareDates:
    def test_gt(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">"
        assert cl._compare_dates(datetime(2023, 6, 1), datetime(2023, 1, 1)) is True

    def test_gte(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">="
        assert cl._compare_dates(datetime(2023, 1, 1), datetime(2023, 1, 1)) is True

    def test_lt(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "<"
        assert cl._compare_dates(datetime(2023, 1, 1), datetime(2023, 6, 1)) is True

    def test_lte(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "<="
        assert cl._compare_dates(datetime(2023, 1, 1), datetime(2023, 1, 1)) is True

    def test_eq(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "=="
        assert cl._compare_dates(datetime(2023, 1, 1), datetime(2023, 1, 1)) is True

    def test_eq_false(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "=="
        assert cl._compare_dates(datetime(2023, 1, 1), datetime(2023, 6, 1)) is False

    def test_unknown_operator(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "!="
        assert cl._compare_dates(datetime(2023, 1, 1), datetime(2023, 1, 1)) is False


class TestCompareNumeric:
    def test_gt(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">"
        assert cl._compare_numeric(10, 5) is True
        assert cl._compare_numeric(5, 10) is False

    def test_gte(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">="
        assert cl._compare_numeric(5, 5) is True
        assert cl._compare_numeric(4, 5) is False

    def test_lt(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "<"
        assert cl._compare_numeric(3, 10) is True
        assert cl._compare_numeric(10, 3) is False

    def test_lte(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "<="
        assert cl._compare_numeric(5, 5) is True
        assert cl._compare_numeric(6, 5) is False

    def test_eq(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "=="
        assert cl._compare_numeric(5, 5) is True
        assert cl._compare_numeric(5, 6) is False

    def test_unknown_operator(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "!="
        assert cl._compare_numeric(5, 5) is False


class TestCompareStrings:
    def test_gt(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">"
        assert cl._compare_strings("b", "a") is True

    def test_gte(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">="
        assert cl._compare_strings("a", "a") is True

    def test_lt(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "<"
        assert cl._compare_strings("a", "b") is True

    def test_lte(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "<="
        assert cl._compare_strings("a", "a") is True

    def test_eq(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "=="
        assert cl._compare_strings("hello", "hello") is True

    def test_unknown_operator(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = "!="
        assert cl._compare_strings("a", "a") is False


class TestGetDetectedDate:
    def test_detect_yyyy_mm_dd(self):
        cl = _make_cl()
        assert cl.get_detected_date("2023-06-15") == datetime(2023, 6, 15)

    def test_detect_dd_mm_yyyy(self):
        cl = _make_cl()
        assert cl.get_detected_date("15/06/2023") == datetime(2023, 6, 15)

    def test_detect_mm_dd_yyyy(self):
        cl = _make_cl()
        assert cl.get_detected_date("06/15/2023") == datetime(2023, 6, 15)

    def test_detect_dd_mon_yyyy(self):
        cl = _make_cl()
        assert cl.get_detected_date("15-Jun-2023") == datetime(2023, 6, 15)

    def test_detect_dd_mon_yyyy_space(self):
        cl = _make_cl()
        assert cl.get_detected_date("15 Jun 2023") == datetime(2023, 6, 15)

    def test_detect_yyyy_mm_dd_slash(self):
        cl = _make_cl()
        assert cl.get_detected_date("2023/06/15") == datetime(2023, 6, 15)

    def test_detect_month_dd_yyyy(self):
        cl = _make_cl()
        assert cl.get_detected_date("June 15, 2023") == datetime(2023, 6, 15)

    def test_detect_dd_mm_yyyy_dash(self):
        cl = _make_cl()
        assert cl.get_detected_date("15-06-2023") == datetime(2023, 6, 15)

    def test_detect_yyyy_mm_dd_dot(self):
        cl = _make_cl()
        assert cl.get_detected_date("2023.06.15") == datetime(2023, 6, 15)

    def test_detect_mm_dd_yyyy_dash(self):
        cl = _make_cl()
        assert cl.get_detected_date("06-15-2023") == datetime(2023, 6, 15)

    def test_detect_invalid_returns_none(self):
        cl = _make_cl()
        assert cl.get_detected_date("not a date") is None

    def test_detect_strips_whitespace(self):
        cl = _make_cl()
        assert cl.get_detected_date("  2023-06-15  ") == datetime(2023, 6, 15)


class TestSelfEvaluate:
    def test_numeric_gt(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = ">"
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue(5, FactValueType.INTEGER)
        result = cl.self_evaluate({"x": FactValue(10, FactValueType.INTEGER)})
        assert result.get_value() is True

    def test_numeric_lt(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = "<"
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue(5, FactValueType.INTEGER)
        result = cl.self_evaluate({"x": FactValue(3, FactValueType.INTEGER)})
        assert result.get_value() is True

    def test_numeric_eq(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue(5, FactValueType.INTEGER)
        result = cl.self_evaluate({"x": FactValue(5, FactValueType.INTEGER)})
        assert result.get_value() is True

    def test_numeric_double(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = ">"
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue(3.14, FactValueType.DOUBLE)
        result = cl.self_evaluate({"x": FactValue(5.0, FactValueType.DOUBLE)})
        assert result.get_value() is True

    def test_numeric_decimal(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue(3.14, FactValueType.DECIMAL)
        result = cl.self_evaluate({"x": FactValue(3.14, FactValueType.DECIMAL)})
        assert result.get_value() is True

    def test_date_comparison(self):
        cl = _make_cl()
        cl._variable_name = "start_date"
        cl._ComparisonLine__operator_string = ">"
        cl._ComparisonLine__lhs = "start_date"
        cl._ComparisonLine__rhs = FactValue("01/01/2023", FactValueType.DATE)
        result = cl.self_evaluate({"start_date": FactValue("01/06/2023", FactValueType.DATE)})
        assert result.get_value() is True

    def test_missing_lhs_returns_none(self):
        cl = _make_cl()
        cl._variable_name = "missing_var"
        cl._ComparisonLine__operator_string = ">"
        cl._ComparisonLine__lhs = "missing_var"
        cl._ComparisonLine__rhs = FactValue(5, FactValueType.INTEGER)
        result = cl.self_evaluate({})
        assert result is None

    def test_rhs_in_working_memory(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = ">"
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue("y", FactValueType.STRING)
        result = cl.self_evaluate({"x": FactValue(10, FactValueType.INTEGER), "y": FactValue(5, FactValueType.INTEGER)})
        assert result.get_value() is True

    def test_none_rhs_returns_none(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = ">"
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = None
        result = cl.self_evaluate({"x": FactValue(10, FactValueType.INTEGER)})
        assert result is None

    def test_numeric_gte_false(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = ">="
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue(10, FactValueType.INTEGER)
        result = cl.self_evaluate({"x": FactValue(5, FactValueType.INTEGER)})
        assert result.get_value() is False

    def test_list_comparison_raises_attribute_error(self):
        cl = _make_cl()
        cl._variable_name = "x"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "x"
        cl._ComparisonLine__rhs = FactValue("target", FactValueType.STRING)
        list_val = FactValue(
            [FactValue("target", FactValueType.STRING)],
            FactValueType.LIST
        )
        with pytest.raises(AttributeError, match="NUMBER"):
            cl.self_evaluate({"x": list_val})

    def test_string_comparison_raises_attribute_error(self):
        cl = _make_cl()
        cl._variable_name = "name"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "name"
        cl._ComparisonLine__rhs = FactValue("Alice", FactValueType.STRING)
        with pytest.raises(AttributeError, match="NUMBER"):
            cl.self_evaluate({"name": FactValue("Alice", FactValueType.STRING)})


class TestRepr:
    def test_repr_raises_type_error(self):
        cl = _make_cl()
        cl._ComparisonLine__operator_string = ">"
        with pytest.raises(TypeError, match="not JSON serializable"):
            repr(cl)


class TestSelfEvaluateListComparison:
    def test_list_contains_matching_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        cl = _make_cl()
        cl._variable_name = "items"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "items"
        cl._ComparisonLine__rhs = FactValue("target", FactValueType.STRING)
        list_val = FactValue(
            [FactValue("target", FactValueType.STRING)],
            FactValueType.LIST
        )
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            result = cl.self_evaluate({"items": list_val})
        assert result is not None
        assert result.get_value() is True
        assert result.get_value_type() == FactValueType.BOOLEAN

    def test_list_not_contains_matching_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        cl = _make_cl()
        cl._variable_name = "items"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "items"
        cl._ComparisonLine__rhs = FactValue("missing", FactValueType.STRING)
        list_val = FactValue(
            [FactValue("other", FactValueType.STRING)],
            FactValueType.LIST
        )
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            result = cl.self_evaluate({"items": list_val})
        assert result is not None
        assert result.get_value() is False
        assert result.get_value_type() == FactValueType.BOOLEAN


class TestSelfEvaluateStringComparison:
    def test_string_eq_comparison(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        cl = _make_cl()
        cl._variable_name = "name"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "name"
        cl._ComparisonLine__rhs = FactValue("Alice", FactValueType.DEFI_STRING)
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            result = cl.self_evaluate({"name": FactValue("Alice", FactValueType.STRING)})
        assert result is not None
        assert result.get_value() is True
        assert result.get_value_type() == FactValueType.BOOLEAN

    def test_string_neq_comparison(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        cl = _make_cl()
        cl._variable_name = "name"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "name"
        cl._ComparisonLine__rhs = FactValue("Bob", FactValueType.DEFI_STRING)
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            result = cl.self_evaluate({"name": FactValue("Alice", FactValueType.STRING)})
        assert result is not None
        assert result.get_value() is False
        assert result.get_value_type() == FactValueType.BOOLEAN

    def test_string_comparison_with_non_defi_string_rhs(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        cl = _make_cl()
        cl._variable_name = "name"
        cl._ComparisonLine__operator_string = "=="
        cl._ComparisonLine__lhs = "name"
        cl._ComparisonLine__rhs = FactValue("Alice", FactValueType.STRING)
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            result = cl.self_evaluate({"name": FactValue("Alice", FactValueType.STRING)})
        assert result is not None
        assert result.get_value() is True
        assert result.get_value_type() == FactValueType.BOOLEAN
