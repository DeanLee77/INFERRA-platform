from unittest.mock import MagicMock

from src.domain.fact_values import FactValue
from src.domain.inference.question_strategy import ConservativeQuestionStrategy
from src.domain.nodes.line_type import LineType


def _node(name="n1", variable="v1", line_type=LineType.VALUE_CONCLUSION):
    node = MagicMock()
    node.get_node_name.return_value = name
    node.get_variable_name.return_value = variable
    node.get_line_type.return_value = line_type
    return node


def test_should_ask_value_conclusion_leaf():
    strategy = ConservativeQuestionStrategy()

    assert strategy.should_ask(_node(), {}, has_children=False) is True


def test_should_not_ask_when_known():
    strategy = ConservativeQuestionStrategy()

    assert strategy.should_ask(_node(variable="known"), {"known": FactValue(True)}) is False


def test_select_next_returns_first_askable_candidate():
    strategy = ConservativeQuestionStrategy()
    known = _node(name="known_node", variable="known")
    unknown = _node(name="unknown_node", variable="unknown")

    result = strategy.select_next([known, unknown], {"known": FactValue(True)})

    assert result is unknown
