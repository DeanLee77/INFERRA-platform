import pytest
from unittest.mock import patch, MagicMock
from src.domain.nodes.expression_conclusion_line import ExprConclusionLine
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.tokens import Token


class ConcreteExprConclusionLine(ExprConclusionLine):
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        pass


def _make_token(tokens_list, tokens_string_list):
    return Token(tokens_list=tokens_list, tokens_string_list=tokens_string_list)


def _make_ecl(**kwargs):
    ecl = ConcreteExprConclusionLine(**kwargs)
    ecl._ExprConclusionLine__equation = None
    ecl._ExprConclusionLine__date_formatter = '%Y-%m-%d'
    return ecl


class TestExprConclusionLineInit:
    def test_default_init(self):
        ecl = _make_ecl()
        assert ecl.get_equation() is None
        assert ecl.get_line_type() == LineType.EXPR_CONCLUSION

    def test_init_with_id(self):
        ecl = _make_ecl(id=10)
        assert ecl.get_node_id() == 10


class TestExprConclusionLineGettersSetters:
    def test_set_and_get_equation(self):
        ecl = _make_ecl()
        fv = FactValue("a + b", FactValueType.STRING)
        ecl.set_equation(fv)
        assert ecl.get_equation() == fv

    def test_get_line_type(self):
        ecl = _make_ecl()
        assert ecl.get_line_type() == LineType.EXPR_CONCLUSION


class TestExprConclusionLineInitialisation:
    def test_initialisation_sets_variable_name(self):
        ecl = _make_ecl()
        tokens = _make_token(["x", "IS CALC y + z"], ["L", "C"])
        ecl._initialisation("x IS CALC y + z", tokens)
        assert ecl.get_variable_name() == "x"

    def test_initialisation_sets_equation(self):
        ecl = _make_ecl()
        tokens = _make_token(["x", "IS CALC y + z"], ["L", "C"])
        ecl._initialisation("x IS CALC y + z", tokens)
        assert ecl.get_equation() is not None

    def test_initialisation_sets_node_name(self):
        ecl = _make_ecl()
        tokens = _make_token(["x", "IS CALC y + z"], ["L", "C"])
        ecl._initialisation("x IS CALC y + z", tokens)
        assert ecl.get_node_name() == "x IS CALC y + z"


