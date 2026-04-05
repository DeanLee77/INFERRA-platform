"""
Topological Sort Module.
Implements topological sorting algorithms for PALOS rule sets.
Implements access levels and strong typing where appropriate.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional
from project.loggers.logger import Logger
from project.nodes.node import Node
from project.nodes import DependencyType

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class TopologicalSort:
    """
    TopologicalSort provides algorithms for sorting nodes in dependency order.
    Supports BFS (Kahn's algorithm) and DFS approaches.
    
    Access Levels:
    - Public: Static API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal utilities (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods (BFS)
    # -------------------------------------------------------------------------
    @staticmethod
    def bfs_topological_sort(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """
        Public API: Topological sort using Kahn's algorithm (BFS).
        
        Note: Creates a copy of dependency_matrix to preserve original data.
        
        Args:
            node_dictionary: Mapping of node names to Node objects
            node_id_dictionary: Mapping of node IDs to node names
            dependency_matrix: 2D list representing dependencies
            
        Returns:
            Sorted list of Node objects, or empty list if cyclic
        """
        _logger.info("bfs_topological_sort ...")

        sorted_list: List[Node] = list()
        size_of_matrix = len(dependency_matrix)
        copy_of_dependency_matrix = TopologicalSort._create_copy_of_dependency_matrix(
            dependency_matrix, size_of_matrix
        )

        temp_list: List[Node] = list()
        s_list = TopologicalSort._filling_s_list(
            node_dictionary, node_id_dictionary, temp_list, copy_of_dependency_matrix
        )

        while len(s_list) > 0:
            node = s_list.pop(0)
            sorted_list.append(node)
            node_id = node.get_node_id()

            for index in range(size_of_matrix):
                if (node_id is not index) and copy_of_dependency_matrix[node_id][index] != -1:
                    copy_of_dependency_matrix[node_id][index] = -1
                    number_of_incoming_edge = TopologicalSort._count_incoming_edges(
                        copy_of_dependency_matrix, index, size_of_matrix
                    )
                    if number_of_incoming_edge == 0:
                        s_list.append(node_dictionary[node_id_dictionary[index]])

        if TopologicalSort._check_for_cycles(copy_of_dependency_matrix, size_of_matrix):
            sorted_list.clear()

        return sorted_list

    # -------------------------------------------------------------------------
    # Public Access Level: Static API Methods (DFS)
    # -------------------------------------------------------------------------
    @staticmethod
    def dfs_topological_sort(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """
        Public API: Topological sort using Depth First Search.
        
        Note: Strictly for sorting child nodes of IterateLine.
        Does NOT have a mechanism to check if it is DAG yet.
        
        Args:
            node_dictionary: Mapping of node names to Node objects
            node_id_dictionary: Mapping of node IDs to node names
            dependency_matrix: 2D list representing dependencies
            
        Returns:
            Sorted list of Node objects
        """
        sorted_list: List[Node] = list()
        copy_of_dependency_matrix = TopologicalSort._create_copy_of_dependency_matrix(
            dependency_matrix, len(dependency_matrix)
        )
        s_list = TopologicalSort._filling_s_list(
            node_dictionary, node_id_dictionary, list(), copy_of_dependency_matrix
        )
        visited_list: List[int] = list()
        
        while len(s_list) > 0:
            node = s_list.pop(0)
            sorted_list.append(node)
            visited_list.append(node.get_node_id())
            node_id = node.get_node_id()
            child_id_list = TopologicalSort._get_child_ids(copy_of_dependency_matrix, node_id)

            for child_id in child_id_list:
                current_node = node_dictionary[node_id_dictionary[child_id]]
                if child_id not in visited_list:
                    sorted_list.append(current_node)
                    visited_list.append(child_id)
                    TopologicalSort._deepening(
                        node_dictionary, node_id_dictionary,
                        copy_of_dependency_matrix, sorted_list,
                        visited_list, child_id
                    )

        return sorted_list

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    @staticmethod
    def _filling_s_list(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        temp_list: List[Node],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """
        Protected Helper: Fills the initial S list with nodes having no incoming edges.
        
        Args:
            node_dictionary: Mapping of node names to Node objects
            node_id_dictionary: Mapping of node IDs to node names
            temp_list: Temporary list to populate
            dependency_matrix: 2D list representing dependencies
            
        Returns:
            List of nodes with no incoming dependencies
        """
        size_of_matrix = len(dependency_matrix)
        for child_row in range(size_of_matrix):
            count = 0
            for parent_col in range(size_of_matrix):
                if (parent_col != child_row) and (dependency_matrix[parent_col][child_row] == -1):
                    count = count + 1
            if count == size_of_matrix - 1:
                temp_node_name = node_id_dictionary.get(child_row)
                if temp_node_name is not None:
                    temp_list.append(node_dictionary[temp_node_name])
        return temp_list

    @staticmethod
    def _create_copy_of_dependency_matrix(
        dependency_matrix: List[List[Any]],
        size_of_matrix: int,
    ) -> List[List[Any]]:
        """
        Protected Helper: Creates a deep copy of the dependency matrix.
        
        Args:
            dependency_matrix: Original dependency matrix
            size_of_matrix: Size of the matrix
            
        Returns:
            Deep copy of the dependency matrix
        """
        copy_of_dependency_matrix = [[0 for x in range(size_of_matrix)] for y in range(size_of_matrix)]
        for parent_col in range(size_of_matrix):
            for child_row in range(size_of_matrix):
                copy_of_dependency_matrix[parent_col][child_row] = deepcopy(dependency_matrix[parent_col][child_row])
        return copy_of_dependency_matrix

    @staticmethod
    def _deepening(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
        sorted_list: List[Node],
        visited_list: List[int],
        child_id: int,
    ) -> None:
        """
        Protected Helper: Recursively visits child nodes for DFS sorting.
        
        Args:
            node_dictionary: Mapping of node names to Node objects
            node_id_dictionary: Mapping of node IDs to node names
            dependency_matrix: 2D list representing dependencies
            sorted_list: List to append sorted nodes
            visited_list: List of visited node IDs
            child_id: Current child node ID
        """
        child_id_list = TopologicalSort._get_child_ids(dependency_matrix, child_id)

        for child_id in child_id_list:
            current_node = node_dictionary[node_id_dictionary[child_id]]
            if child_id not in visited_list:
                sorted_list.append(current_node)
                visited_list.append(child_id)
                TopologicalSort._deepening(
                    node_dictionary, node_id_dictionary,
                    dependency_matrix, sorted_list,
                    visited_list, child_id
                )

    @staticmethod
    def _count_incoming_edges(
        dependency_matrix: List[List[Any]],
        node_index: int,
        size_of_matrix: int,
    ) -> int:
        """
        Protected Helper: Counts incoming edges for a node.
        
        Args:
            dependency_matrix: 2D list representing dependencies
            node_index: Index of the node to check
            size_of_matrix: Size of the matrix
            
        Returns:
            Number of incoming edges
        """
        number_of_incoming_edge = size_of_matrix - 1
        for second_index in range(size_of_matrix):
            if (node_index != second_index) and (dependency_matrix[second_index][node_index] == -1):
                number_of_incoming_edge = number_of_incoming_edge - 1
        return number_of_incoming_edge

    @staticmethod
    def _get_child_ids(dependency_matrix: List[List[Any]], node_id: int) -> List[int]:
        """
        Protected Helper: Gets list of child node IDs for a given node.
        
        Args:
            dependency_matrix: 2D list representing dependencies
            node_id: ID of the parent node
            
        Returns:
            List of child node IDs
        """
        child_id_list: List[int] = list()
        for index in range(len(dependency_matrix)):
            if dependency_matrix[node_id][index] != -1:
                child_id_list.append(index)
        return child_id_list

    @staticmethod
    def _check_for_cycles(dependency_matrix: List[List[Any]], size_of_matrix: int) -> bool:
        """
        Protected Helper: Checks if the dependency matrix contains cycles.
        
        Args:
            dependency_matrix: 2D list representing dependencies
            size_of_matrix: Size of the matrix
            
        Returns:
            True if cycles detected, False otherwise
        """
        check_dag = False
        for i in range(size_of_matrix):
            for j in range(size_of_matrix):
                if (i != j) and dependency_matrix[i][j] != -1:
                    check_dag = True
                    _logger.error(f"Rules are not DAG, if it is not DAG then rules cannot be sorted. i: {i}, j: {j}")
                    break
        return check_dag