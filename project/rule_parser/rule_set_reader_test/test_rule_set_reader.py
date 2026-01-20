import os
import pytest

from rule_parser.rule_set_reader import RuleSetReader


class RuleSetReaderTest:
    file_path = os.path.dirname(__file__) + "/rule_set_reader_testing.txt"
    rule_set_reader = RuleSetReader()

    def __init__(self): pass

    def set_file_with_path(self):
        self.rule_set_reader.set_file_with_path(self.file_path)

    def set_file_with_binary(self):
        with open(self.file_path, 'rb') as file:
            self.rule_set_reader.set_file_with_binary(file.readlines())

    def set_file_with_text(self):
        text = None
        with open(self.file_path, "r") as file:
            text = "".join(file.readlines())
            self.rule_set_reader.set_file_with_text(text)

    def clear_buffered_reader(self):
        self.rule_set_reader = RuleSetReader()

@pytest.fixture(scope="function")
def rule_set_reader_test():
    instance = RuleSetReaderTest()
    yield instance

    return instance


def test_set_file_with_path(rule_set_reader_test):
    rule_set_reader_test.set_file_with_path()

    with open(rule_set_reader_test.file_path) as file:
        for line in file.readlines():
            read_line = rule_set_reader_test.rule_set_reader.get_next_line()
            assert line == read_line


def test_set_file_with_binary(rule_set_reader_test):
    rule_set_reader_test.set_file_with_binary()

    with open(rule_set_reader_test.file_path, "rb") as file:
        for line in file.readlines():
            read_line = rule_set_reader_test.rule_set_reader.get_next_line()
            assert line.decode('utf8') == read_line


def test_set_file_with_text(rule_set_reader_test):
    rule_set_reader_test.set_file_with_text()

    with open(rule_set_reader_test.file_path) as file:
        for line in file.readlines():
            read_line = rule_set_reader_test.rule_set_reader.get_next_line()
            assert line == read_line