"""
Line Type Enum.
Defines all possible line types in INFERRA rule sets.
Implements access levels and strong typing where appropriate.
"""

from enum import Enum
from typing import Optional, Type


class LineType(Enum):
    """
    Enum containing all line types.
    Members are Public (API).
    """
    # -------------------------------------------------------------------------
    # Public Access Level: Enum Members (API Surface)
    # -------------------------------------------------------------------------
    META = "META"
    VALUE_CONCLUSION = "VALUE_CONCLUSION"
    EXPR_CONCLUSION = "EXPR_CONCLUSION"
    COMPARISON = "COMPARISON"
    ITERATE = "ITERATE"
    WARNING = "WARNING"

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def get_all_values() -> list[str]:
        """
        Public API: Returns all line type strings.
        
        Returns:
            List of all line type value strings
        """
        return [member.value for member in LineType]

    @staticmethod
    def get_appropriate_node_type(node_type: str) -> Optional[Type]:
        """
        Public API: Returns the appropriate node class for a line type.
        
        Args:
            node_type: String representation of line type
            
        Returns:
            Node class type or None if not found
        """
        from src.domain.nodes import MetadataLine, ValueConclusionLine, ExprConclusionLine, ComparisonLine
        from src.domain.nodes.iterate_line import IterateLine
        
        if node_type == LineType.META.value:
            return MetadataLine
        elif node_type == LineType.ITERATE.value:
            return IterateLine
        elif node_type == LineType.COMPARISON.value:
            return ComparisonLine
        elif node_type == LineType.EXPR_CONCLUSION.value:
            return ExprConclusionLine
        elif node_type == LineType.VALUE_CONCLUSION.value:
            return ValueConclusionLine
        return None
