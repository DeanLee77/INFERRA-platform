"""
Graph-to-Matrix Adapter Module.
Derives a DependencyMatrix on demand from a HyperAdjacencyGraph.

Reverse of Phase 1's MatrixToHyperGraphAdapter. Used during transition
for legacy consumers that still require matrix access (e.g., old tests,
legacy session loading). The matrix is NOT stored — it is reconstructed
each time.

Phase 2.5 (WS-3): One-way bridge from graph to matrix.
"""

from typing import Dict, Iterator, List, Optional, Tuple

from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.nodes.dependency_matrix import DependencyMatrix


class GraphToMatrixAdapter(DependencyMatrix):
    """
    Derives a DependencyMatrix from a HyperAdjacencyGraph on demand.

    The matrix is NOT stored — it is reconstructed each time from the
    graph's edge types and node ID mappings. This avoids data drift
    between the two representations.
    """

    def __init__(self, graph: HyperAdjacencyGraph) -> None:
        self._graph = graph
        self._matrix_cache: Optional[List[List[int]]] = None
        self._id_map: Optional[Dict[int, str]] = None

    def _rebuild(self) -> None:
        all_names = self._graph.all_node_names()
        name_to_id: Dict[str, int] = {}
        id_to_name: Dict[int, str] = {}

        for name in sorted(all_names):
            rid = self._graph.lookup_by_name(name)
            if rid is None:
                rid = len(name_to_id)
            name_to_id[name] = rid
            id_to_name[rid] = name

        n = max(list(name_to_id.values()) + [-1]) + 1 if name_to_id else 0
        if n == 0:
            self._matrix_cache = [[]]
            self._id_map = id_to_name
            return

        matrix = [[-1] * n for _ in range(n)]
        for parent, child, dep_type in self._graph.edges():
            pid = name_to_id.get(parent)
            cid = name_to_id.get(child)
            if pid is not None and cid is not None and pid < n and cid < n:
                existing = matrix[pid][cid]
                matrix[pid][cid] = existing | dep_type if existing != -1 else dep_type

        self._matrix_cache = matrix
        self._id_map = id_to_name

    def get_dependency_two_dimension_list(self) -> List[List[int]]:
        self._rebuild()
        return self._matrix_cache

    def get_node_id_dictionary(self) -> Dict[int, str]:
        self._rebuild()
        return self._id_map

    def _matrix(self) -> DependencyMatrix:
        self._rebuild()
        return DependencyMatrix(self._matrix_cache)

    def get_dependency_type(self, parent_rule_id: int, child_rule_id: int) -> int:
        return self._matrix().get_dependency_type(parent_rule_id, child_rule_id)

    def get_to_child_dependency_list(self, node_id: int) -> List[int]:
        return self._matrix().get_to_child_dependency_list(node_id)

    def get_or_to_child_dependency_list(self, node_id: int) -> List[int]:
        return self._matrix().get_or_to_child_dependency_list(node_id)

    def get_and_to_child_dependency_list(self, node_id: int) -> List[int]:
        return self._matrix().get_and_to_child_dependency_list(node_id)

    def get_mandatory_to_child_dependency_list(self, node_id: int) -> List[int]:
        return self._matrix().get_mandatory_to_child_dependency_list(node_id)

    def get_from_parent_dependency_list(self, node_id: int) -> List[int]:
        return self._matrix().get_from_parent_dependency_list(node_id)

    def has_mandatory_child_node(self, node_id: int) -> bool:
        return self._matrix().has_mandatory_child_node(node_id)

    def sparse_items(self) -> Iterator[Tuple[Tuple[int, int], int]]:
        yield from self._matrix().sparse_items()
