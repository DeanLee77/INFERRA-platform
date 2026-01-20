import logging
import os

import pytest

from fact_values.fact_value_type import FactValueType
from loggers.logger import Logger
from nodes.line_type import LineType
from nodes.meta_type import MetaType
from nodes.metadata_line import MetadataLine
from tokens.tokenizer import Tokenizer


class MetadataLineList:
    list_metadata_line = []
    metadata_line_type_confirm_list = []
    metadata_line_fact_value_confirm_list = []

    def __init__(self): pass

    @classmethod
    def add_values(cls, metadata_line: MetadataLine, metadata_line_type: str,
                   fact_value_type: str):
        cls.list_metadata_line.append(metadata_line)
        cls.metadata_line_type_confirm_list.append(metadata_line_type)
        cls.metadata_line_fact_value_confirm_list.append(fact_value_type)


@pytest.fixture(scope="function")
def metadata_line_list():
    instance = MetadataLineList()
    yield instance

    with open(os.path.dirname(__file__) + '/metadata_line_testing.txt') as f:
        lines = f.readlines()
        for line in lines:
            string_array = line.split(':')
            token = Tokenizer.get_tokens(string_array[0].strip())
            meta_data = MetadataLine(line, token)
            meta_type = string_array[1].strip()
            fact_value_type = string_array[2].strip()
            instance.add_values(meta_data, meta_type, fact_value_type)
    return instance


def test_init(metadata_line_list):
    for meta in metadata_line_list.list_metadata_line:
        assert meta is not None


def test_get_node_id(metadata_line_list):
    id_incremented = True
    for index in range(len(metadata_line_list.list_metadata_line) - 1):
        if not (metadata_line_list.list_metadata_line[index].get_node_id() < metadata_line_list.list_metadata_line[index + 1].get_node_id()):
            id_incremented = False
    assert id_incremented is True


def test_get_meta_type(metadata_line_list):
    for index in range(len(metadata_line_list.list_metadata_line)):
        assert metadata_line_list.list_metadata_line[index].get_meta_type().value \
               == metadata_line_list.metadata_line_type_confirm_list[index]


def test_get_name(metadata_line_list):
    for meta in metadata_line_list.list_metadata_line:
        assert meta.get_name() is not None


def test_get_line_type(metadata_line_list):
    for index in range(len(metadata_line_list.list_metadata_line)):
        assert metadata_line_list.list_metadata_line[index].get_line_type().value \
               == LineType.META.value


def test_get_tokens(metadata_line_list):
    for meta in metadata_line_list.list_metadata_line:
        assert meta.get_tokens() is not None


def test_get_variable_name(metadata_line_list):
    for meta in metadata_line_list.list_metadata_line:
        assert meta.get_variable_name() is not None
