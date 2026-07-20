"""Core-owned dependency graph value types."""

from enum import IntFlag
from typing import FrozenSet, List, NamedTuple


class DependencyType(IntFlag):
    """Dependency relationship flags preserving the legacy PALOS bit layout."""

    KNOWN = 1
    NOT = 2
    OR = 4
    AND = 8
    POSSIBLE = 16
    OPTIONAL = 32
    MANDATORY = 64

    @classmethod
    def get_mandatory(cls) -> int:
        return int(cls.MANDATORY)

    @classmethod
    def get_optional(cls) -> int:
        return int(cls.OPTIONAL)

    @classmethod
    def get_possible(cls) -> int:
        return int(cls.POSSIBLE)

    @classmethod
    def get_and(cls) -> int:
        return int(cls.AND)

    @classmethod
    def get_or(cls) -> int:
        return int(cls.OR)

    @classmethod
    def get_not(cls) -> int:
        return int(cls.NOT)

    @classmethod
    def get_known(cls) -> int:
        return int(cls.KNOWN)

    @classmethod
    def populating_dependency(cls) -> None:
        """Retain the legacy no-op hook for compatibility."""

    @classmethod
    def get_dependency_array(cls) -> List[int]:
        """Return dependency bits in legacy matcher order."""
        return [
            cls.get_and(),
            cls.get_or(),
            cls.get_not(),
            cls.get_known(),
            cls.get_mandatory(),
            cls.get_optional(),
            cls.get_possible(),
        ]


class DependencyGroup(NamedTuple):
    """Immutable, hashable group of children sharing a dependency type."""

    dep_type: DependencyType
    children: FrozenSet[str]

