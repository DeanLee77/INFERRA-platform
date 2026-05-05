"""
Node Set Module.
Manages collections of nodes/rules in the INFERRA rule tree.
Implements access levels and strong typing where appropriate.
"""

import json
import warnings
from typing import Any, Dict, List, Optional, Tuple
from src.shared.loggers import Logger
from src.domain.nodes.node import Node
from src.domain.nodes.dependency_matrix import DependencyMatrix
from src.domain.nodes.meta_data import MetaData

_logger: Logger = Logger.get_logger(__name__)


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
        self.__node_dictionary: Dict[str, Node] = dict()
        self.__node_id_dictionary: Dict[int, str] = dict()
        self.__stable_node_id_dictionary: Dict[str, str] = dict()
        self.__sorted_node_list: List[Node] = []
        self.__default_goal_node: Optional[Node] = None
        self.__dependency_matrix: DependencyMatrix = DependencyMatrix([[]])
        self.__matrix_explicit: bool = False
        self.__graph: Optional[Any] = None  # HyperAdjacencyGraph (lazy import)
        self._ensure_graph()
        
        _logger.info("NodeSet is generated")

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_dependency_matrix(self) -> DependencyMatrix:
        """
        Public API: Returns a legacy dependency matrix view.

        Phase 2.5 keeps this method for compatibility, but graph-backed
        NodeSets derive the matrix on demand from the canonical graph.
        
        Returns:
            DependencyMatrix object
        """
        if (
            self.__graph is not None
            and not self.__matrix_explicit
            and (len(self.__graph.all_node_names()) > 0 or any(True for _ in self.__graph.edges()))
        ):
            from src.domain.graph.graph_to_matrix_adapter import GraphToMatrixAdapter

            return GraphToMatrixAdapter(self.__graph)
        return self.__dependency_matrix

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
        self.__matrix_explicit = False

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_dependency_matrix(self, dependency_matrix: Any) -> None:
        """
        Public API: Sets the dependency matrix.
        
        Args:
            dependency_matrix: DependencyMatrix or list to set
        """
        if isinstance(dependency_matrix, list):
            self.__dependency_matrix = DependencyMatrix(dependency_matrix)
        elif isinstance(dependency_matrix, DependencyMatrix):
            self.__dependency_matrix = dependency_matrix
        else:
            return
        self.__matrix_explicit = True
        self._derive_graph_from_matrix()

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
        if not isinstance(nid, int):
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
        self.__matrix_explicit = False

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
            from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph

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
        if not self.__node_id_dictionary:
            return
        from src.domain.graph.matrix_to_hyper_adapter import MatrixToHyperGraphAdapter

        self.__graph = MatrixToHyperGraphAdapter(
            self.__dependency_matrix,
            dict(self.__node_id_dictionary),
        )

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
        children_list = self.__dependency_matrix.get_to_child_dependency_list(node_id)
        return len(children_list) > 0, children_list

    def _has_parents(self, node_id: int) -> Tuple[bool, List[int]]:
        """
        Protected Helper: Checks if node has parents.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            Tuple of (has_parents, parents_index_list)
        """
        parents_list = self.__dependency_matrix.get_from_parent_dependency_list(node_id)
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
