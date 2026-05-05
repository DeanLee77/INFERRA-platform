"""
ML-Optimized Topological Sort Strategy Module.
Standalone class that accepts DependencyGraphPort + Dict[str, HistoryRecord]
and produces ML-optimized traversal order.

Phase 2.5 (WS-4): Replaces dfs_topological_sort_with_record() with a
graph-native implementation that uses the port API exclusively.

Key design: The strategy does NOT call node.get_node_id(). It uses
graph.get_child_groups() (primitive port API) and
graph.get_typed_child_groups() (domain convenience) for type-separated
traversal. Record keys are stable_id strings, matching the new node
identity model.
"""

from typing import Dict, Optional, Tuple

from src.domain.graph.dependency_type import DependencyType
from src.domain.nodes.record import HistoryRecord
from src.ports.dependency_graph_port import DependencyGraphPort
from src.shared.loggers import Logger

_logger: Logger = Logger.get_logger(__name__)


class MLTopologicalSortStrategy:
    """
    ML-optimized topological sort using HistoryRecord data.

    For OR children: visit most-likely-TRUE first.
    For AND children: visit most-likely-FALSE first.
    Mixed children: OR first (most-TRUE), then AND (most-FALSE).
    Falls back to standard topological_sort() when no records available.
    """

    def __init__(self, graph: DependencyGraphPort):
        self._graph = graph

    def sort(self, records: Optional[Dict[str, HistoryRecord]] = None) -> Tuple[str, ...]:
        """
        Produce ML-optimized topological order.

        Args:
            records: Optional dict mapping node_name -> HistoryRecord.
                When None, falls back to standard topological_sort().

        Returns:
            Tuple of node names in ML-optimized topological order
        """
        if records is None or len(records) == 0:
            return self._graph.topological_sort()

        base_order = self._graph.topological_sort()
        if not base_order:
            return ()

        reordered: list = []
        placed: set = set()

        in_degree: Dict[str, int] = {}
        for name in base_order:
            parents = self._graph.get_parent_edges(name)
            in_degree[name] = len([p for p in parents if p in set(base_order)])

        available = [n for n in base_order if in_degree.get(n, 0) == 0]
        self._sort_available(available, records)

        while available:
            node = available.pop(0)
            if node in placed:
                continue
            placed.add(node)
            reordered.append(node)

            for dep_type, children in self._graph.get_child_groups(node):
                for child in children:
                    if child in in_degree:
                        in_degree[child] -= 1
                        if in_degree[child] == 0 and child not in placed:
                            available.append(child)

            self._sort_available(available, records)

        return tuple(reordered)

    def _sort_available(self, available: list, records: Dict[str, HistoryRecord]) -> None:
        """Sort available nodes by ML heuristics: OR→most-TRUE, AND→most-FALSE."""
        def _score(name: str) -> float:
            record = records.get(name)
            if record is None:
                return 0.0
            return record.true_rate

        def _key(name: str) -> float:
            has_or = self._graph.has_children_of_type(name, int(DependencyType.OR))
            has_and = self._graph.has_children_of_type(name, int(DependencyType.AND))

            if has_or and not has_and:
                return -_score(name)
            elif has_and and not has_or:
                return _score(name)
            elif has_or and has_and:
                return -_score(name)
            return 0.0

        available.sort(key=_key)
