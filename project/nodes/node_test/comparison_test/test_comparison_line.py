import os

import pytest

from fact_values.fact_value import FactValue
from fact_values.fact_value_type import FactValueType
from nodes.comparison_line import ComparisonLine
from nodes.line_type import LineType
from tokens.tokenizer import Tokenizer


class ComparisonLineList:
    list_comparison_line = []
    list_lhs = []
    list_operator = []
    list_rhs = []
    working_memory = {}

    def __init__(self): pass

    @classmethod
    def add_values(cls, comparison_line: ComparisonLine, lhs: str, operator: str, rhs: str):
        cls.list_comparison_line.append(comparison_line)
        cls.list_lhs.append(lhs)
        cls.list_operator.append(operator)
        cls.list_rhs.append(rhs)


@pytest.fixture(scope="function")
def comparison_line_list():
    instance = ComparisonLineList()
    yield instance

    with open(os.path.dirname(__file__) + '/comparison_line_testing.txt') as f:
        lines = f.readlines()
        for line in lines:
            text_array = line.split("-")
            comparison_line_text = text_array[0].strip()
            token = Tokenizer.get_tokens(comparison_line_text)
            comparison_line = ComparisonLine(comparison_line_text, token)
            test_line_array = text_array[1].strip().split(":")
            instance.add_values(comparison_line, test_line_array[0].strip(), test_line_array[1].strip(),
                                test_line_array[2].strip())

        instance.working_memory['person passport type'] = FactValue("\"Australian\"")
        instance.working_memory['person passport issued country'] = FactValue("\"Australia\"")
        instance.working_memory['person age'] = FactValue(16, FactValueType.INTEGER)
        instance.working_memory['a number of countries the person has travelled so far'] = \
            FactValue(39, FactValueType.INTEGER)

        return instance


def test_init(comparison_line_list):
    for comparison_line in comparison_line_list.list_comparison_line:
        assert comparison_line is not None


def test_get_node_id(comparison_line_list):
    confirm_to_be = True
    for index in range(len(comparison_line_list.list_comparison_line)):
        if index != len(comparison_line_list.list_comparison_line) - 1:
            if not (comparison_line_list.list_comparison_line[index].get_node_id()
                    <
                    comparison_line_list.list_comparison_line[index + 1].get_node_id()):
                confirm_to_be = False
    assert confirm_to_be is True


def test_get_node_name(comparison_line_list):
    confirm_to_be = True
    for index in range(len(comparison_line_list.list_comparison_line)):
        comparison_line = comparison_line_list.list_comparison_line[index]
        node_name = comparison_line.get_node_name()
        if index == 0 and \
                node_name != "person passport type = \"Australian\"":
            confirm_to_be = False
        elif index == 1 and \
                node_name != "person passport issued country = \"Australia\"":
            confirm_to_be = False
        elif index == 2 and \
                node_name != "person age >18":
            confirm_to_be = False
        elif index == 3 and \
                node_name != "a number of countries the person has travelled so far >= 40":
            confirm_to_be = False
    assert confirm_to_be is True


def test_get_tokens(comparison_line_list):
    confirm_to_be = True
    for comparison_line in comparison_line_list.list_comparison_line:
        token = comparison_line.get_tokens()
        tokens_list = token.get_tokens_list()
        tokens_string_list = token.get_tokens_string_list()
        tokens_string = token.get_tokens_string()

        if not (len(tokens_list) > 0 and len(tokens_string_list) > 0 and len(tokens_string) > 0):
            confirm_to_be = False

    assert confirm_to_be is True


def test_get_variable_name(comparison_line_list):
    confirm_to_be = True
    for index in range(len(comparison_line_list.list_comparison_line)):
        comparison_line = comparison_line_list.list_comparison_line[index]
        node_variable_name = comparison_line.get_variable_name()
        if index == 0 and \
                node_variable_name != "person passport type":
            confirm_to_be = False
        elif index == 1 and \
                node_variable_name != "person passport issued country":
            confirm_to_be = False
        elif index == 2 and \
                node_variable_name != "person age":
            confirm_to_be = False
        elif index == 3 and \
                node_variable_name != "a number of countries the person has travelled so far":
            confirm_to_be = False
    assert confirm_to_be is True


def test_get_lhs(comparison_line_list):
    confirm_to_be = True
    for index in range(len(comparison_line_list.list_comparison_line)):
        comparison_line = comparison_line_list.list_comparison_line[index]
        node_lhs = comparison_line.get_lhs()
        print("node_lhs: " + node_lhs)
        if index == 0 and \
                node_lhs != "person passport type":
            confirm_to_be = False
        elif index == 1 and \
                node_lhs != "person passport issued country":
            confirm_to_be = False
        elif index == 2 and \
                node_lhs != "person age":
            confirm_to_be = False
        elif index == 3 and \
                node_lhs != "a number of countries the person has travelled so far":
            confirm_to_be = False
    assert confirm_to_be is True


def test_get_operator(comparison_line_list):
    confirm_to_be = True
    for index in range(len(comparison_line_list.list_comparison_line)):
        comparison_line = comparison_line_list.list_comparison_line[index]
        operator = comparison_line.get_operator()
        if index == 0 and \
                operator != "==":
            confirm_to_be = False
        elif index == 1 and \
                operator != "==":
            confirm_to_be = False
        elif index == 2 and \
                operator != ">":
            confirm_to_be = False
        elif index == 3 and \
                operator != ">=":
            confirm_to_be = False
    assert confirm_to_be is True


def test_get_rhs(comparison_line_list):
    confirm_to_be = True
    for index in range(len(comparison_line_list.list_comparison_line)):
        comparison_line = comparison_line_list.list_comparison_line[index]
        node_rhs = comparison_line.get_rhs()
        if index == 0 and \
                node_rhs.get_value() != "\"Australian\"":
            confirm_to_be = False
        elif index == 1 and \
                node_rhs.get_value() != "\"Australia\"":
            confirm_to_be = False
        elif index == 2 and \
                node_rhs.get_value() != "18":
            confirm_to_be = False
        elif index == 3 and \
                node_rhs.get_value() != "40":
            confirm_to_be = False
    assert confirm_to_be is True


def test_get_line_type(comparison_line_list):
    for comparison_line in comparison_line_list.list_comparison_line:
        assert comparison_line.get_line_type() is LineType.COMPARISON


def test_self_evaluate(comparison_line_list):
    working_memory = comparison_line_list.working_memory
    for comparison_line in comparison_line_list.list_comparison_line:
        if comparison_line.get_lhs() == "person passport type"\
                or comparison_line.get_lhs() == "person passport issued country":
            assert comparison_line.self_evaluate(working_memory).get_value() is True
        elif comparison_line.get_lhs() == "person age"\
                or comparison_line.get_lhs() == "a number of countries the person has travelled so far":
            assert comparison_line.self_evaluate(working_memory).get_value() is False
