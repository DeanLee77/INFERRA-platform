import pytest
from src.domain.nodes.metadata_line import MetadataLine
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.nodes.meta_type import MetaType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.tokens import Token


def _make_token(tokens_list, tokens_string_list):
    return Token(tokens_list=tokens_list, tokens_string_list=tokens_string_list)


def _make_ml():
    ml = MetadataLine(node_text="FIXED x IS 0", tokens=_make_token(["FIXED", "x", "IS", "0"], ["L", "L", "L", "No"]))
    return ml


class TestMetadataLineInit:
    def test_init_sets_line_type(self):
        ml = _make_ml()
        assert ml.get_line_type() == LineType.META


class TestMetadataLineInitialisationFixed:
    def test_fixed_with_is_integer(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "age", "IS", "5"], ["L", "L", "L", "No"])
        ml.initialisation("FIXED age IS 5", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value() == 5
        assert ml.get_fact_value().get_value_type() == FactValueType.INTEGER

    def test_fixed_with_is_double(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "price", "IS", "3.14"], ["L", "L", "L", "De"])
        ml.initialisation("FIXED price IS 3.14", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value() == 3.14
        assert ml.get_fact_value().get_value_type() == FactValueType.DOUBLE

    def test_fixed_with_is_date(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "start", "IS", "01/01/2023"], ["L", "L", "L", "Da"])
        ml.initialisation("FIXED start IS 01/01/2023", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value_type() == FactValueType.DATE

    def test_fixed_with_is_boolean_true(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "flag", "IS", "true"], ["L", "L", "L", "true"])
        ml.initialisation("FIXED flag IS true", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value() is True
        assert ml.get_fact_value().get_value_type() == FactValueType.BOOLEAN

    def test_fixed_with_is_boolean_false(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "flag", "IS", "false"], ["L", "L", "L", "false"])
        ml.initialisation("FIXED flag IS false", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value() is False
        assert ml.get_fact_value().get_value_type() == FactValueType.BOOLEAN

    def test_fixed_with_is_hash(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "data", "IS", "abc123"], ["L", "L", "L", "Ha"])
        ml.initialisation("FIXED data IS abc123", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value_type() == FactValueType.HASH

    def test_fixed_with_is_url(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "link", "IS", "http://example.com"], ["L", "L", "L", "Url"])
        ml.initialisation("FIXED link IS http://example.com", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value_type() == FactValueType.URL

    def test_fixed_with_is_guid(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "uid", "IS", "abc-def"], ["L", "L", "L", "Id"])
        ml.initialisation("FIXED uid IS abc-def", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value_type() == FactValueType.GUID

    def test_fixed_as_list(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "items", "AS", "LIST"], ["L", "L", "L", "L"])
        ml.initialisation("FIXED items AS LIST", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value_type() == FactValueType.LIST
        assert ml.get_fact_value().get_value() == []

    def test_fixed_as_warning(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "items", "AS", "UNKNOWN"], ["L", "L", "L", "L"])
        ml.initialisation("FIXED items AS UNKNOWN", tokens)
        assert ml.get_meta_type() == MetaType.FIXED
        assert ml.get_fact_value().get_value_type() == FactValueType.WARNING


