"""
Topological Sort Module.
Implements topological sorting algorithms for INFERRA rule sets.

Three sorting strategies:
1. bfs_topological_sort — Kahn's algorithm, deterministic order, no history
2. dfs_topological_sort — plain DFS, deterministic order, no history
3. dfs_topological_sort_with_record — ML-optimized DFS using HistoryRecord
   data to reorder child traversal so nodes most likely to prune the search
   space are visited first. Gated by ML_OPTIMIZED_DFS feature flag.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional

import structlog

from src.domain.nodes.dependency_type import DependencyType
from src.domain.nodes.node import Node
from src.domain.nodes.record import HistoryRecord

logger = structlog.get_logger(__name__)


class TopologicalSort:

    @staticmethod
    def bfs_topological_sort(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """
        Topological sort using Kahn's algorithm (BFS).

        Note: Creates a copy of dependency_matrix to preserve original data.

        Args:
            node_dictionary: Mapping of node names to Node objects
            node_id_dictionary: Mapping of node IDs to node names
            dependency_matrix: 2D list representing dependencies

        Returns:
            Sorted list of Node objects, or empty list if cyclic
        """
        logger.info("bfs_topological_sort")

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

    @staticmethod
    def dfs_topological_sort(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """
        Topological sort using Depth First Search.

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

    @staticmethod
    def dfs_topological_sort_with_record(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
    ) -> List[Node]:
        """
        ML-optimized DFS topological sort using HistoryRecord data.

        When ML_OPTIMIZED_DFS is enabled, the engine uses historical
        true/false counts to reorder child traversal so that nodes most
        likely to prune the search space are visited first:

        - OR rules: visit the most-likely-TRUE child first (shortest
          path to a TRUE parent result)
        - AND rules: visit the most-likely-FALSE child first (shortest
          path to a FALSE parent result)

        Falls back to bfs_topological_sort when no records are available.

        Args:
            node_dictionary: Mapping of node names to Node objects
            node_id_dictionary: Mapping of node IDs to node names
            dependency_matrix: 2D list representing dependencies
            record_dictionary_of_nodes: Dict mapping node name -> HistoryRecord

        Returns:
            Sorted list of Node objects
        """
        if not record_dictionary_of_nodes:
            return TopologicalSort.bfs_topological_sort(
                node_dictionary, node_id_dictionary, dependency_matrix
            )

        sorted_list: List[Node] = list()
        visited_node_list: List[Node] = list()
        copy_of_dependency_matrix = TopologicalSort._create_copy_of_dependency_matrix(
            dependency_matrix, len(dependency_matrix)
        )
        s_list = TopologicalSort._filling_s_list(
            node_dictionary, node_id_dictionary, list(), copy_of_dependency_matrix
        )

        while len(s_list) > 0:
            node = s_list.pop(0)
            visited_node_list.append(node)
            TopologicalSort._visit(
                node, sorted_list, record_dictionary_of_nodes,
                node_dictionary, node_id_dictionary,
                visited_node_list, dependency_matrix,
            )

        return sorted_list

    @staticmethod
    def _visit(
        node: Node,
        sorted_list: List[Node],
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        visited_node_list: List[Node],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """
        Visit a node and recursively visit children in ML-optimized order.

        For OR-only children: visit most-likely-TRUE first.
        For AND-only children: visit most-likely-FALSE first.
        For mixed children: OR children first (most-TRUE), then AND (most-FALSE).
        """
        if node is None:
            return sorted_list

        sorted_list.append(node)
        node_id = node.get_node_id()
        or_dependency_type = DependencyType.get_or()
        and_dependency_type = DependencyType.get_and()
        dependency_matrix_as_list = list(dependency_matrix[node_id])
        size_of_dependency_matrix_as_list = len(dependency_matrix_as_list)

        or_out_dependency = [
            idx for idx in range(size_of_dependency_matrix_as_list)
            if dependency_matrix_as_list[idx] > 0
            and (dependency_matrix_as_list[idx] & or_dependency_type) == or_dependency_type
        ]
        and_out_dependency = [
            idx for idx in range(size_of_dependency_matrix_as_list)
            if dependency_matrix_as_list[idx] > 0
            and (dependency_matrix_as_list[idx] & and_dependency_type) == and_dependency_type
        ]

        if not or_out_dependency and not and_out_dependency:
            return sorted_list

        child_rule_list: List[Node] = []
        for idx in range(size_of_dependency_matrix_as_list):
            if dependency_matrix_as_list[idx] > 0:
                child_rule_list.append(node_dictionary[node_id_dictionary[idx]])

        if or_out_dependency and not and_out_dependency:
            while child_rule_list:
                the_most_positive = TopologicalSort._find_the_most_positive(
                    child_rule_list, record_dictionary_of_nodes, dependency_matrix_as_list
                )
                if the_most_positive not in visited_node_list:
                    visited_node_list.append(the_most_positive)
                    TopologicalSort._visit(
                        the_most_positive, sorted_list, record_dictionary_of_nodes,
                        node_dictionary, node_id_dictionary,
                        visited_node_list, dependency_matrix,
                    )

        elif not or_out_dependency and and_out_dependency:
            while child_rule_list:
                the_most_negative = TopologicalSort._find_the_most_negative(
                    child_rule_list, record_dictionary_of_nodes, dependency_matrix_as_list
                )
                if the_most_negative not in visited_node_list:
                    visited_node_list.append(the_most_negative)
                    TopologicalSort._visit(
                        the_most_negative, sorted_list, record_dictionary_of_nodes,
                        node_dictionary, node_id_dictionary,
                        visited_node_list, dependency_matrix,
                    )

        return sorted_list

    @staticmethod
    def _find_the_most_positive(
        child_node_list: List[Node],
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
        dependency_matrix_as_list: Optional[List[int]] = None,
    ) -> Node:
        """
        Find the child node with the highest true rate.

        For OR rules, visiting the most-likely-TRUE child first gives
        the shortest path to a TRUE parent result.
        """
        the_most_positive: Optional[Node] = None
        best_rate = -1.0
        best_total = -1

        for node in child_node_list:
            record = TopologicalSort._lookup_record(
                node, record_dictionary_of_nodes, dependency_matrix_as_list
            )
            if record is not None:
                yes_count = record.true_count
                no_count = record.false_count
            else:
                yes_count = 0
                no_count = 0

            total = yes_count + no_count
            rate = yes_count / total if total > 0 else 0.0

            if TopologicalSort._is_better_choice(rate, best_rate, total, best_total):
                best_rate = rate
                best_total = total
                the_most_positive = node

        if the_most_positive is None and child_node_list:
            the_most_positive = child_node_list[0]

        for i in range(len(child_node_list)):
            if child_node_list[i].get_node_name() == the_most_positive.get_node_name():
                child_node_list.pop(i)
                break

        return the_most_positive

    @staticmethod
    def _find_the_most_negative(
        child_node_list: List[Node],
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
        dependency_matrix_as_list: Optional[List[int]] = None,
    ) -> Node:
        """
        Find the child node with the highest false rate.

        For AND rules, visiting the most-likely-FALSE child first gives
        the shortest path to a FALSE parent result.
        """
        the_most_negative: Optional[Node] = None
        best_rate = -1.0
        best_total = -1

        for node in child_node_list:
            record = TopologicalSort._lookup_record(
                node, record_dictionary_of_nodes, dependency_matrix_as_list
            )
            if record is not None:
                yes_count = record.true_count
                no_count = record.false_count
            else:
                yes_count = 0
                no_count = 0

            total = yes_count + no_count
            rate = no_count / total if total > 0 else 0.0

            if TopologicalSort._is_better_choice(rate, best_rate, total, best_total):
                best_rate = rate
                best_total = total
                the_most_negative = node

        if the_most_negative is None and child_node_list:
            the_most_negative = child_node_list[0]

        for i in range(len(child_node_list)):
            if child_node_list[i].get_node_name() == the_most_negative.get_node_name():
                child_node_list.pop(i)
                break

        return the_most_negative

    @staticmethod
    def _lookup_record(
        node: Node,
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
        dependency_matrix_as_list: Optional[List[int]] = None,
    ) -> Optional[HistoryRecord]:
        """
        Look up a node's HistoryRecord, handling dependency-type prefixes.

        For NOT/KNOWN dependencies, the record key is prefixed accordingly:
        - KNOWN: "known" + node_name
        - NOT: "not" + node_name
        - NOT|KNOWN: "not known" + node_name
        - Otherwise: node_name
        """
        if dependency_matrix_as_list is not None:
            prefix = ""
            dep_type = dependency_matrix_as_list[node.get_node_id()]
            known = DependencyType.get_known()
            not_dep = DependencyType.get_not()

            if (dep_type & known) == known and (dep_type & not_dep) == not_dep:
                prefix = "not known"
            elif (dep_type & known) == known:
                prefix = "known"
            elif (dep_type & not_dep) == not_dep:
                prefix = "not"

            return record_dictionary_of_nodes.get(prefix + node.get_node_name())

        return record_dictionary_of_nodes.get(node.get_node_name())

    @staticmethod
    def _is_better_choice(
        rate: float, best_rate: float, total: int, best_total: int,
    ) -> bool:
        """
        Decide whether the current node is a better traversal choice.

        Two criteria:
        1. Higher rate AND equal-or-more observations → clearly better
        2. Equal rate AND more observations → prefer the node with more data
        """
        if rate > best_rate and total >= best_total:
            return True

        if rate >= best_rate and rate == best_rate and total > best_total:
            return True

        if rate >= best_rate and best_rate < 0:
            return True

        return False

    @staticmethod
    def _filling_s_list(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        temp_list: List[Node],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
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
        number_of_incoming_edge = size_of_matrix - 1
        for second_index in range(size_of_matrix):
            if (node_index != second_index) and (dependency_matrix[second_index][node_index] == -1):
                number_of_incoming_edge = number_of_incoming_edge - 1
        return number_of_incoming_edge

    @staticmethod
    def _get_child_ids(dependency_matrix: List[List[Any]], node_id: int) -> List[int]:
        child_id_list: List[int] = list()
        for index in range(len(dependency_matrix)):
            if dependency_matrix[node_id][index] != -1:
                child_id_list.append(index)
        return child_id_list

    @staticmethod
    def _check_for_cycles(dependency_matrix: List[List[Any]], size_of_matrix: int) -> bool:
        check_dag = False
        for i in range(size_of_matrix):
            for j in range(size_of_matrix):
                if (i != j) and dependency_matrix[i][j] != -1:
                    check_dag = True
                    logger.error("dependency_matrix_not_dag", i=i, j=j)
                    break
        return check_dag
