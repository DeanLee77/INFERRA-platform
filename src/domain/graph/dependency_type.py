"""
Dependency Type Enum for HyperAdjacencyGraph.
Wraps the existing DependencyType bit flags for graph-level usage.

Phase 2.5 (WS-7): Migrated from IntEnum to IntFlag to enable native
bitmask operations (|, &, in) without casting.
"""

from enum import IntFlag
from src.domain.nodes.dependency_type import DependencyType as _DT


class DependencyType(IntFlag):
    """
    Graph-level dependency type enum.
    Values match the bit-flag constants in nodes.dependency_type.DependencyType.

    IntFlag enables native bitmask composition:
      DependencyType.MANDATORY | DependencyType.AND  → DependencyType.MANDATORY|AND (72)
      DependencyType.AND in (DependencyType.MANDATORY | DependencyType.AND)  → True
    """

    MANDATORY = _DT.get_mandatory()
    OPTIONAL = _DT.get_optional()
    POSSIBLE = _DT.get_possible()
    AND = _DT.get_and()
    OR = _DT.get_or()
    NOT = _DT.get_not()
    KNOWN = _DT.get_known()
