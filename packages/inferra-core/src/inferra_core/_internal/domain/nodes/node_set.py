"""
Node Set Module.
Manages collections of nodes/rules in the INFERRA rule tree.
Implements access levels and strong typing where appropriate.
"""

import json
import warnings
from typing import Any, Dict, List, Optional, Tuple
from inferra_core._internal._logging import get_logger
from inferra_core._internal.domain.nodes.node import Node
from inferra_core._internal.domain.nodes.meta_data import MetaData

_logger = get_logger(__name__)


class LegacyMatrixAdapterRequired(RuntimeError):
    """Raised when a host requests a Platform-owned matrix compatibility view."""


def _legacy_matrix_error() -> LegacyMatrixAdapterRequired:
    return LegacyMatrixAdapterRequired(
        "Legacy dependency matrices are inferra-platform compatibility "
        "adapters and are not part of inferra-core"
    )


class NodeSet:
    """
    NodeSet manages a collection of nodes forming a rule tree.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self):
        """
        Public Constructor: Initializes NodeSet.
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__node_set_name: str = ''
        self.__input_dictionary: Dict[str, Any] = dict()
        self.__fact_dictionary: Dict[str, Any] = dict()
        self.__type_dictionary: Dict[str, Dict[str, Any]] = dict()
        self.__collection_dictionary: Dict[str, Dict[str, Any]] = dict()
        self.__node_dictionary: Dict[str, Node] = dict()
        self.__node_id_dictionary: Dict[int, str] = dict()
        self.__stable_node_id_dictionary: Dict[str, str] = dict()
        self.__sorted_node_list: List[Node] = []
        self.__default_goal_node: Optional[Node] = None
        self.__legacy_dependency_matrix_payload: Optional[Any] = None
        self.__graph: Optional[Any] = None  # HyperAdjacencyGraph (lazy import)
        self._ensure_graph()
        
        _logger.info("NodeSet is generated")

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_dependency_matrix(self) -> Any:
        """
        Deprecated API: Returns a legacy dependency matrix view.

        Core does not carry the compatibility adapter. Platform may expose a
        host wrapper for legacy callers; direct Core use raises
        :class:`LegacyMatrixAdapterRequired`.

        .. deprecated:: Phase 2.5
            Use get_graph() / DependencyGraphPort instead. Matrix views are
            compatibility-only and must not be used by runtime code.
        
        Returns:
            Matrix-like object
        """
        warnings.warn(
            "NodeSet.get_dependency_matrix() is deprecated for runtime use; use get_graph() "
            "or DependencyGraphPort instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        raise _legacy_matrix_error()

    def get_node_set_name(self) -> str:
        """
        Public API: Returns the node set name.
        
        Returns:
            Node set name string
        """
        return self.__node_set_name

    def get_node_id_dictionary(self) -> Dict[int, str]:
        """
        Public API: Returns the node ID dictionary.

        .. deprecated:: Phase 2
            Use :meth:`get_stable_node_id_dictionary` instead.
            Runtime integer node IDs will be removed in Phase 3+.

        Returns:
            Dictionary mapping node IDs to node names
        """
        warnings.warn(
            "NodeSet.get_node_id_dictionary() is deprecated; use get_stable_node_id_dictionary()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.__node_id_dictionary

    def get_node_dictionary(self) -> Dict[str, Node]:
        """
        Public API: Returns the node dictionary.
        
        Returns:
            Dictionary mapping node names to Node objects
        """
        return self.__node_dictionary

    def get_stable_node_id_dictionary(self) -> Dict[str, str]:
        """
        Public API: Returns the stable node ID dictionary.

        Returns:
            Dictionary mapping stable IDs to node names
        """
        return self.__stable_node_id_dictionary

    def get_sorted_node_list(self) -> List[Node]:
        """
        Public API: Returns the sorted node list.
        
        Returns:
            List of Node objects in sorted order
        """
        return self.__sorted_node_list

    def get_input_dictionary(self) -> Dict[str, Any]:
        """
        Public API: Returns the input dictionary.
        
        Returns:
            Dictionary of input facts
        """
        return self.__input_dictionary

    def get_fact_dictionary(self) -> Dict[str, Any]:
        """
        Public API: Returns the fact dictionary.
        
        Returns:
            Dictionary of fixed facts
        """
        return self.__fact_dictionary

    def get_type_dictionary(self) -> Dict[str, Dict[str, Any]]:
        """
        Public API: Returns declared record types.

        Shape:
            {
                "service period": {
                    "fields": {
                        "period of service in days": FactValueType.DOUBLE
                    },
                    "field_options": {
                        "service type": "DVA service type options"
                    }
                }
            }
        """
        return self.__type_dictionary

    def get_collection_dictionary(self) -> Dict[str, Dict[str, Any]]:
        """
        Public API: Returns declared collection metadata.

        Shape:
            {
                "service history": {
                    "item_type": "service period",
                    "size_from": "number of service periods"
                }
            }
        """
        return self.__collection_dictionary

    def get_default_goal_node(self) -> Optional[Node]:
        return self.__default_goal_node

    def get_graph(self) -> Optional[Any]:
        """
        Public API: Returns the canonical HyperAdjacencyGraph.

        Returns None if no graph has been set (legacy NodeSet without graph).
        """
        return self.__graph

    def set_graph(self, graph: Any) -> None:
        """
        Public API: Sets the canonical HyperAdjacencyGraph.

        Args:
            graph: HyperAdjacencyGraph instance
        """
        self.__graph = graph
        self.__legacy_dependency_matrix_payload = None

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_dependency_matrix(self, dependency_matrix: Any) -> None:
        """
        Deprecated API: Sets a legacy dependency matrix payload.

        .. deprecated:: Phase 2.5
            Use set_graph() with HyperAdjacencyGraph instead. Core rejects this
            call because matrix-to-graph migration belongs to Platform.
        
        Args:
            dependency_matrix: legacy matrix-like object or 2D list to adapt
        """
        warnings.warn(
            "NodeSet.set_dependency_matrix() is deprecated; use set_graph() with "
            "HyperAdjacencyGraph instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        del dependency_matrix
        raise _legacy_matrix_error()

    def set_node_set_name(self, node_set_name: str) -> None:
        """
        Public API: Sets the node set name.
        
        Args:
            node_set_name: Name to set
        """
        if len(node_set_name) == 0:
            _logger.error("node_set_name is None")
        self.__node_set_name = node_set_name

    def set_node_id_dictionary(self, node_id_dictionary: Dict[int, str]) -> None:
        """
        Public API: Sets the node ID dictionary.
        
        Args:
            node_id_dictionary: Dictionary to set
        """
        if len(node_id_dictionary) == 0:
            _logger.debug("node_id_dictionary has no items")
        self.__node_id_dictionary = node_id_dictionary
        self._derive_graph_from_matrix()

    def set_stable_node_id_dictionary(self, stable_node_id_dictionary: Dict[str, str]) -> None:
        """
        Public API: Sets the stable node ID dictionary.

        Args:
            stable_node_id_dictionary: Dictionary to set
        """
        if len(stable_node_id_dictionary) == 0:
            _logger.debug("stable_node_id_dictionary has no items")
        self.__stable_node_id_dictionary = stable_node_id_dictionary

    def set_node_dictionary(self, node_dictionary: Dict[str, Node]) -> None:
        """
        Public API: Sets the node dictionary.
        
        Args:
            node_dictionary: Dictionary to set
        """
        if len(node_dictionary) == 0:
            _logger.debug("node_dictionary has no items")
        self.__node_dictionary = node_dictionary

    def set_sorted_node_list(self, sorted_node_list: List[Node]) -> None:
        """
        Public API: Sets the sorted node list.
        
        Args:
            sorted_node_list: List to set
        """
        if len(sorted_node_list) == 0:
            _logger.error("sorted_node_list has no items")
        self.__sorted_node_list = sorted_node_list

    def set_fact_dictionary(self, fact_dictionary: Dict[str, Any]) -> None:
        """
        Public API: Sets the fact dictionary.
        
        Args:
            fact_dictionary: Dictionary to set
        """
        if len(fact_dictionary) == 0:
            _logger.info("fact_dictionary has no items")
        self.__fact_dictionary = fact_dictionary

    def set_input_dictionary(self, input_dictionary: Dict[str, Any]) -> None:
        """
        Public API: Sets the input dictionary.

        Args:
            input_dictionary: Dictionary to set
        """
        if len(input_dictionary) == 0:
            _logger.debug("input_dictionary has no items")
        self.__input_dictionary = input_dictionary

    def set_type_dictionary(self, type_dictionary: Dict[str, Dict[str, Any]]) -> None:
        """
        Public API: Sets declared record types.

        Args:
            type_dictionary: Dictionary to set
        """
        if len(type_dictionary) == 0:
            _logger.debug("type_dictionary has no items")
        self.__type_dictionary = type_dictionary

    def set_collection_dictionary(self, collection_dictionary: Dict[str, Dict[str, Any]]) -> None:
        """
        Public API: Sets declared collection metadata.

        Args:
            collection_dictionary: Dictionary to set
        """
        if len(collection_dictionary) == 0:
            _logger.debug("collection_dictionary has no items")
        self.__collection_dictionary = collection_dictionary

    def register_type(self, type_name: str) -> None:
        if not type_name:
            return
        self.__type_dictionary.setdefault(type_name, {"fields": {}})

    def register_type_field(self, type_name: str, field_name: str, field_type: Any) -> None:
        if not type_name or not field_name:
            return
        self.register_type(type_name)
        self.__type_dictionary[type_name].setdefault("fields", {})[field_name] = field_type

    def register_type_field_options(
        self,
        type_name: str,
        field_name: str,
        option_list_name: str,
    ) -> None:
        if not type_name or not field_name or not option_list_name:
            return
        self.register_type(type_name)
        self.__type_dictionary[type_name].setdefault("field_options", {})[
            field_name
        ] = option_list_name

    def register_collection(
        self,
        collection_name: str,
        item_type: Optional[str] = None,
        size_from: Optional[str] = None,
    ) -> None:
        if not collection_name:
            return
        metadata = self.__collection_dictionary.setdefault(collection_name, {})
        if item_type:
            metadata["item_type"] = item_type
        if size_from:
            metadata["size_from"] = size_from

    def register_collection_field(
        self,
        collection_name: str,
        field_name: str,
        field_type: Any,
    ) -> None:
        if not collection_name or not field_name:
            return
        metadata = self.__collection_dictionary.setdefault(collection_name, {})
        metadata.setdefault("fields", {})[field_name] = field_type

    def register_collection_field_options(
        self,
        collection_name: str,
        field_name: str,
        option_list_name: str,
    ) -> None:
        if not collection_name or not field_name or not option_list_name:
            return
        metadata = self.__collection_dictionary.setdefault(collection_name, {})
        metadata.setdefault("field_options", {})[field_name] = option_list_name

    def set_default_goal_node(self, name: str) -> None:
        """
        Public API: Sets the default goal node by name.
        
        Args:
            name: Name of the goal node
        """
        self.__default_goal_node = self.get_node_dictionary().get(name)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Node Retrieval)
    # -------------------------------------------------------------------------
    def get_node(self, node_index: int) -> Node:
        """
        Public API: Gets a node by index.
        
        Args:
            node_index: Index in sorted list
            
        Returns:
            Node object
        """
        return self.get_sorted_node_list()[node_index]

    def get_node_by_node_id(self, node_id: int) -> Node:
        """
        Public API: Gets a node by ID.

        .. deprecated:: Phase 2
            Use :meth:`get_node_by_stable_node_id` or look up by name
            via :meth:`get_node_dictionary` instead.

        Args:
            node_id: Node ID

        Returns:
            Node object
        """
        warnings.warn(
            "NodeSet.get_node_by_node_id() is deprecated; use get_node_by_stable_node_id() or get_node_dictionary()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_node_dictionary()[self.__node_id_dictionary[node_id]]

    def get_node_by_stable_node_id(self, stable_node_id: str) -> Node:
        """
        Public API: Gets a node by its canonical stable ID.

        Args:
            stable_node_id: Stable node ID

        Returns:
            Node object
        """
        return self.get_node_dictionary()[self.get_stable_node_id_dictionary()[stable_node_id]]

    def register_node(self, node: Node, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Public API: Registers a node across name, runtime ID, and stable ID lookups.

        Args:
            node: Node to register
            metadata: Optional graph NodeRecord metadata
        """
        self.__node_dictionary[node.get_node_name()] = node

        nid = getattr(node, '_node_id', None)
        if nid is not None and isinstance(nid, int):
            self.__node_id_dictionary[nid] = node.get_node_name()

        if node.get_stable_node_id() is not None:
            self.__stable_node_id_dictionary[node.get_stable_node_id()] = node.get_node_name()

        if self.__graph is not None:
            graph_metadata = self._metadata_for_node(node, metadata)
            self.__graph.register_node(node.get_node_name(), graph_metadata)

    def add_node(self, node: Node, metadata: Optional[Dict[str, Any]] = None) -> None:
        nid = getattr(node, '_node_id', None)
        if not isinstance(nid, int) or nid in self.__node_id_dictionary:
            node._node_id = self.get_next_node_id()
            node._node_unique_id = node._node_id
        self.register_node(node, metadata)
        self.__sorted_node_list.append(node)

    def remove_node_by_name(self, name: str) -> None:
        node = self.__node_dictionary.pop(name, None)
        if node is None:
            return

        nid = getattr(node, '_node_id', None)
        if isinstance(nid, int):
            self.__node_id_dictionary.pop(nid, None)

        if node.get_stable_node_id() is not None:
            self.__stable_node_id_dictionary.pop(node.get_stable_node_id(), None)

        self.__sorted_node_list = [
            n for n in self.__sorted_node_list if n.get_node_name() != name
        ]

        if self.__graph is not None:
            self._remove_node_from_graph(name)

    def _remove_node_from_graph(self, name: str) -> None:
        """Remove a node and all its edges from the graph."""
        if self.__graph is None:
            return
        if hasattr(self.__graph, "remove_node"):
            self.__graph.remove_node(name)

    def get_next_node_id(self) -> int:
        """
        Public API: Returns the next available runtime node ID for this node set.

        Returns:
            Next runtime node ID
        """
        if len(self.__node_id_dictionary) == 0:
            return 0
        return max(self.__node_id_dictionary.keys()) + 1

    def find_node_index(self, node_name: str) -> int:
        """
        Public API: Finds the index of a node by name.
        
        Args:
            node_name: Name of the node
            
        Returns:
            Index in sorted list, or -1 if not found
        """
        for node_index in range(len(self.get_sorted_node_list())):
            if self.get_sorted_node_list()[node_index].get_node_name() == node_name:
                return node_index
        return -1

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Working Memory)
    # -------------------------------------------------------------------------
    def transfer_fact_dictionary_to_working_memory(self, working_memory: Dict[str, Any]) -> Dict[str, Any]:
        """
        Public API: Transfers fact dictionary to working memory.
        
        Args:
            working_memory: Working memory dictionary to update
            
        Returns:
            Updated working memory dictionary
        """
        if len(working_memory) == 0:
            _logger.info("working_memory has no items")
        for key in self.get_fact_dictionary().keys():
            working_memory[key] = self.get_fact_dictionary()[key]
        return working_memory

    def rebuild_dependency_groups(self) -> None:
        self._ensure_graph()
        self._rebuild_graph_edges()
        self.__legacy_dependency_matrix_payload = None

    def _rebuild_graph_edges(self) -> None:
        """Reconstruct graph edges from node dependency metadata."""
        if self.__graph is None:
            return
        node_dict = self.get_node_dictionary()
        for node in node_dict.values():
            deps = getattr(node, '_dependencies', None)
            if deps is None:
                continue
            for dep in deps:
                parent_name = dep.get('parent_name')
                child_name = dep.get('child_name')
                if parent_name and child_name:
                    self.__graph.add_dependency_group(
                        parent_name, dep.get('dep_type', 4), {child_name}
                    )

    def _ensure_graph(self) -> None:
        """Create the canonical graph lazily without importing at module load."""
        if self.__graph is None:
            from inferra_core._internal.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph

            self.__graph = HyperAdjacencyGraph()

    def _metadata_for_node(
        self,
        node: Node,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build NodeRecord metadata without relying on dynamic node._origin."""
        result: Dict[str, Any] = dict(metadata or {})
        nid = getattr(node, "_node_id", None)
        if isinstance(nid, int):
            result.setdefault("runtime_id", nid)
        if node.get_stable_node_id() is not None:
            result.setdefault("stable_id", node.get_stable_node_id())
        return result

    def _derive_graph_from_matrix(self) -> None:
        """Refresh the canonical graph from an explicitly assigned legacy matrix."""
        if self.__legacy_dependency_matrix_payload is None or not self.__node_id_dictionary:
            return
        raise _legacy_matrix_error()

    def _matrix_view_from_graph(self) -> Any:
        raise _legacy_matrix_error()

    def _legacy_matrix_payload(self) -> Any:
        raise _legacy_matrix_error()

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _has_children(self, node_id: int) -> Tuple[bool, List[int]]:
        """
        Protected Helper: Checks if node has children.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            Tuple of (has_children, children_index_list)
        """
        children_list: List[int] = []
        if self.__graph is not None:
            node_name = self.__graph.lookup_by_id(node_id)
            if node_name is not None:
                children_list = [
                    child_id
                    for child_id in (
                        self.__graph.lookup_by_name(child)
                        for child in self.__graph.get_children_flat(node_name)
                    )
                    if child_id is not None
                ]
        return len(children_list) > 0, children_list

    def _has_parents(self, node_id: int) -> Tuple[bool, List[int]]:
        """
        Protected Helper: Checks if node has parents.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            Tuple of (has_parents, parents_index_list)
        """
        parents_list: List[int] = []
        if self.__graph is not None:
            node_name = self.__graph.lookup_by_id(node_id)
            if node_name is not None:
                parents_list = [
                    parent_id
                    for parent_id in (
                        self.__graph.lookup_by_name(parent)
                        for parent in self.__graph.get_parent_edges(node_name)
                    )
                    if parent_id is not None
                ]
        return len(parents_list) > 0, parents_list

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)
