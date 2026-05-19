import re
from typing import Optional
from src.domain.tokens.token import Token
from src.domain.tokens.tokenizer_matcher_constant import TokenizerMatcherConstant
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)


class Tokenizer:
    _TOKEN_CODES = {
        "RULE_SET_MATCHER": "U",
        "ITERATE_MATCHER": "I",
        "CALCULATION_MATCHER": "C",
        "QUOTED_MATCHER": "Q",
        "URL_MATCHER": "Url",
        "GUID_MATCHER": "Id",
        "HASH_MATCHER": "Ha",
        "DATE_MATCHER": "Da",
        "DECIMAL_NUMBER_MATCHER": "De",
        "OPERATOR_MATCHER": "O",
        "NUMBER_MATCHER": "No",
        "PARAGRAPH_MATCHER": "Pa",
        "SECTION_MATCHER": "Se",
        "FUNCTION_MATCHER": "Fu",
        "UPPER_MATCHER": "U",
        "MIXED_MATCHER": "M",
        "LOWER_MATCHER": "L",
    }

    @staticmethod
    def get_tokens(text: str) -> Token:
        if not text or not text.strip():
            return Token()

        tokens_list: list[str] = []
        tokens_string_list: list[str] = []
        remaining = text

        matchers = TokenizerMatcherConstant.get_all_matcher()
        matcher_names = [e.name for e in TokenizerMatcherConstant.get_all_enums()]

        while remaining:
            matched = False
            for idx, pattern_str in enumerate(matchers):
                if idx >= len(matcher_names):
                    break
                compiled = TokenizerMatcherConstant.get_compiled_matcher(matcher_names[idx])
                if compiled is None:
                    try:
                        compiled = re.compile(pattern_str)
                    except re.error:
                        continue
                match = compiled.match(remaining)
                if match:
                    token_str = match.group(0)
                    if matcher_names[idx] != 'SPACE_MATCHER':
                        tokens_list.append(token_str.strip())
                        tokens_string_list.append(
                            Tokenizer._TOKEN_CODES.get(
                                matcher_names[idx],
                                matcher_names[idx].replace('_MATCHER', '').replace('_NUMBER', '').replace('_', ' '),
                            )
                        )
                    remaining = remaining[len(token_str):]
                    matched = True
                    break

            if not matched:
                if remaining:
                    tokens_list.append(remaining[0])
                    remaining = remaining[1:]
                else:
                    break

        tokens_string = ''.join(tokens_string_list) if tokens_string_list else ''
        return Token(tokens_list, tokens_string_list, tokens_string)
