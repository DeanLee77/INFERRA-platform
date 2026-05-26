"""
Canonical graph dependency type flags.

The values intentionally preserve the legacy PALOS bitmask layout while using
IntFlag so composed dependencies such as MANDATORY | AND remain first-class
values.
"""

from enum import IntFlag
from typing import List


class DependencyType(IntFlag):
    """Dependency relationship flags used by graph and matrix adapters."""

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
        """
        Legacy compatibility hook.

        The old node-level class appended to mutable class state. The canonical
        enum is immutable, so callers should read get_dependency_array().
        """

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
