"""
Dependency Group Module.
Immutable, hashable representation of a dependency group for HyperAdjacencyGraph.
Uses NamedTuple for __hash__/__eq__ guarantees.
"""

from typing import FrozenSet, NamedTuple

from src.domain.graph.dependency_type import DependencyType


class DependencyGroup(NamedTuple):
    """
    Immutable, hashable representation of a dependency group.

    A dependency group represents a set of child nodes that share the same
    dependency type from a common parent. NamedTuple provides built-in
    __hash__ and __eq__ for use in sets and dict keys.

    Attributes:
        dep_type: Dependency type bit flag
        children: Frozen set of child node name strings
    """

    dep_type: DependencyType
    children: FrozenSet[str]
