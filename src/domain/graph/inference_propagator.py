"""
Incremental Propagator Module.

Replaces the legacy full-matrix-scan back-propagation with targeted BFS
over the HyperAdjacencyGraph. Only impacted nodes are re-evaluated.

Delegates BFS traversal to Phase 1's cycle-guarded graph.back_propagate().
Uses primitive DependencyGraphPort API (not get_typed_child_groups()).
"""

import graphlib
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

import structlog

from src.domain.fact_values import FactValue
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import CyclicGraphError
from src.domain.state.fact_source import FactSource
from src.ports.dependency_graph_port import DependencyGraphPort
from src.ports.fact_store_port import FactStorePort

log = structlog.get_logger()


class IncrementalPropagator:
    """
    Queue-based incremental forward propagation.

    Given a set of changed nodes, computes the impacted subgraph via
    back_propagate(), topo-sorts it, then evaluates only those nodes
    whose dependencies are satisfied.
    """

    def __init__(self, graph: DependencyGraphPort, fact_store: FactStorePort):
        self._graph = graph
        self._store = fact_store
        self._topo_cache: Dict[frozenset, Tuple[str, ...]] = {}

    def forward_propagate_incremental(self, changed_node_ids: Set[str]) -> None:
        """
        Incremental forward propagation using impacted-subgraph BFS.

        Delegates BFS to Phase 1's cycle-guarded graph.back_propagate(),
        then topo-sorts + evaluates only the impacted subgraph.

        Args:
            changed_node_ids: Set of node names whose values changed
        """
        if not changed_node_ids:
            return

        impacted_ordered = self._compute_impacted_subgraph(changed_node_ids)
        if not impacted_ordered:
            return

        log.info(
            "forward_propagation_start",
            impacted_count=len(impacted_ordered),
        )

        impacted_set = set(impacted_ordered)
        sub_children = {
            n: self._graph.get_child_groups(n) for n in impacted_set
        }
        ordered = self._topo_sort_subgraph(impacted_set, sub_children)

        evaluated = 0
        for nid in ordered:
            if self._can_evaluate_parent(nid):
                self._evaluate_and_store(nid)
                evaluated += 1

        log.info(
            "forward_propagation_complete",
            evaluated_count=evaluated,
            total_impacted=len(impacted_set),
        )

    def _compute_impacted_subgraph(
        self, changed_node_ids: Set[str]
    ) -> Deque[str]:
        """
        Compute impacted nodes by delegating BFS to graph.back_propagate().

        Aggregates results from all changed nodes and deduplicates while
        preserving BFS visit order.

        Args:
            changed_node_ids: Set of node names that changed

        Returns:
            Deque of impacted parent node names in BFS visit order

        Raises:
            CyclicGraphError: If graph.back_propagate() detects a cycle
        """
        seen: Set[str] = set()
        result: Deque[str] = deque()

        for node_id in changed_node_ids:
            if not self._graph.has_node(node_id):
                continue
            parents = self._graph.back_propagate(node_id)
            for p in parents:
                if p not in seen:
                    seen.add(p)
                    result.append(p)

        return result

    def _topo_sort_subgraph(
        self,
        node_ids: Set[str],
        child_map: Dict[str, Tuple[Tuple[int, Tuple[str, ...]], ...]],
    ) -> List[str]:
        """
        Topologically sort an impacted subgraph using graphlib.TopologicalSorter.

        Only considers edges within the subgraph — external dependencies
        are ignored. Uses primitive port API: child_map values are
        (dep_type_int, children_tuple) tuples.

        Args:
            node_ids: Set of node names in the subgraph
            child_map: Mapping of node name → child groups (primitive tuples)

        Returns:
            List of node names in topological order

        Raises:
            graphlib.CycleError: If the subgraph contains a cycle
        """
        if not node_ids:
            return []

        cache_key = frozenset(node_ids)
        if cache_key in self._topo_cache:
            return list(self._topo_cache[cache_key])

        sorter = graphlib.TopologicalSorter()
        for nid in node_ids:
            sorter.add(nid)
            for _dep_type_int, children_tuple in child_map.get(nid, ()):
                for child in children_tuple:
                    if child in node_ids:
                        sorter.add(nid, child)

        result = tuple(sorter.static_order())
        self._topo_cache[cache_key] = result
        return list(result)

    def invalidate_cache(self) -> None:
        """Clear the topological sort cache (call after graph mutations)."""
        self._topo_cache.clear()

    def _can_evaluate_parent(self, parent_id: str) -> bool:
        """
        Check whether all dependencies for a parent node are satisfied.

        Uses primitive port API: get_child_groups() returns
        (dep_type_int, children_tuple) tuples.

        Args:
            parent_id: Node name to check

        Returns:
            True if all required dependencies are in working memory
        """
        wm = self._store.get_unified_view()
        for dep_type_int, children_tuple in self._graph.get_child_groups(
            parent_id
        ):
            if dep_type_int & DependencyType.AND:
                if not all(c in wm for c in children_tuple):
                    return False
            elif dep_type_int & DependencyType.OR:
                if not any(c in wm for c in children_tuple):
                    return False
        return True

    def _evaluate_and_store(self, node_id: str) -> None:
        """
        Evaluate a node and store the result as INFERRED.

        Args:
            node_id: Node name to evaluate (used as fact key per Phase 1 convention)
        """
        value = self._compute_node_value(node_id)
        self._store.set_fact(node_id, value, source=FactSource.INFERRED)

    def _compute_node_value(self, node_id: str) -> FactValue:
        """
        Compute the truth value for a node from its children.

        For AND groups: all children must be True.
        For OR groups: at least one child must be True.

        Args:
            node_id: Node name to compute

        Returns:
            FactValue with the computed boolean result
        """
        wm = self._store.get_unified_view()
        for dep_type_int, children_tuple in self._graph.get_child_groups(
            node_id
        ):
            child_values = [
                bool(wm[c].get_value()) for c in children_tuple if c in wm
            ]
            if dep_type_int & DependencyType.AND:
                if child_values and all(child_values):
                    return FactValue(True)
            elif dep_type_int & DependencyType.OR:
                if child_values and any(child_values):
                    return FactValue(True)
        return FactValue(False)
