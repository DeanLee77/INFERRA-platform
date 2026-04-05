"""
Token Module.
Represents a tokenized unit of text in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import List, Optional
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class Token:
    """
    Token represents a tokenized unit with original text and type information.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        tokens_list: Optional[List[str]] = None,
        tokens_string_list: Optional[List[str]] = None,
        tokens_string: str = '',
    ):
        """
        Public Constructor: Initializes Token.
        
        Args:
            tokens_list: List of token strings
            tokens_string_list: List of token type codes
            tokens_string: Concatenated token type string
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__tokens_list: List[str] = tokens_list or []
        self.__tokens_string_list: List[str] = tokens_string_list or []
        self.__tokens_string: str = tokens_string
        
        _logger.debug("Token initialized with %d tokens", len(self.__tokens_list))

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_tokens_list(self) -> List[str]:
        """
        Public API: Returns the list of token strings.
        
        Returns:
            List of token strings
        """
        return self.__tokens_list

    def get_tokens_string_list(self) -> List[str]:
        """
        Public API: Returns the list of token type codes.
        
        Returns:
            List of token type codes (e.g., ['U', 'M', 'L'])
        """
        return self.__tokens_string_list

    def get_tokens_string(self) -> str:
        """
        Public API: Returns the concatenated token type string.
        
        Returns:
            Concatenated token type string (e.g., 'UML')
        """
        return self.__tokens_string

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps({
            'tokens_list': self.__tokens_list,
            'tokens_string_list': self.__tokens_string_list,
            'tokens_string': self.__tokens_string
        })

    def __len__(self) -> int:
        """
        Public API: Returns the number of tokens.
        
        Returns:
            Number of tokens
        """
        return len(self.__tokens_list)

    def __bool__(self) -> bool:
        """
        Public API: Returns True if token has content.
        
        Returns:
            True if tokens_list is not empty
        """
        return bool(self.__tokens_list)