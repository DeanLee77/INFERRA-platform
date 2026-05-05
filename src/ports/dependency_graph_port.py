"""
Dependency Graph Port Module.
Abstract interface for dependency graph operations.

Uses only primitive types to avoid circular imports with domain.graph.
Phase 2.5 (WS-7): Added default method implementations for matrix-compatible
query API and new abstract methods register_node() and edges().
"""

from abc import ABCMeta, abstractmethod
from collections import deque
from typing import Deque, Dict, Iterator, Optional, Set, Tuple


class DependencyGraphPort(metaclass=ABCMeta):
    """
    Abstract interface for a dependency graph.

    Defines the contract for graph traversal and back-propagation.
    Implementations must support cycle-protected traversal and
    topological sorting.

    The port uses primitive types (str, int, Set, Tuple) rather than
    domain value objects to avoid circular imports. Adapters translate
    between port-level primitives and domain-level types.

    Default method implementations are provided for matrix-compatible
    query API. Concrete adapters only need to implement the abstract
    methods; defaults are inherited automatically.
    """

    @abstractmethod
    def add_dependency_group(
        self,
        parent: str,
        dep_type: int,
        children: Set[str],
    ) -> None:
        """
        Add a dependency group from parent to a set of children.

        Args:
            parent: Parent node name
            dep_type: Dependency type bit flag (int)
            children: Set of child node names
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_parent_edges(self, node_name: str) -> Set[str]:
        """
        Return the set of parent node names for the given node.

        Args:
            node_name: Node name to query

        Returns:
            Set of parent node names
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_child_groups(self, node_name: str) -> Tuple[Tuple[int, Tuple[str, ...]], ...]:
        """
        Return the dependency groups from this node as primitive tuples.

        Each group is (dep_type: int, children: tuple of str).

        Args:
            node_name: Node name to query

        Returns:
            Tuple of (dep_type, children_tuple) tuples
        """
        pass  # pragma: no cover

    @abstractmethod
    def back_propagate(self, changed_node: str, max_steps: int = 0) -> Deque[str]:
        """
        BFS back-propagation from a changed node to all affected parents.

        Args:
            changed_node: Name of the node that changed
            max_steps: Maximum BFS steps (0 = auto-compute)

        Returns:
            Deque of parent node names in BFS visit order

        Raises:
            CyclicGraphError: If traversal exceeds max_steps
        """
        pass  # pragma: no cover

    @abstractmethod
    def topological_sort(self) -> Tuple[str, ...]:
        """
        Return nodes in topological order.

        Returns:
            Tuple of node names in topological order
        """
        pass  # pragma: no cover

    @abstractmethod
    def all_node_names(self) -> Set[str]:
        """
        Return all node names known to the graph.

        Returns:
            Set of all node name strings
        """
        pass  # pragma: no cover

    @abstractmethod
    def has_node(self, node_name: str) -> bool:
        """
        Check whether a node name exists in the graph.

        Args:
            node_name: Node name to check

        Returns:
            True if the node exists
        """
        pass  # pragma: no cover

    @abstractmethod
    def register_node(self, name: str, metadata: Optional[dict] = None) -> int:
        """
        Register a node with optional metadata, returning a runtime integer ID.

        Args:
            name: Node name
            metadata: Optional dict of node metadata (e.g. stable_id, module)

        Returns:
            Runtime integer ID assigned to the node
        """
        pass  # pragma: no cover

    @abstractmethod
    def edges(self) -> Iterator[Tuple[str, str, int]]:
        """
        Iterate over all edges as (parent, child, dep_type) triples.

        Yields:
            Tuple of (parent_name, child_name, dep_type_int)
        """
        pass  # pragma: no cover

    def get_children_by_type(self, node_name: str, type_mask: int) -> Tuple[str, ...]:
        """
        Return children matching a bitmask filter.

        Default: O(groups) scan over get_child_groups().
        """
        result: list = []
        for dep_type, children in self.get_child_groups(node_name):
            if dep_type & type_mask == type_mask:
                result.extend(children)
        return tuple(result)

    def get_children_flat(self, node_name: str) -> Tuple[str, ...]:
        """
        Return all children as a flat tuple (regardless of type).

        Default: O(groups) scan over get_child_groups().
        """
        result: list = []
        for _, children in self.get_child_groups(node_name):
            result.extend(children)
        return tuple(result)

    def get_dependency_type(self, parent: str, child: str) -> int:
        """
        Return dep_type bitmask for a specific edge. Default: O(groups) scan.

        Returns -1 if no edge exists.
        """
        for dep_type, children in self.get_child_groups(parent):
            if child in children:
                return dep_type
        return -1

    def has_children_of_type(self, node_name: str, type_mask: int) -> bool:
        """Check if node has any children matching a bitmask."""
        return len(self.get_children_by_type(node_name, type_mask)) > 0

    def subgraph(self, node_names: Set[str]) -> 'DependencyGraphPort':
        """
        Extract induced subgraph preserving all dependency types.

        Default: rebuilds a fresh instance via __class__().
        """
        result = self.__class__()
        for name in node_names:
            if self.has_node(name):
                for dep_type, children in self.get_child_groups(name):
                    in_sub = {c for c in children if c in node_names}
                    if in_sub:
                        result.add_dependency_group(name, dep_type, in_sub)
        return result

    def lookup_by_id(self, runtime_id: int) -> Optional[str]:
        """
        Look up node name by runtime integer ID. Default: not supported.
        """
        return None

    def lookup_by_name(self, name: str) -> Optional[int]:
        """
        Look up runtime integer ID by node name. Default: not supported.
        """
        return None
