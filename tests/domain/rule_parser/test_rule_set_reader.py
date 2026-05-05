import pytest
from unittest.mock import MagicMock, patch

from src.domain.rule_parser.rule_set_reader import RuleSetReader


class TestRuleSetReaderInit:
    def test_init_sets_buffered_reader_to_none(self):
        reader = RuleSetReader()
        assert reader._RuleSetReader__buffered_reader is None


class TestRuleSetReaderCreate:
    def test_create_resets_buffered_reader(self):
        reader = RuleSetReader()
        reader._RuleSetReader__buffered_reader = MagicMock()
        reader.create()
        assert reader._RuleSetReader__buffered_reader is None

    def test_create_when_already_none(self):
        reader = RuleSetReader()
        reader.create()
        assert reader._RuleSetReader__buffered_reader is None


class TestRuleSetReaderSetFileWithPath:
    def test_set_file_with_path_success(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        reader = RuleSetReader()
        reader.set_file_with_path(str(test_file))
        assert reader._RuleSetReader__buffered_reader is not None
        reader._RuleSetReader__buffered_reader.close()

    def test_set_file_with_path_file_not_found(self):
        reader = RuleSetReader()
        with pytest.raises(FileNotFoundError, match="Sorry, the file does not exist"):
            reader.set_file_with_path("/nonexistent/path/file.txt")

    def test_set_file_with_path_opens_binary_mode(self, tmp_path):
        test_file = tmp_path / "binary_test.txt"
        test_file.write_bytes(b"binary data")
        reader = RuleSetReader()
        reader.set_file_with_path(str(test_file))
        assert reader._RuleSetReader__buffered_reader is not None
        reader._RuleSetReader__buffered_reader.close()


class TestRuleSetReaderSetFileWithBinary:
    def test_set_file_with_binary_bytes(self):
        reader = RuleSetReader()
        reader.set_file_with_binary(b"line1\nline2\n")
        assert reader._RuleSetReader__buffered_reader is not None

    def test_set_file_with_binary_list_of_bytes(self):
        reader = RuleSetReader()
        reader.set_file_with_binary([b"line1\n", b"line2\n"])
        assert reader._RuleSetReader__buffered_reader is not None

    def test_set_file_with_binary_none_raises_value_error(self):
        reader = RuleSetReader()
        with pytest.raises(ValueError, match="file_binary cannot be None"):
            reader.set_file_with_binary(None)

    def test_set_file_with_binary_invalid_type(self):
        reader = RuleSetReader()
        with pytest.raises(ValueError, match="binary file does not exist"):
            reader.set_file_with_binary(12345)


class TestRuleSetReaderSetFileWithText:
    def test_set_file_with_text_success(self):
        reader = RuleSetReader()
        reader.set_file_with_text("line1\nline2\n")
        assert reader._RuleSetReader__buffered_reader is not None

    def test_set_file_with_text_none_raises_value_error(self):
        reader = RuleSetReader()
        with pytest.raises(ValueError, match="text cannot be None"):
            reader.set_file_with_text(None)

    def test_set_file_with_text_empty_string(self):
        reader = RuleSetReader()
        reader.set_file_with_text("")
        assert reader._RuleSetReader__buffered_reader is not None

    def test_set_file_with_text_unicode(self):
        reader = RuleSetReader()
        reader.set_file_with_text("Unicode content")
        assert reader._RuleSetReader__buffered_reader is not None


class TestRuleSetReaderGetNextLine:
    def test_get_next_line_from_text(self):
        reader = RuleSetReader()
        reader.set_file_with_text("first line\nsecond line\n")
        line1 = reader.get_next_line()
        assert "first line" in line1
        line2 = reader.get_next_line()
        assert "second line" in line2

    def test_get_next_line_returns_empty_at_end(self):
        reader = RuleSetReader()
        reader.set_file_with_text("only one line\n")
        reader.get_next_line()
        line = reader.get_next_line()
        assert line == ""

    def test_get_next_line_no_file_loaded_raises_runtime_error(self):
        reader = RuleSetReader()
        with pytest.raises(RuntimeError, match="No file has been loaded"):
            reader.get_next_line()

    def test_get_next_line_from_binary(self):
        reader = RuleSetReader()
        reader.set_file_with_binary(b"binary line 1\nbinary line 2\n")
        line1 = reader.get_next_line()
        assert "binary line 1" in line1

    def test_get_next_line_closes_reader_at_eof(self):
        reader = RuleSetReader()
        reader.set_file_with_text("single line\n")
        reader.get_next_line()
        reader.get_next_line()
        assert reader._RuleSetReader__buffered_reader is None or reader._RuleSetReader__buffered_reader.closed


class TestRuleSetReaderIsReaderOpen:
    def test_is_reader_open_false_initially(self):
        reader = RuleSetReader()
        assert reader._is_reader_open() is False

    def test_is_reader_open_true_after_setting_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        reader = RuleSetReader()
        reader.set_file_with_path(str(test_file))
        assert reader._is_reader_open() is True
        reader._RuleSetReader__buffered_reader.close()

    def test_is_reader_open_false_after_close(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        reader = RuleSetReader()
        reader.set_file_with_path(str(test_file))
        reader._RuleSetReader__buffered_reader.close()
        assert reader._is_reader_open() is False


class TestRuleSetReaderCloseReader:
    def test_close_reader_when_open(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        reader = RuleSetReader()
        reader.set_file_with_path(str(test_file))
        reader._close_reader()
        assert reader._RuleSetReader__buffered_reader is None

    def test_close_reader_when_none(self):
        reader = RuleSetReader()
        reader._close_reader()
        assert reader._RuleSetReader__buffered_reader is None


class TestRuleSetReaderSetFileWithTextError:
    def test_set_file_with_text_oserror_handling(self):
        reader = RuleSetReader()
        with patch("io.BytesIO", side_effect=OSError("read error")):
            with pytest.raises(ValueError, match="no Input string"):
                reader.set_file_with_text("some text")

    def test_set_file_with_text_type_error_handling(self):
        reader = RuleSetReader()
        with patch("io.BytesIO", side_effect=TypeError("type error")):
            with pytest.raises(ValueError, match="no Input string"):
                reader.set_file_with_text("some text")


class TestRuleSetReaderGetNextLineOSError:
    def test_get_next_line_readline_oserror(self):
        reader = RuleSetReader()
        reader.set_file_with_binary(b"line1\n")
        with patch.object(reader._RuleSetReader__buffered_reader, "readline", side_effect=OSError("read error")):
            with pytest.raises(RuntimeError, match="No lines to read"):
                reader.get_next_line()


class TestRuleSetReaderGetNextLineCloseOSError:
    def test_get_next_line_close_oserror(self):
        reader = RuleSetReader()
        reader.set_file_with_text("single line\n")
        reader.get_next_line()
        with patch.object(reader._RuleSetReader__buffered_reader, "close", side_effect=OSError("close error")):
            with pytest.raises(RuntimeError, match="No buffered reader to close"):
                reader.get_next_line()


class TestRuleSetReaderCloseReaderOSError:
    def test_close_reader_handles_oserror(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        reader = RuleSetReader()
        reader.set_file_with_path(str(test_file))
        with patch.object(reader._RuleSetReader__buffered_reader, "close", side_effect=OSError("close error")):
            reader._close_reader()
        assert reader._RuleSetReader__buffered_reader is None
