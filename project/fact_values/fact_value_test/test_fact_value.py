import pytest
import os

from project.fact_values import FactValue


class FactValueList:

    list_fact_value = []
    fact_value_type_confirm_list = []

    def __init__(self): pass

    @classmethod
    def add_fact_value(cls, fact_value: FactValue, fact_value_type: str):
        cls.list_fact_value.append(fact_value)
        cls.fact_value_type_confirm_list.append(fact_value_type)


@pytest.fixture(scope="function")
def fact_value_list():
    instance = FactValueList()
    yield instance

    with open(os.path.dirname(__file__) + '/fact_value_testing.txt') as f:
        lines = f.readlines()
        for line in lines:
            string_array = line.split('&')
            fv: FactValue = FactValue(string_array[0])
            instance.add_fact_value(fv, string_array[1])
    return instance


def test_init(fact_value_list):
    for fv in fact_value_list.list_fact_value:
        assert fv is not None


def test_get_value(fact_value_list):
    for index in range(len(fact_value_list.list_fact_value)):
        assert fact_value_list.list_fact_value[index].get_value is not None


def test_get_value_type(fact_value_list):
    for index in range(len(fact_value_list.list_fact_value)):
        assert fact_value_list.list_fact_value[index].get_value_type().value \
               == fact_value_list.fact_value_type_confirm_list[index].strip()
