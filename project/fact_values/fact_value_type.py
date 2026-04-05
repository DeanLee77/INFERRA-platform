"""
Fact Value Type Enum.
Defines all possible fact value types in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

import json
from enum import Enum
from typing import List

class FactValueType(Enum):
    """
    Enum containing all fact value types.
    Members are Public (API).
    """
    # -------------------------------------------------------------------------
    # Public Access Level: Enum Members (API Surface)
    # -------------------------------------------------------------------------
    BOOLEAN = "BOOLEAN "
    INTEGER = "INTEGER "
    DEFI_STRING = "DEFI_STRING "
    TEXT = "TEXT "
    STRING = "STRING "
    DOUBLE = "DOUBLE "
    NUMBER = "NUMBER "
    DATE = "DATE "
    DECIMAL = "DECIMAL "
    LIST = "LIST "
    RULE = "RULE "
    RULE_SET = "RULE_SET "
    OBJECT = "OBJECT "
    UNKNOWN = "UNKNOWN "
    URL = "URL "
    HASH = "HASH "
    GUID = "GUID "
    SECTION = "SECTION "
    NULL = "NULL "
    WARNING = "WARNING "

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_all_values() -> List[str]:
        """
        Public API: Returns all fact value type strings.
        
        Returns:
            List of all fact value type strings
        """
        return FactValueType._extract_values()

    @staticmethod
    def get_all_enums() -> List['FactValueType']:
        """
        Public API: Returns all fact value type enums.
        
        Returns:
            List of all FactValueType enum members
        """
        return FactValueType._extract_enums()

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_values() -> List[str]:
        """
        Protected Helper: Extracts values from Enum.
        Intended for internal use or subclassing.
        
        Returns:
            List of enum value strings
        """
        return [member.value for member in FactValueType]

    @staticmethod
    def _extract_enums() -> List['FactValueType']:
        """
        Protected Helper: Extracts Enum members.
        Intended for internal use or subclassing.
        
        Returns:
            List of enum members
        """
        return list(FactValueType)

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the enum.
        
        Returns:
            JSON string representation
        """
        return json.dumps({"value": self.value, "name": self.name})

    @classmethod
    def __contains__(cls, item: str) -> bool:
        """
        Private Helper: Check if item exists in enum values.
        Name-mangled for encapsulation.
        
        Args:
            item: Item to check
            
        Returns:
            True if item exists in enum values
        """
        return item in [v.value for v in cls.__members__.values()]