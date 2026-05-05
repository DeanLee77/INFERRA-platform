"""
Graph Dependency Builder Module.
Collects parent-child dependency relationships during parsing and writes
them directly to a HyperAdjacencyGraph, replacing the legacy
DependencyBuilder → DynamicVectorisedDependencyMatrix → DependencyMatrix pipeline.

Maintains an internal id→name mapping so the parser's integer-based flow
continues to work. The graph converts to name-based storage.

Phase 2.5 (WS-2): New builder that bypasses the matrix entirely.
"""

from typing import Dict, List, Optional, Set

from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.nodes.node import Node


class GraphDependencyBuilder:
    """
    Builds a HyperAdjacencyGraph during rule scanning.

    The parser's integer-based flow is preserved as a convenience:
    the builder translates integer node IDs to name-based storage on the graph.
    Write-time bitmask merge ensures overlapping edges are composed correctly.
    """

    def __init__(self, graph: Optional[HyperAdjacencyGraph] = None):
        self._graph: HyperAdjacencyGraph = graph if graph is not None else HyperAdjacencyGraph()
        self._id_to_name: Dict[int, str] = {}
        self._name_to_id: Dict[str, int] = {}

    @property
    def graph(self) -> HyperAdjacencyGraph:
        return self._graph

    def register_node(self, node_id: int, name: str, metadata: Optional[dict] = None) -> None:
        """
        Register a node by its integer ID and name.

        Args:
            node_id: Parser-assigned integer node ID
            name: Node name (variable name)
            metadata: Optional metadata dict for NodeRecord
        """
        self._id_to_name[node_id] = name
        self._name_to_id[name] = node_id
        self._graph.register_node(name, metadata)

    def add_dependency(self, parent_id: int, child_id: int, dep_type: int) -> None:
        """
        Add a dependency edge using integer IDs.

        Translates to name-based storage on the graph. Bitmask merge
        is handled by the graph's add_dependency_group().

        Args:
            parent_id: Parent node's integer ID
            child_id: Child node's integer ID
            dep_type: Dependency type bitmask
        """
        parent_name = self._id_to_name.get(parent_id, f"__node_{parent_id}__")
        child_name = self._id_to_name.get(child_id, f"__node_{child_id}__")
        self._graph.add_dependency_group(parent_name, dep_type, {child_name})

    def add_dependencies_from_nodes(self, parent: Node, child: Node, dep_type: int) -> None:
        """
        Add a dependency from Node objects (convenience for parser integration).

        Args:
            parent: Parent Node
            child: Child Node
            dep_type: Dependency type bitmask
        """
        pid = self._name_to_id.get(parent.get_node_name())
        if pid is None:
            pid = getattr(parent, '_node_id', None)
        cid = self._name_to_id.get(child.get_node_name())
        if cid is None:
            cid = getattr(child, '_node_id', None)

        if pid is not None:
            self._id_to_name.setdefault(pid, parent.get_node_name())
        if cid is not None:
            self._id_to_name.setdefault(cid, child.get_node_name())

        parent_name = parent.get_node_name()
        child_name = child.get_node_name()
        self._name_to_id.setdefault(parent_name, pid if pid is not None else -1)
        self._name_to_id.setdefault(child_name, cid if cid is not None else -1)

        self._graph.add_dependency_group(parent_name, dep_type, {child_name})

    def get_id_to_name_map(self) -> Dict[int, str]:
        return dict(self._id_to_name)

    def get_name_to_id_map(self) -> Dict[str, int]:
        return dict(self._name_to_id)