class TestExprConclusionLineSelfEvaluate:
    def test_self_evaluate_none_equation(self):
        ecl = _make_ecl()
        result = ecl.self_evaluate({})
        assert result.get_value() is None
        assert result.get_value_type() == FactValueType.UNKNOWN

    def test_self_evaluate_simple_addition(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x + y", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "x": FactValue(3, FactValueType.INTEGER),
            "y": FactValue(4, FactValueType.INTEGER),
        }
        mock_token = MagicMock()
        mock_token.get_tokens_string.return_value = "No"
        with patch('src.domain.nodes.expression_conclusion_line.Tokenizer.get_tokens', return_value=mock_token):
            result = ecl.self_evaluate(working_memory)
        assert result is not None
        assert float(result.get_value()) == 7.0

    def test_self_evaluate_multiplication(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("a * b", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "a": FactValue(5, FactValueType.INTEGER),
            "b": FactValue(6, FactValueType.INTEGER),
        }
        mock_token = MagicMock()
        mock_token.get_tokens_string.return_value = "No"
        with patch('src.domain.nodes.expression_conclusion_line.Tokenizer.get_tokens', return_value=mock_token):
            result = ecl.self_evaluate(working_memory)
        assert result is not None
        assert float(result.get_value()) == 30.0

    def test_self_evaluate_double_result(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("a / b", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "a": FactValue(10, FactValueType.INTEGER),
            "b": FactValue(3, FactValueType.INTEGER),
        }
        mock_token = MagicMock()
        mock_token.get_tokens_string.return_value = "De"
        with patch('src.domain.nodes.expression_conclusion_line.Tokenizer.get_tokens', return_value=mock_token):
            result = ecl.self_evaluate(working_memory)
        assert result is not None
        assert result.get_value_type() == FactValueType.DOUBLE

    def test_self_evaluate_boolean_expression_raises_error(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x > 0", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "x": FactValue(5, FactValueType.INTEGER),
        }
        with pytest.raises(ValueError, match="Evaluation failed"):
            ecl.self_evaluate(working_memory)

    def test_self_evaluate_ternary_true_branch(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("(distance > threshold ? 100 : 50)", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "distance": FactValue(60, FactValueType.INTEGER),
            "threshold": FactValue(50, FactValueType.INTEGER),
        }
        result = ecl.self_evaluate(working_memory)
        assert float(result.get_value()) == 100.0

    def test_self_evaluate_ternary_false_branch(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("(distance > threshold ? 100 : 50)", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "distance": FactValue(40, FactValueType.INTEGER),
            "threshold": FactValue(50, FactValueType.INTEGER),
        }
        result = ecl.self_evaluate(working_memory)
        assert float(result.get_value()) == 50.0

    def test_self_evaluate_ternary_string_equality_condition(self):
        ecl = _make_ecl()
        ecl.set_equation(
            FactValue(
                '(decoration type = "Victoria Cross" ? victoria cross allowance rate : decoration allowance rate)',
                FactValueType.STRING,
            )
        )
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "decoration type": FactValue("Victoria Cross", FactValueType.STRING),
            "victoria cross allowance rate": FactValue(100, FactValueType.INTEGER),
            "decoration allowance rate": FactValue(50, FactValueType.INTEGER),
        }
        result = ecl.self_evaluate(working_memory)
        assert float(result.get_value()) == 100.0

    def test_self_evaluate_round_max_min_functions(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("MAX(base amount, minimum amount) + MIN(ROUND(rate * days), cap)", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "base amount": FactValue(10, FactValueType.INTEGER),
            "minimum amount": FactValue(20, FactValueType.INTEGER),
            "rate": FactValue(2.4, FactValueType.DOUBLE),
            "days": FactValue(2, FactValueType.INTEGER),
            "cap": FactValue(5, FactValueType.INTEGER),
        }
        result = ecl.self_evaluate(working_memory)
        assert float(result.get_value()) == 25.0

    def test_self_evaluate_with_list_value(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        list_fv = FactValue(
            [FactValue(1, FactValueType.INTEGER), FactValue(2, FactValueType.INTEGER)],
            FactValueType.LIST
        )
        working_memory = {"x": list_fv}
        mock_token = MagicMock()
        mock_token.get_tokens_string.return_value = "L"
        with patch('src.domain.nodes.expression_conclusion_line.Tokenizer.get_tokens', return_value=mock_token):
            result = ecl.self_evaluate(working_memory)
        assert result is not None

    def test_compatibility_helpers_preserve_bounded_values(self):
        ecl = _make_ecl()

        assert ecl._expression_value([(1, None)]) == [(1, 0)]
        assert ecl._evaluate_expression("1 + 1") == 2

        boolean_result = ecl._fact_value_from_outcome(True)
        string_result = ecl._fact_value_from_outcome("approved")
        assert boolean_result.get_value_type() == FactValueType.BOOLEAN
        assert string_result.get_value_type() == FactValueType.STRING

    def test_self_evaluate_with_none_value_substitutes_empty(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x + 1", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {"x": FactValue(None, FactValueType.UNKNOWN)}
        mock_token = MagicMock()
        mock_token.get_tokens_string.return_value = "No"
        with patch('src.domain.nodes.expression_conclusion_line.Tokenizer.get_tokens', return_value=mock_token):
            result = ecl.self_evaluate(working_memory)
        assert result is not None

    def test_self_evaluate_fallback_path(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x + ( y", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "x": FactValue(3, FactValueType.INTEGER),
            "y": FactValue(4, FactValueType.INTEGER),
        }
        with pytest.raises(ValueError, match="Evaluation failed"):
            ecl.self_evaluate(working_memory)

    def test_self_evaluate_rejects_python_call_without_side_effect(self, tmp_path):
        target = tmp_path / "must-not-exist"
        ecl = _make_ecl()
        ecl.set_equation(
            FactValue(
                f"open('{target.as_posix()}', 'w')",
                FactValueType.STRING,
            )
        )
        ecl._variable_name = "result"
        ecl._node_name = "test_node"

        with pytest.raises(ValueError, match="Unsupported function"):
            ecl.self_evaluate({})

        assert not target.exists()

    def test_self_evaluate_rejects_unsupported_operator(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("amount % divisor", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"

        with pytest.raises(ValueError, match="Unsupported identifier"):
            ecl.self_evaluate(
                {
                    "amount": FactValue(5, FactValueType.INTEGER),
                    "divisor": FactValue(2, FactValueType.INTEGER),
                }
            )

    def test_self_evaluate_date_result(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x + y", FactValueType.STRING))
        ecl._variable_name = "result"
        ecl._node_name = "test_node"
        working_memory = {
            "x": FactValue(3, FactValueType.INTEGER),
            "y": FactValue(4, FactValueType.INTEGER),
        }
        mock_token = MagicMock()
        mock_token.get_tokens_string.return_value = "Da"
        with patch('src.domain.nodes.expression_conclusion_line.Tokenizer.get_tokens', return_value=mock_token):
            result = ecl.self_evaluate(working_memory)
        assert result is not None
        assert result.get_value_type() == FactValueType.DATE


class TestExprConclusionLineRepr:
    def test_repr_raises_type_error(self):
        ecl = _make_ecl()
        ecl.set_equation(FactValue("x + y", FactValueType.STRING))
        with pytest.raises(TypeError, match="not JSON serializable"):
            repr(ecl)
