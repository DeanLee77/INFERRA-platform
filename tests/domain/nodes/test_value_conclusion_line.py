import pytest
from unittest.mock import patch
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.tokens import Token
from src.domain.nodes.meta_data import MetaData


def _make_token(tokens_list, tokens_string_list):
    return Token(tokens_list=tokens_list, tokens_string_list=tokens_string_list)


def _make_vcl(**kwargs):
    vcl = ValueConclusionLine(**kwargs)
    vcl._ValueConclusionLine__is_plain_statement_format = False
    return vcl


class TestValueConclusionLineInit:
    def test_default_init(self):
        vcl = ValueConclusionLine()
        assert vcl.get_is_plain_statement() is False
        assert vcl.get_line_type() == LineType.VALUE_CONCLUSION

    def test_init_with_id(self):
        vcl = ValueConclusionLine(id=7)
        assert vcl.get_node_id() == 7

    def test_init_with_meta_data(self):
        md = MetaData(reference="ref1")
        vcl = ValueConclusionLine(meta_data=md)
        assert vcl.get_meta_data() is md


class TestValueConclusionLineSelfEvaluate:
    def test_self_evaluate_is_format_returns_value(self):
        vcl = _make_vcl()
        vcl._variable_name = "score"
        vcl._value = FactValue(5, FactValueType.INTEGER)
        vcl._tokens = _make_token(["score", "IS", "5"], ["L", "L", "No"])
        result = vcl.self_evaluate({})
        assert result is not None
        assert result.get_value() == 5

    def test_self_evaluate_plain_statement_returns_none(self):
        vcl = _make_vcl()
        vcl._ValueConclusionLine__is_plain_statement_format = True
        result = vcl.self_evaluate({})
        assert result is None

    def test_self_evaluate_is_in_list_not_in_working_memory(self):
        vcl = _make_vcl()
        vcl._variable_name = "item"
        vcl._value = FactValue("my_list", FactValueType.STRING)
        vcl._tokens = _make_token(["item", "IS IN LIST", "my_list"], ["L", "L", "L"])
        result = vcl.self_evaluate({})
        assert result is not None
        assert result.get_value() is False

    def test_self_evaluate_is_in_list_variable_in_working_memory(self):
        vcl = _make_vcl()
        vcl._variable_name = "item"
        vcl._value = FactValue("my_list", FactValueType.STRING)
        vcl._tokens = _make_token(["item", "IS IN LIST", "my_list"], ["L", "L", "L"])
        list_fv = FactValue(
            [FactValue("item_val", FactValueType.STRING)],
            FactValueType.LIST
        )
        working_memory = {
            "my_list": list_fv,
            "item": FactValue("item_val", FactValueType.STRING),
        }
        result = vcl.self_evaluate(working_memory)
        assert result is not None
        assert result.get_value() is True

    def test_self_evaluate_is_in_list_variable_not_in_memory_uses_name(self):
        vcl = _make_vcl()
        vcl._variable_name = "item_val"
        vcl._value = FactValue("my_list", FactValueType.STRING)
        vcl._tokens = _make_token(["item_val", "IS IN LIST", "my_list"], ["L", "L", "L"])
        list_fv = FactValue(
            [FactValue("item_val", FactValueType.STRING)],
            FactValueType.LIST
        )
        working_memory = {"my_list": list_fv}
        result = vcl.self_evaluate(working_memory)
        assert result is not None
        assert result.get_value() is True

    def test_self_evaluate_is_in_list_not_found(self):
        vcl = _make_vcl()
        vcl._variable_name = "item"
        vcl._value = FactValue("my_list", FactValueType.STRING)
        vcl._tokens = _make_token(["item", "IS IN LIST", "my_list"], ["L", "L", "L"])
        list_fv = FactValue(
            [FactValue("other_val", FactValueType.STRING)],
            FactValueType.LIST
        )
        working_memory = {
            "my_list": list_fv,
            "item": FactValue("item_val", FactValueType.STRING),
        }
        result = vcl.self_evaluate(working_memory)
        assert result is not None
        assert result.get_value() is False

    def test_self_evaluate_is_in_list_no_variable_in_memory(self):
        vcl = _make_vcl()
        vcl._variable_name = "item"
        vcl._value = FactValue("my_list", FactValueType.STRING)
        vcl._tokens = _make_token(["item", "IS IN LIST", "my_list"], ["L", "L", "L"])
        list_fv = FactValue(
            [FactValue("item", FactValueType.STRING)],
            FactValueType.LIST
        )
        working_memory = {"my_list": list_fv}
        result = vcl.self_evaluate(working_memory)
        assert result is not None
        assert result.get_value() is True


class TestValueConclusionLineGetLineType:
    def test_get_line_type(self):
        vcl = ValueConclusionLine()
        assert vcl.get_line_type() == LineType.VALUE_CONCLUSION


class TestValueConclusionLineRepr:
    def test_repr_raises_type_error(self):
        vcl = ValueConclusionLine(id=1)
        with pytest.raises(TypeError, match="not JSON serializable"):
            repr(vcl)


class TestValueConclusionLineInitialisation:
    def test_initialisation_plain_statement(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["plain_statement"], ["L"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("plain_statement", tokens)
        assert vcl.get_is_plain_statement() is True
        assert vcl.get_variable_name() == "plain_statement"

    def test_initialisation_is_format(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["score", "IS", "5"], ["L", "L", "No"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("score IS 5", tokens)
        assert vcl.get_is_plain_statement() is False
        assert vcl.get_variable_name() == "score"

    def test_initialisation_is_double(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["price", "IS", "3.14"], ["L", "L", "De"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("price IS 3.14", tokens)
        assert vcl.get_variable_name() == "price"

    def test_initialisation_is_boolean_true(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["flag", "IS", "true"], ["L", "L", "true"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("flag IS true", tokens)
        assert vcl.get_variable_name() == "flag"

    def test_initialisation_is_boolean_false(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["flag", "IS", "false"], ["L", "L", "false"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("flag IS false", tokens)
        assert vcl.get_variable_name() == "flag"

    def test_initialisation_is_string(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["name", "IS", "hello"], ["L", "L", "L"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("name IS hello", tokens)
        assert vcl.get_variable_name() == "name"

    def test_initialisation_is_date(self):
        vcl = ValueConclusionLine()
        tokens = _make_token(["dob", "IS", "01/01/2023"], ["L", "L", "Da"])
        with patch.object(ValueConclusionLine, '_set_value', create=True):
            vcl.initialisation("dob IS 01/01/2023", tokens)
        assert vcl.get_variable_name() == "dob"
