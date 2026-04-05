"""
Meta Type Enum.
Defines all possible metadata types in PALOS rule sets.
Implements access levels and strong typing where appropriate.
"""

from enum import Enum
from typing import List


class MetaType(Enum):
    """
    Enum containing all metadata types.
    Members are Public (API).
    """
    # -------------------------------------------------------------------------
    # Public Access Level: Enum Members (API Surface)
    # -------------------------------------------------------------------------
    LINE = 'LINE'
    FIXED = 'FIXED'
    INPUT = 'INPUT'
    ITEM = 'ITEM'
    GOAL = 'GOAL'
    CLICK_LINK = 'CLICK_LINK'
    DOC = 'DOC'
    IMPORT = 'IMPORT'

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_all_meta_type() -> List['MetaType']:
        """
        Public API: Returns all meta type enums.
        
        Returns:
            List of all MetaType enum members
        """
        return list(MetaType)