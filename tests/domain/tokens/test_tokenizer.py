import pytest
import re
from unittest.mock import patch

from src.domain.tokens.tokenizer import Tokenizer
from src.domain.tokens.token import Token
from src.shared.constants.tokenizer_matcher_constant import TokenizerMatcherConstant


_VALID_ENUM_NAMES = [
    "SPACE_MATCHER", "RULE_SET_MATCHER", "ITERATE_MATCHER", "CALCULATION_MATCHER",
    "QUOTED_MATCHER", "URL_MATCHER", "GUID_MATCHER", "HASH_MATCHER",
    "DATE_MATCHER", "DECIMAL_NUMBER_MATCHER", "OPERATOR_MATCHER", "NUMBER_MATCHER",
    "PARAGRAPH_MATCHER", "SECTION_MATCHER", "FUNCTION_MATCHER", "UPPER_MATCHER",
    "MIXED_MATCHER", "LOWER_MATCHER",
]

_pattern_cache = {}


def _mock_get_all_matcher():
    return [TokenizerMatcherConstant[name].value for name in _VALID_ENUM_NAMES]


def _mock_get_all_enums():
    return [TokenizerMatcherConstant[name] for name in _VALID_ENUM_NAMES]


def _mock_get_compiled_matcher(name):
    if name not in _VALID_ENUM_NAMES:
        return None
    if name in _pattern_cache:
        return _pattern_cache[name]
    try:
        pattern = re.compile(TokenizerMatcherConstant[name].value)
        _pattern_cache[name] = pattern
        return pattern
    except (re.error, KeyError):
        return None


@pytest.fixture(autouse=True)
def _patch_tokenizer_constants():
    _pattern_cache.clear()
    with patch(
        "src.shared.constants.tokenizer_matcher_constant.TokenizerMatcherConstant.get_all_matcher",
        side_effect=_mock_get_all_matcher,
    ), patch(
        "src.shared.constants.tokenizer_matcher_constant.TokenizerMatcherConstant.get_all_enums",
        side_effect=_mock_get_all_enums,
    ), patch(
        "src.shared.constants.tokenizer_matcher_constant.TokenizerMatcherConstant.get_compiled_matcher",
        side_effect=_mock_get_compiled_matcher,
    ), patch(
        "src.domain.tokens.tokenizer.TokenizerMatcherConstant",
    ) as mock_const:
        mock_const.get_all_matcher = _mock_get_all_matcher
        mock_const.get_all_enums = _mock_get_all_enums
        mock_const.get_compiled_matcher = _mock_get_compiled_matcher
        yield


class TestTokenizerGetTokens:
    def test_get_tokens_empty_string(self):
        result = Tokenizer.get_tokens("")
        assert isinstance(result, Token)
        assert result.get_tokens_list() == []
        assert result.get_tokens_string() == ""

    def test_get_tokens_none(self):
        result = Tokenizer.get_tokens(None)
        assert isinstance(result, Token)
        assert result.get_tokens_list() == []

    def test_get_tokens_whitespace_only(self):
        result = Tokenizer.get_tokens("   ")
        assert isinstance(result, Token)
        assert result.get_tokens_list() == []

    def test_get_tokens_single_word(self):
        result = Tokenizer.get_tokens("hello")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_simple_statement(self):
        result = Tokenizer.get_tokens("status IS active")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0
        assert "status" in result.get_tokens_list()

    def test_get_tokens_value_conclusion(self):
        result = Tokenizer.get_tokens("score IS 10")
        assert isinstance(result, Token)
        assert "score" in result.get_tokens_list()
        assert "IS" in result.get_tokens_list()

    def test_get_tokens_comparison(self):
        result = Tokenizer.get_tokens("age > 18")
        assert isinstance(result, Token)
        assert "age" in result.get_tokens_list()

    def test_get_tokens_with_number(self):
        result = Tokenizer.get_tokens("count IS 5")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_with_decimal(self):
        result = Tokenizer.get_tokens("rate IS 3.14")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_expression_conclusion(self):
        result = Tokenizer.get_tokens("total IS CALC amount + tax")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_iterate(self):
        result = Tokenizer.get_tokens("ITERATE: LIST OF items")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_fixed_metadata(self):
        result = Tokenizer.get_tokens("FIXED rate IS 3.14")
        assert isinstance(result, Token)
        assert "FIXED" in result.get_tokens_list()

    def test_get_tokens_input_metadata(self):
        result = Tokenizer.get_tokens("INPUT age AS NUMBER")
        assert isinstance(result, Token)
        assert "INPUT" in result.get_tokens_list()

    def test_get_tokens_with_boolean(self):
        result = Tokenizer.get_tokens("eligible IS True")
        assert isinstance(result, Token)
        assert "eligible" in result.get_tokens_list()

    def test_get_tokens_with_false(self):
        result = Tokenizer.get_tokens("eligible IS False")
        assert isinstance(result, Token)
        assert "eligible" in result.get_tokens_list()

    def test_get_tokens_date(self):
        result = Tokenizer.get_tokens("01/01/2024")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_url(self):
        result = Tokenizer.get_tokens("http://example.com/path")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_guid(self):
        result = Tokenizer.get_tokens("12345678-1234-1234-1234-123456789012")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_tokens_string_populated(self):
        result = Tokenizer.get_tokens("score IS 10")
        assert isinstance(result, Token)
        assert result.get_tokens_string() != ""

    def test_get_tokens_tokens_string_list_populated(self):
        result = Tokenizer.get_tokens("score IS 10")
        assert isinstance(result, Token)
        assert len(result.get_tokens_string_list()) > 0

    def test_get_tokens_rule_set_prefix(self):
        result = Tokenizer.get_tokens("RULE SET: test module")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_quoted_string(self):
        result = Tokenizer.get_tokens('"quoted value"')
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_section_reference(self):
        result = Tokenizer.get_tokens("Section 1.2.3")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_function_call(self):
        result = Tokenizer.get_tokens("MAX(1, 2, 3)")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_comparison_operator(self):
        result = Tokenizer.get_tokens("age >= 18")
        assert isinstance(result, Token)
        assert "age" in result.get_tokens_list()

    def test_get_tokens_mixed_case(self):
        result = Tokenizer.get_tokens("UpperValue lower_value")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0

    def test_get_tokens_returns_token_instance(self):
        result = Tokenizer.get_tokens("test IS value")
        assert isinstance(result, Token)

    def test_get_tokens_only_spaces(self):
        result = Tokenizer.get_tokens("     ")
        assert isinstance(result, Token)
        assert result.get_tokens_list() == []

    def test_get_tokens_operator_extraction(self):
        result = Tokenizer.get_tokens("x >= 5")
        assert isinstance(result, Token)
        assert len(result.get_tokens_list()) > 0
