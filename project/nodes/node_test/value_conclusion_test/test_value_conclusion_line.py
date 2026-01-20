import os
import re

import pytest

from fact_values.fact_value import FactValue
from nodes.line_type import LineType
from nodes.value_conclusion_line import ValueConclusionLine
from tokens.tokenizer import Tokenizer


class ValueConclusionLineList:
    list_value_conclusion_line = []
    is_plain_statement_confirm_list = []
    working_memory = {}

    def __init__(self): pass

    @classmethod
    def add_values(cls, value_conclusion_line: ValueConclusionLine,
                   is_plain_statement: bool):
        cls.list_value_conclusion_line.append(value_conclusion_line)
        cls.is_plain_statement_confirm_list.append(is_plain_statement)


@pytest.fixture(scope="function")
def value_conclusion_line_list():
    instance = ValueConclusionLineList()
    yield instance

    with open(os.path.dirname(__file__) + '/value_conclusion_line_testing.txt') as f:
        lines = f.readlines()
        key = ""
        for line in lines:
            if re.match(r"FIXED", line):
                key = line.split("FIXED")[1].strip()
                instance.working_memory[key] = list()
            elif re.match(r"ITEM", line):
                list(instance.working_memory[key]).append(line.split("ITEM")[1].strip())
            else:
                string_array = line.split('&')
                token = Tokenizer.get_tokens(string_array[0].strip())
                value_conclusion_line = ValueConclusionLine(string_array[0].strip(), token)
                if re.match(r"true", string_array[1].strip(), re.IGNORECASE):
                    is_plain_statement = True
                else:
                    is_plain_statement = False

                instance.add_values(value_conclusion_line, is_plain_statement)

        instance.working_memory["person's name"] = FactValue("Dean Tudir")
        instance.working_memory["person's drinking habit"] = FactValue("heavy drinker")
    return instance


def test_init(value_conclusion_line_list):
    for value_conclusion_line in value_conclusion_line_list.list_value_conclusion_line:
        assert value_conclusion_line is not None


def test_get_is_plain_statement(value_conclusion_line_list):
    line_list: [] = value_conclusion_line_list.list_value_conclusion_line
    length: int = len(line_list)
    for index in range(length):
        valueConclusionNode = value_conclusion_line_list.list_value_conclusion_line[index]
        assert valueConclusionNode.get_is_plain_statement() \
               == value_conclusion_line_list.is_plain_statement_confirm_list[index]


def test_get_line_type(value_conclusion_line_list):
    for value_conclusion_line in value_conclusion_line_list.list_value_conclusion_line:
        assert value_conclusion_line.get_line_type() \
               == LineType.VALUE_CONCLUSION


def test_self_evaluate(value_conclusion_line_list):
    for value_conclusion_line in value_conclusion_line_list.list_value_conclusion_line:
        if value_conclusion_line.get_is_plain_statement() is False:
            if value_conclusion_line.get_variable_name() == "person's name":
                assert value_conclusion_line.self_evaluate() is True
            elif value_conclusion_line.get_variable_name() == "person's drinking habit":
                assert value_conclusion_line.self_evaluate() is False

