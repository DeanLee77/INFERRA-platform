"""
ML-Optimized Topological Sort Strategy Module.

Standalone class that accepts DependencyGraphPort + Dict[str, HistoryRecord]
and produces ML-optimized traversal order.

Phase 2.5: graph-native implementation using the primitive port API only.
Record keys are canonical node-name graph keys, not runtime integer IDs or
stable IDs.
"""

import heapq
from typing import Dict, Iterable, Mapping, Optional, Tuple, TypeVar

from src.domain.graph.dependency_type import DependencyType
from src.domain.nodes.node_id_utils import unqualified_node_key
from src.domain.nodes.record import HistoryRecord
from src.infrastructure.logging_config import get_logger
from src.ports.dependency_graph_port import DependencyGraphPort

_logger = get_logger(__name__)
T = TypeVar("T")
_AND_MASK = int(DependencyType.AND)
_KNOWN_MASK = int(DependencyType.KNOWN)
_NOT_MASK = int(DependencyType.NOT)
_OR_MASK = int(DependencyType.OR)


class MLTopologicalSortStrategy:
    """
    ML-optimized topological sort using HistoryRecord data.

    For OR children: visit most-likely-TRUE first.
    For AND children: visit most-likely-FALSE first.
    ``sort()`` preserves topological validity and applies the releasing edge's
    dependency type once a child becomes available.

    ``sort_depth_first()`` preserves the legacy TopologicalSort DFS behavior:
    parent first, then recursively visit history-prioritized children.
    """

    def __init__(self, graph: DependencyGraphPort):
        self._graph = graph

    def sort(self, records: Optional[Dict[str, HistoryRecord]] = None) -> Tuple[str, ...]:
        """
        Produce ML-optimized topological order.

        Args:
            records: Optional dict mapping canonical node key -> HistoryRecord.
                When None or empty, falls back to standard topological_sort().

        Returns:
            Tuple of node names in ML-optimized topological order.
        """
        if records is None or len(records) == 0:
            return self._graph.topological_sort()

        base_order = self._graph.topological_sort()
        if not base_order:
            return ()

        in_degree = self._in_degree_for(base_order)

        reordered: list = []
        placed: set = set()
        available: list[Tuple[Tuple[float, int, str], str]] = []
        key_cache: Dict[Tuple[str, int], Tuple[float, int, str]] = {}
        for name in base_order:
            if in_degree.get(name, 0) == 0:
                heapq.heappush(
                    available,
                    (self._availability_key_cached(name, 0, records, key_cache), name),
                )

        while available:
            _, node = heapq.heappop(available)
            if node in placed:
                continue
            placed.add(node)
            reordered.append(node)

            for dep_type, children in self._graph.get_child_groups(node):
                for child in self._sort_children(children, dep_type, records, key_cache):
                    if child in in_degree:
                        in_degree[child] -= 1
                        if in_degree[child] == 0 and child not in placed:
                            heapq.heappush(
                                available,
                                (
                                    self._availability_key_cached(
                                        child,
                                        dep_type,
                                        records,
                                        key_cache,
                                    ),
                                    child,
                                ),
                            )

        return tuple(reordered)

    def sort_depth_first(
        self,
        records: Optional[Dict[str, HistoryRecord]] = None,
    ) -> Tuple[str, ...]:
        """
        Produce legacy-compatible DFS order with optional HistoryRecord child
        ordering.

        This is intentionally different from :meth:`sort`: it is a traversal
        order optimized for asking/evaluating likely-pruning paths, not a
        strict topological ordering for graphs with shared descendants.
        """
        records = records or {}

        base_order = self._graph.topological_sort()
        if not base_order:
            return ()

        in_degree = self._in_degree_for(base_order)
        roots = [
            name for name in base_order
            if in_degree.get(name, 0) == 0
        ]

        result: list = []
        visited: set = set()
        key_cache: Dict[Tuple[str, int], Tuple[float, int, str]] = {}
        for root in roots:
            self._visit_depth_first(root, records, visited, result, key_cache)
        return tuple(result)

    def sort_items(
        self,
        items_by_key: Mapping[str, T],
        records: Optional[Dict[str, HistoryRecord]] = None,
    ) -> Tuple[T, ...]:
        """Return mapped items in graph topological order."""
        return self.items_for_order(items_by_key, self.sort(records))

    def sort_items_depth_first(
        self,
        items_by_key: Mapping[str, T],
        records: Optional[Dict[str, HistoryRecord]] = None,
    ) -> Tuple[T, ...]:
        """Return mapped items in graph-native DFS order."""
        return self.items_for_order(items_by_key, self.sort_depth_first(records))

    @staticmethod
    def items_for_order(
        items_by_key: Mapping[str, T],
        order: Iterable[str],
    ) -> Tuple[T, ...]:
        """Resolve canonical graph keys to caller-owned items.

        Imported graph keys may be qualified while legacy node dictionaries may
        still be keyed by raw node name. The unqualified fallback keeps that
        bridge outside the traversal algorithms.
        """
        result: list[T] = []
        for key in order:
            item = items_by_key.get(key)
            if item is None:
                item = items_by_key.get(unqualified_node_key(key))
            if item is not None:
                result.append(item)
        return tuple(result)

    def _visit_depth_first(
        self,
        node: str,
        records: Dict[str, HistoryRecord],
        visited: set,
        result: list,
        key_cache: Dict[Tuple[str, int], Tuple[float, int, str]],
    ) -> None:
        stack = [node]
        while stack:
            current = stack.pop()
            if current in visited:
                continue

            visited.add(current)
            result.append(current)

            next_children: list[str] = []
            for dep_type, children in self._ordered_child_groups(current):
                next_children.extend(
                    self._sort_children(children, dep_type, records, key_cache)
                )

            for child in reversed(next_children):
                if child not in visited:
                    stack.append(child)

    def _in_degree_for(self, base_order: Tuple[str, ...]) -> Dict[str, int]:
        base_set = set(base_order)
        in_degree: Dict[str, int] = {name: 0 for name in base_order}
        edges = getattr(self._graph, "edges", None)
        if callable(edges):
            for parent, child, _ in edges():
                if parent in base_set and child in in_degree:
                    in_degree[child] += 1
            return in_degree

        for name in base_order:
            in_degree[name] = sum(
                1 for parent in self._graph.get_parent_edges(name)
                if parent in base_set
            )
        return in_degree

    def _availability_key(
        self,
        name: str,
        dep_type: int,
        records: Dict[str, HistoryRecord],
    ) -> Tuple[float, int, str]:
        record = self._lookup_record(name, dep_type, records)
        true_rate = record.true_rate if record is not None else 0.0
        false_rate = record.false_rate if record is not None else 0.0
        total = record.total if record is not None else 0

        if dep_type & _OR_MASK == _OR_MASK:
            return (-true_rate, -total, name)
        if dep_type & _AND_MASK == _AND_MASK:
            return (-false_rate, -total, name)
        return (0.0, 0, name)

    def _availability_key_cached(
        self,
        name: str,
        dep_type: int,
        records: Dict[str, HistoryRecord],
        key_cache: Dict[Tuple[str, int], Tuple[float, int, str]],
    ) -> Tuple[float, int, str]:
        cache_key = (name, dep_type)
        cached = key_cache.get(cache_key)
        if cached is None:
            cached = self._availability_key(name, dep_type, records)
            key_cache[cache_key] = cached
        return cached

    def _ordered_child_groups(
        self,
        node: str,
    ) -> Tuple[Tuple[int, Tuple[str, ...]], ...]:
        def _group_rank(group: Tuple[int, Tuple[str, ...]]) -> Tuple[int, str]:
            dep_type, children = group
            if dep_type & _OR_MASK == _OR_MASK:
                return (0, min(children, default=""))
            if dep_type & _AND_MASK == _AND_MASK:
                return (1, min(children, default=""))
            return (2, min(children, default=""))

        return tuple(sorted(self._graph.get_child_groups(node), key=_group_rank))

    def _sort_children(
        self,
        children: Tuple[str, ...],
        dep_type: int,
        records: Dict[str, HistoryRecord],
        key_cache: Dict[Tuple[str, int], Tuple[float, int, str]],
    ) -> Tuple[str, ...]:
        return tuple(
            sorted(
                children,
                key=lambda name: self._availability_key_cached(
                    name,
                    dep_type,
                    records,
                    key_cache,
                ),
            )
        )

    def _lookup_record(
        self,
        name: str,
        dep_type: int,
        records: Dict[str, HistoryRecord],
    ) -> Optional[HistoryRecord]:
        if dep_type & _KNOWN_MASK == _KNOWN_MASK and dep_type & _NOT_MASK == _NOT_MASK:
            return records.get(f"not known{name}") or records.get(name)
        if dep_type & _KNOWN_MASK == _KNOWN_MASK:
            return records.get(f"known{name}") or records.get(name)
        if dep_type & _NOT_MASK == _NOT_MASK:
            return records.get(f"not{name}") or records.get(name)
        return records.get(name)
