"""
Node Set Module.
Manages collections of nodes/rules in the PALOS rule tree.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from project.loggers import Logger
from project.nodes.node import Node
from . import MetaData, DependencyMatrix
import utils
import inspect

# Protected Module-Level Logger (Access Level: Protected)
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
        self.__sorted_node_list: List[Node] = []
        self.__default_goal_node: Optional[Node] = None
        self.__dependency_matrix: DependencyMatrix = DependencyMatrix([[]])
        
        _logger.info("NodeSet is generated")

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_dependency_matrix(self) -> DependencyMatrix:
        """
        Public API: Returns the dependency matrix.
        
        Returns:
            DependencyMatrix object
        """
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
        
        Returns:
            Dictionary mapping node IDs to node names
        """
        return self.__node_id_dictionary

    def get_node_dictionary(self) -> Dict[str, Node]:
        """
        Public API: Returns the node dictionary.
        
        Returns:
            Dictionary mapping node names to Node objects
        """
        return self.__node_dictionary

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
        """
        Public API: Returns the default goal node.
        
        Returns:
            Default goal Node or None
        """
        return self.__default_goal_node

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
        
        Args:
            node_id: Node ID
            
        Returns:
            Node object
        """
        return self.get_node(self.get_node_id_dictionary()[node_id])

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