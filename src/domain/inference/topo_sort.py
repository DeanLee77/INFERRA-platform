"""Deprecated compatibility facade for rule-set topological ordering.

Runtime traversal is graph-native. New code should use
``MLTopologicalSortStrategy`` with a ``DependencyGraphPort`` directly.

This module exists only to bridge legacy callers that still pass a dense
matrix-like payload plus ``node_id_dictionary``. The facade immediately adapts
that payload to ``HyperAdjacencyGraph`` and delegates all ordering logic to
``MLTopologicalSortStrategy``.
"""

import warnings
from typing import Any, Dict, List

import structlog

from src.domain.graph.matrix_to_hyper_adapter import MatrixToHyperGraphAdapter
from src.domain.graph.ml_topological_sort_strategy import MLTopologicalSortStrategy
from src.domain.nodes.node import Node
from src.domain.nodes.record import HistoryRecord
from src.ports.dependency_graph_port import DependencyGraphPort

logger = structlog.get_logger(__name__)


class TopologicalSort:
    """Compatibility wrapper around graph-native topology strategies."""

    @staticmethod
    def bfs_topological_sort(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """Adapt legacy matrix inputs and return graph topological order."""
        TopologicalSort._warn_legacy_matrix_entrypoint("bfs_topological_sort")
        graph = TopologicalSort._graph_from_legacy_inputs(
            node_id_dictionary,
            dependency_matrix,
        )
        return TopologicalSort.bfs_graph_topological_sort(node_dictionary, graph)

    @staticmethod
    def bfs_graph_topological_sort(
        node_dictionary: Dict[str, Node],
        graph: DependencyGraphPort,
    ) -> List[Node]:
        """Return nodes in graph-native topological order."""
        strategy = MLTopologicalSortStrategy(graph)
        return list(strategy.sort_items(node_dictionary))

    @staticmethod
    def dfs_topological_sort(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> List[Node]:
        """Adapt legacy matrix inputs and return graph-native DFS order."""
        TopologicalSort._warn_legacy_matrix_entrypoint("dfs_topological_sort")
        graph = TopologicalSort._graph_from_legacy_inputs(
            node_id_dictionary,
            dependency_matrix,
        )
        return TopologicalSort.dfs_graph_topological_sort(node_dictionary, graph)

    @staticmethod
    def dfs_graph_topological_sort(
        node_dictionary: Dict[str, Node],
        graph: DependencyGraphPort,
    ) -> List[Node]:
        """Return nodes in graph-native deterministic DFS order."""
        strategy = MLTopologicalSortStrategy(graph)
        return list(strategy.sort_items_depth_first(node_dictionary))

    @staticmethod
    def dfs_topological_sort_with_record(
        node_dictionary: Dict[str, Node],
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
    ) -> List[Node]:
        """Adapt legacy matrix inputs and return HistoryRecord-optimized DFS."""
        TopologicalSort._warn_legacy_matrix_entrypoint(
            "dfs_topological_sort_with_record"
        )
        graph = TopologicalSort._graph_from_legacy_inputs(
            node_id_dictionary,
            dependency_matrix,
        )
        return TopologicalSort.dfs_graph_topological_sort_with_record(
            node_dictionary,
            graph,
            record_dictionary_of_nodes,
        )

    @staticmethod
    def dfs_graph_topological_sort_with_record(
        node_dictionary: Dict[str, Node],
        graph: DependencyGraphPort,
        record_dictionary_of_nodes: Dict[str, HistoryRecord],
    ) -> List[Node]:
        """Return nodes in graph-native HistoryRecord-optimized DFS order."""
        strategy = MLTopologicalSortStrategy(graph)
        return list(
            strategy.sort_items_depth_first(
                node_dictionary,
                record_dictionary_of_nodes,
            )
        )

    @staticmethod
    def _graph_from_legacy_inputs(
        node_id_dictionary: Dict[int, str],
        dependency_matrix: List[List[Any]],
    ) -> DependencyGraphPort:
        return MatrixToHyperGraphAdapter.from_legacy_list(
            dependency_matrix,
            node_id_dictionary,
        )

    @staticmethod
    def _warn_legacy_matrix_entrypoint(method_name: str) -> None:
        warnings.warn(
            (
                f"TopologicalSort.{method_name}() is deprecated; build a "
                "DependencyGraphPort and use MLTopologicalSortStrategy instead."
            ),
            DeprecationWarning,
            stacklevel=3,
        )
        logger.info("legacy_matrix_topo_sort_adapter_used", topo_method=method_name)
