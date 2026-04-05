"""
Token String Dictionary Module.
Maps token type codes to FactValueType enums.
Implements access levels and strong typing where appropriate.
"""

from typing import Dict, Optional
from project.fact_values.fact_value_type import FactValueType


class TokenStringDictionary:
    """
    TokenStringDictionary provides mapping from token codes to FactValueType.
    Implements private class constants with public accessors.
    
    Access Levels:
    - Public: Static API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Class constants (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Class Constants (Name Mangling)
    # -------------------------------------------------------------------------
    __DICTIONARY: Dict[str, FactValueType] = {
        'No': FactValueType.INTEGER,
        'Do': FactValueType.DOUBLE,
        'De': FactValueType.DECIMAL,
        'Da': FactValueType.DATE,
        'Url': FactValueType.URL,
        'Id': FactValueType.GUID,
        'Ha': FactValueType.HASH,
        'Se': FactValueType.SECTION,
        'Q': FactValueType.DEFI_STRING,
        'false': FactValueType.BOOLEAN,
        'FALSE': FactValueType.BOOLEAN,
        'False': FactValueType.BOOLEAN,
        'true': FactValueType.BOOLEAN,
        'TRUE': FactValueType.BOOLEAN,
        'True': FactValueType.BOOLEAN,
        'WARNING': FactValueType.WARNING,
        'L': FactValueType.STRING,
        'M': FactValueType.STRING,
        'U': FactValueType.STRING,
        'C': FactValueType.STRING,
        'Pa': FactValueType.STRING,
        'Fu': FactValueType.STRING,
    }

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def find_fact_value_type(token: str) -> FactValueType:
        """
        Public API: Finds FactValueType for a given token code.
        
        Args:
            token: Token type code (e.g., 'No', 'Da', 'Url')
            
        Returns:
            FactValueType enum value, defaults to STRING if not found
        """
        return TokenStringDictionary.__DICTIONARY.get(token, FactValueType.STRING)

    @classmethod
    def get_all_key_and_values(cls) -> Dict[str, FactValueType]:
        """
        Public API: Returns all token-to-type mappings.
        
        Returns:
            Copy of the dictionary mapping
        """
        return cls.__DICTIONARY.copy()

    @classmethod
    def _is_known_token(cls, token: str) -> bool:
        """
        Protected Helper: Checks if token code is recognized.
        
        Args:
            token: Token code to check
            
        Returns:
            True if token is in dictionary
        """
        return token in cls.__DICTIONARY

    @classmethod
    def _get_default_type(cls) -> FactValueType:
        """
        Protected Helper: Returns default FactValueType for unknown tokens.
        
        Returns:
            Default FactValueType (STRING)
        """
        return FactValueType.STRING