class TestMetadataLineInitialisationInput:
    def test_input_list_no_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "items", "AS", "LIST"], ["L", "L", "L", "L"])
        ml.initialisation("INPUT items AS LIST", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value_type() == FactValueType.LIST

    def test_input_text_no_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "name", "AS", "TEXT"], ["L", "L", "L", "L"])
        ml.initialisation("INPUT name AS TEXT", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value() is None
        assert ml.get_fact_value().get_value_type() == FactValueType.STRING

    def test_input_string_no_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "name", "AS", "STRING"], ["L", "L", "L", "L"])
        ml.initialisation("INPUT name AS STRING", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_url_no_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "link", "AS", "URL"], ["L", "L", "L", "L"])
        ml.initialisation("INPUT link AS URL", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value_type() == FactValueType.URL

    def test_input_guid_no_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "uid", "AS", "GUID"], ["L", "L", "L", "L"])
        ml.initialisation("INPUT uid AS GUID", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value_type() == FactValueType.GUID

    def test_input_date_no_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "dob", "AS", "DATE"], ["L", "L", "L", "L"])
        ml.initialisation("INPUT dob AS DATE", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value_type() == FactValueType.DATE

    def test_input_list_with_value_date(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "dates", "AS", "LIST", "DATE", "01/01/2023"], ["L", "L", "L", "L", "L", "Da"])
        ml.initialisation("INPUT dates AS LIST DATE 01/01/2023", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_double(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "prices", "AS", "LIST", "DOUBLE", "3.14"], ["L", "L", "L", "L", "L", "De"])
        ml.initialisation("INPUT prices AS LIST DOUBLE 3.14", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_integer(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "nums", "AS", "LIST", "INTEGER", "5"], ["L", "L", "L", "L", "L", "No"])
        ml.initialisation("INPUT nums AS LIST INTEGER 5", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_url(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "links", "AS", "LIST", "URL", "http://x"], ["L", "L", "L", "L", "L", "Url"])
        ml.initialisation("INPUT links AS LIST URL http://x", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_guid(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "ids", "AS", "LIST", "GUID", "abc-def"], ["L", "L", "L", "L", "L", "Id"])
        ml.initialisation("INPUT ids AS LIST GUID abc-def", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_boolean_true(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "flags", "AS", "LIST", "BOOLEAN", "true"], ["L", "L", "L", "L", "L", "true"])
        ml.initialisation("INPUT flags AS LIST BOOLEAN true", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_boolean_false(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "flags", "AS", "LIST", "BOOLEAN", "false"], ["L", "L", "L", "L", "L", "false"])
        ml.initialisation("INPUT flags AS LIST BOOLEAN false", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_string_fallback(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "items", "AS", "LIST", "STRING", "hello"], ["L", "L", "L", "L", "L", "L"])
        ml.initialisation("INPUT items AS LIST STRING hello", tokens)
        assert ml.get_meta_type() == MetaType.INPUT

    def test_input_list_with_value_hash_raises_index_error(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "hashes", "AS", "LIST", "HASH", "abc"], ["L", "L", "L", "L", "L", "Ha"])
        with pytest.raises(IndexError):
            ml.initialisation("INPUT hashes AS LIST HASH abc", tokens)

    def test_input_hash_no_value_raises_attribute_error(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "data", "AS", "HASH"], ["L", "L", "L", "L"])
        with pytest.raises(AttributeError, match="NUMBER"):
            ml.initialisation("INPUT data AS HASH", tokens)

    def test_input_double_no_value_raises_attribute_error(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "price", "AS", "DOUBLE"], ["L", "L", "L", "L"])
        with pytest.raises(AttributeError, match="NUMBER"):
            ml.initialisation("INPUT price AS DOUBLE", tokens)

    def test_input_boolean_no_value_raises_attribute_error(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "flag", "AS", "BOOLEAN"], ["L", "L", "L", "L"])
        with pytest.raises(AttributeError, match="NUMBER"):
            ml.initialisation("INPUT flag AS BOOLEAN", tokens)

    def test_input_non_list_with_value_raises_index_error(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "name", "AS", "TEXT", "hello"], ["L", "L", "L", "L", "L"])
        with pytest.raises(IndexError):
            ml.initialisation("INPUT name AS TEXT hello", tokens)


class TestMetadataLineSetMetaType:
    def test_set_meta_type_fixed(self):
        ml = _make_ml()
        ml._set_meta_type("FIXED something")
        assert ml.get_meta_type() == MetaType.FIXED

    def test_set_meta_type_input(self):
        ml = _make_ml()
        ml._set_meta_type("INPUT something")
        assert ml.get_meta_type() == MetaType.INPUT

    def test_set_meta_type_line(self):
        ml = _make_ml()
        ml._set_meta_type("LINE something")
        assert ml.get_meta_type() == MetaType.LINE

    def test_set_meta_type_no_match(self):
        ml = _make_ml()
        ml._set_meta_type("something else")
        assert ml.get_meta_type() is None


class TestMetadataLineGetters:
    def test_get_name(self):
        ml = _make_ml()
        tokens = _make_token(["FIXED", "age", "IS", "5"], ["L", "L", "L", "No"])
        ml.initialisation("FIXED age IS 5", tokens)
        assert ml.get_name() == "FIXED age IS 5"

    def test_get_line_type(self):
        ml = _make_ml()
        assert ml.get_line_type() == LineType.META


class TestMetadataLineSelfEvaluate:
    def test_self_evaluate_returns_none_fact_value(self):
        ml = _make_ml()
        result = ml.self_evaluate({})
        assert result.get_value() is None


