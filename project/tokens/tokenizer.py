"""
Tokenizer Module.
Tokenizes input text using regex patterns defined in TokenizerMatcherConstant.
Implements access levels and strong typing where appropriate.
"""

import re
from typing import List, Optional, Tuple
from project.constants import TokenizerMatcherConstant
from project.tokens.token import Token
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class Tokenizer:
    """
    Tokenizer breaks input text into tokens using regex patterns.
    Pattern order is critical - some patterns must come before others.
    
    Access Levels:
    - Public: Static API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Class constants (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Class Constants (Name Mangling)
    # -------------------------------------------------------------------------
    # Pattern order is extremely important - some patterns won't work if others
    # are invoked earlier (especially 'I' pattern must come before 'U' pattern)
    __MATCH_PATTERNS: Tuple[str, ...] = tuple(TokenizerMatcherConstant.get_all_matcher())
    __TOKEN_TYPES: Tuple[str, ...] = (
        'S',   # Space
        'R',   # Rule Set
        'I',   # Iterate
        'C',   # Calculation
        'Q',   # Quoted
        'Url', # URL
        'Id',  # GUID
        'Ha',  # Hash
        'Da',  # Date
        'De',  # Decimal
        'O',   # Operator
        'No',  # Number
        'Pa',  # Paragraph
        'Se',  # Section
        'Fu',  # Function
        'U',   # Upper
        'M',   # Mixed
        'L',   # Lower
    )

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods
    # -------------------------------------------------------------------------
    @classmethod
    def get_tokens(cls, text: str) -> Token:
        """
        Public API: Tokenizes input text into Token object.
        
        Args:
            text: Input text to tokenize
            
        Returns:
            Token object containing tokenized information
            
        Raises:
            ValueError: If text is None
        """
        if text is None:
            raise ValueError("Tokenizer input text cannot be None")

        token_string_list: List[str] = []
        token_list: List[str] = []
        token_string: str = ''
        original_text: str = text
        remaining_text: str = text
        
        while len(remaining_text) > 0:
            matched = False
            
            for i, pattern in enumerate(cls.__MATCH_PATTERNS):
                try:
                    match = re.match(pattern, remaining_text)
                    if match:
                        group = match.group(0)
                        token_type = cls.__TOKEN_TYPES[i]
                        
                        # Skip space tokens (don't add to output)
                        if token_type != 'S':
                            token_string_list.append(token_type)
                            token_list.append(group.strip())
                            token_string += token_type
                        
                        # Move past matched text
                        remaining_text = remaining_text[len(group):].lstrip()
                        matched = True
                        break
                        
                except re.error as e:
                    _logger.exception("Regex error in pattern %s: %s", cls.__TOKEN_TYPES[i], e)
                    continue

            if not matched:
                _logger.warning(
                    "No token match found for remaining text '%s' from original input '%s'",
                    remaining_text,
                    original_text
                )
                token_string = 'WARNING'
                break

        return Token(token_list, token_string_list, token_string)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    @classmethod
    def _get_pattern_count(cls) -> int:
        """
        Protected Helper: Returns number of regex patterns.
        
        Returns:
            Number of patterns in match list
        """
        return len(cls.__MATCH_PATTERNS)

    @classmethod
    def _get_token_type(cls, index: int) -> Optional[str]:
        """
        Protected Helper: Returns token type at given index.
        
        Args:
            index: Pattern index
            
        Returns:
            Token type code or None if index out of range
        """
        if 0 <= index < len(cls.__TOKEN_TYPES):
            return cls.__TOKEN_TYPES[index]
        return None

    @classmethod
    def _validate_pattern_order(cls) -> bool:
        """
        Protected Helper: Validates critical pattern ordering.
        
        Returns:
            True if critical patterns are in correct order
        """
        # 'I' (Iterate) must come before 'U' (Upper)
        # 'Url' must come before 'L' (Lower)
        try:
            i_index = cls.__TOKEN_TYPES.index('I')
            u_index = cls.__TOKEN_TYPES.index('U')
            url_index = cls.__TOKEN_TYPES.index('Url')
            l_index = cls.__TOKEN_TYPES.index('L')
            
            return i_index < u_index and url_index < l_index
        except ValueError:
            _logger.error("Critical token type not found in pattern order")
            return False

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods (Utilities)
    # -------------------------------------------------------------------------
    @classmethod
    def tokenize_to_list(cls, text: str) -> List[str]:
        """
        Public API: Tokenizes text and returns list of token strings.
        
        Args:
            text: Input text to tokenize
            
        Returns:
            List of token strings
        """
        token = cls.get_tokens(text)
        return token.get_tokens_list()

    @classmethod
    def tokenize_to_string(cls, text: str) -> str:
        """
        Public API: Tokenizes text and returns token type string.
        
        Args:
            text: Input text to tokenize
            
        Returns:
            Token type string (e.g., 'UML')
        """
        token = cls.get_tokens(text)
        return token.get_tokens_string()

    @classmethod
    def is_plain_statement(cls, text: str) -> bool:
        """
        Public API: Checks if text is a plain statement (no 'IS' keyword).
        
        Args:
            text: Text to check
            
        Returns:
            True if plain statement format
        """
        token = cls.get_tokens(text)
        return 'IS' not in token.get_tokens_list()