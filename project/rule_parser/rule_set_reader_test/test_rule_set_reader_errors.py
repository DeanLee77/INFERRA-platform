import pytest

from project.rule_parser.rule_set_reader import RuleSetReader


def test_get_next_line_without_loading_file_raises_runtime_error():
    reader = RuleSetReader()
    reader.create()

    with pytest.raises(RuntimeError):
        reader.get_next_line()


def test_set_file_with_text_rejects_none():
    reader = RuleSetReader()
    reader.create()

    with pytest.raises(ValueError):
        reader.set_file_with_text(None)