class TestMetadataLineInputListWithHashValue:
    def test_input_list_with_hash_token_sets_hash_in_list(self):
        ml = _make_ml()
        ml._set_meta_type("INPUT something")
        tokens = _make_token(["INPUT", "items", "AS", "LIST", "ITEM", "abc"], ["L", "L", "L", "L", "L", "Ha"])
        ml._set_value("LIST ITEM abc", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value_type() == FactValueType.LIST
        assert len(ml.get_fact_value().get_value()) == 1
        assert ml.get_fact_value().get_value()[0].get_value_type() == FactValueType.HASH


class TestMetadataLineInputWithValueViaInitialisation:
    def test_input_string_with_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "name", "AS", "STRING", "IS", "hello"], ["L", "L", "L", "L", "L", "L"])
        ml.initialisation("INPUT name AS STRING IS hello", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value() == "hello"
        assert ml.get_fact_value().get_value_type() == FactValueType.STRING

    def test_input_text_with_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "name", "AS", "TEXT", "IS", "hello"], ["L", "L", "L", "L", "L", "L"])
        ml.initialisation("INPUT name AS TEXT IS hello", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value() == "hello"
        assert ml.get_fact_value().get_value_type() == FactValueType.STRING

    def test_input_date_with_value(self):
        ml = _make_ml()
        tokens = _make_token(["INPUT", "dob", "AS", "DATE", "IS", "01/01/2023"], ["L", "L", "L", "L", "L", "Da"])
        ml.initialisation("INPUT dob AS DATE IS 01/01/2023", tokens)
        assert ml.get_meta_type() == MetaType.INPUT
        assert ml.get_fact_value().get_value_type() == FactValueType.DATE


class TestMetadataLineInputWithValueDirectSet:
    def test_input_integer_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "age", "AS", "INTEGER", "IS", "5"], ["L", "L", "L", "L", "L", "No"])
            ml._set_value("INTEGER IS 5", tokens)
            assert ml.get_fact_value().get_value() == 5
            assert ml.get_fact_value().get_value_type() == FactValueType.INTEGER

    def test_input_double_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "price", "AS", "DOUBLE", "IS", "3.14"], ["L", "L", "L", "L", "L", "De"])
            ml._set_value("DOUBLE IS 3.14", tokens)
            assert ml.get_fact_value().get_value() == 3.14
            assert ml.get_fact_value().get_value_type() == FactValueType.DOUBLE

    def test_input_boolean_true_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "flag", "AS", "BOOLEAN", "IS", "true"], ["L", "L", "L", "L", "L", "true"])
            ml._set_value("BOOLEAN IS true", tokens)
            assert ml.get_fact_value().get_value() is True
            assert ml.get_fact_value().get_value_type() == FactValueType.BOOLEAN

    def test_input_boolean_false_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "flag", "AS", "BOOLEAN", "IS", "false"], ["L", "L", "L", "L", "L", "false"])
            ml._set_value("BOOLEAN IS false", tokens)
            assert ml.get_fact_value().get_value() is False
            assert ml.get_fact_value().get_value_type() == FactValueType.BOOLEAN

    def test_input_url_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "link", "AS", "URL", "IS", "http://x"], ["L", "L", "L", "L", "L", "Url"])
            ml._set_value("URL IS http://x", tokens)
            assert ml.get_fact_value().get_value() == "http://x"
            assert ml.get_fact_value().get_value_type() == FactValueType.URL

    def test_input_hash_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "data", "AS", "HASH", "IS", "abc"], ["L", "L", "L", "L", "L", "Ha"])
            ml._set_value("HASH IS abc", tokens)
            assert ml.get_fact_value().get_value() == "abc"
            assert ml.get_fact_value().get_value_type() == FactValueType.HASH

    def test_input_guid_with_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "uid", "AS", "GUID", "IS", "abc"], ["L", "L", "L", "L", "L", "Id"])
            ml._set_value("GUID IS abc", tokens)
            assert ml.get_fact_value().get_value() == "abc"
            assert ml.get_fact_value().get_value_type() == FactValueType.GUID


class TestMetadataLineInputNoValueDirectSet:
    def test_input_hash_no_value(self):
        ml = _make_ml()
        ml._set_meta_type("INPUT something")
        tokens = _make_token(["INPUT", "data", "AS", "HASH"], ["L", "L", "L", "L"])
        ml._set_value("HASH", tokens)
        assert ml.get_fact_value().get_value() is None
        assert ml.get_fact_value().get_value_type() == FactValueType.HASH

    def test_input_integer_no_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "age", "AS", "INTEGER"], ["L", "L", "L", "L"])
            ml._set_value("INTEGER", tokens)
            assert ml.get_fact_value().get_value() is None
            assert ml.get_fact_value().get_value_type() == FactValueType.INTEGER

    def test_input_double_no_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "price", "AS", "DOUBLE"], ["L", "L", "L", "L"])
            ml._set_value("DOUBLE", tokens)
            assert ml.get_fact_value().get_value() is None
            assert ml.get_fact_value().get_value_type() == FactValueType.DOUBLE

    def test_input_boolean_no_value(self):
        from unittest.mock import patch, MagicMock
        mock_number = MagicMock()
        mock_number.value = "NUMBER"
        with patch.object(FactValueType, "NUMBER", mock_number, create=True):
            ml = _make_ml()
            ml._set_meta_type("INPUT something")
            tokens = _make_token(["INPUT", "flag", "AS", "BOOLEAN"], ["L", "L", "L", "L"])
            ml._set_value("BOOLEAN", tokens)
            assert ml.get_fact_value().get_value() is None
            assert ml.get_fact_value().get_value_type() == FactValueType.BOOLEAN
