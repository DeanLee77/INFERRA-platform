import pytest

from nodes import value_conclusion_line


class TopoSortTest:
    list_rule_line = []
    list_sorted_rule_line = []

    def __init__(self): pass

    @classmethod
    def add_values(cls, rule_line: str,
                   is_plain_statement: bool):
        cls.list_value_conclusion_line.append(value_conclusion_line)
        cls.is_plain_statement_confirm_list.append(is_plain_statement)

@pytest.fixture(scope="function")
def my_assessment_state():
    instance = []

    first = "person qualifies for the grant"
    second = "person's name = \"troy jones\""
    third = "person's dob > 01/01/1990"
    my_list = [first, second, third]
    instance.append(my_list)

    fact_dict: dict = {}
    for item in my_list:
        fact_dict[item] = True

    instance.append(fact_dict)
    return instance
