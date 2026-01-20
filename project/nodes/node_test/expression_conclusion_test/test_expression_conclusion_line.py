import os

import pytest

from nodes.expression_conclusion_line import ExprConclusionLine
from tokens.tokenizer import Tokenizer


class ExpressionLineList:
    list_expression_line = []
    list_variable = []
    list_equation = []

    def __init__(self): pass

    @classmethod
    def add_values(cls, expression_line: ExprConclusionLine, variable: str, equation: str):
        cls.list_expression_line.append(expression_line)
        cls.list_variable.append(variable)
        cls.list_equation.append(equation)


@pytest.fixture(scope="function")
def expression_line_list():
    instance = ExpressionLineList()
    yield instance

    with open(os.path.dirname(__file__) + '/expression_conclusion_line_testing.txt') as f:
        lines = f.readlines()
        for line in lines:
            text_array = line.split("&")
            expression_line_text = text_array[0].strip()
            token = Tokenizer.get_tokens(expression_line_text)
            expression_line = ExprConclusionLine(expression_line_text, token)
            instance.list_expression_line.append(expression_line)
            instance.list_variable.append(text_array[1].strip())
            instance.list_equation.append(text_array[2].strip())

        return instance


def test_init(expression_line_list):
    for expression_line in expression_line_list.list_expression_line:
        assert expression_line is not None


def test_get_node_id(expression_line_list):
    confirm_to_be = True
    for index in range(len(expression_line_list.list_expression_line)):
        if index != len(expression_line_list.list_expression_line) - 1:
            if not (expression_line_list.list_expression_line[index].get_node_id()
                    <
                    expression_line_list.list_expression_line[index + 1].get_node_id()):
                confirm_to_be = False
    assert confirm_to_be is True


def test_get_node_name(expression_line_list):
    confirm_to_be = True
    for index in range(len(expression_line_list.list_expression_line)):
        expression_line = expression_line_list.list_expression_line[index]
        node_name = expression_line.get_node_name()
        if index == 0 and \
                node_name != "number of drinks the person consumes a week IS CALC ( number of drinks the person consumes an hour * hours of drinks a day * (5-1))":
            confirm_to_be = False
        elif index == 1 and \
                node_name != "yearly period of service by 6/04/1994 IS CALC (6/04/1994 - enlistment date)":
            confirm_to_be = False
        elif index == 2 and \
                node_name != "yearly period of service IS CALC (discharge date - enlistment date)":
            confirm_to_be = False

    assert confirm_to_be is True


def test_get_tokens(expression_line_list):
    confirm_to_be = True
    for expression_line in expression_line_list.list_expression_line:
        token = expression_line.get_tokens()
        tokens_list = token.get_tokens_list()
        tokens_string_list = token.get_tokens_string_list()
        tokens_string = token.get_tokens_string()

        if not (len(tokens_list) > 0 and len(tokens_string_list) > 0 and len(tokens_string) > 0):
            confirm_to_be = False

    assert confirm_to_be is True


def test_get_variable_name(expression_line_list):
    confirm_to_be = True
    for index in range(len(expression_line_list.list_expression_line)):
        expression_line = expression_line_list.list_expression_line[index]
        node_variable_name = expression_line.get_variable_name()
        compared_variable = expression_line_list.list_variable[index]
        if node_variable_name != compared_variable:
            confirm_to_be = False

    assert confirm_to_be is True


def test_get_equation(expression_line_list):
    confirm_to_be = True
    for index in range(len(expression_line_list.list_expression_line)):
        expression_line = expression_line_list.list_expression_line[index]
        node_equation = expression_line.get_equation().get_value()
        compared_equation = expression_line_list.list_equation[index]
        if node_equation != compared_equation:
            confirm_to_be = False

    assert confirm_to_be is True