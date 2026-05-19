"""Domain graph package: HyperAdjacencyGraph, matrix bridges, and edge types."""

from src.domain.graph.dependency import Dependency
from src.domain.graph.dependency_group import DependencyGroup
from src.domain.graph.dependency_matrix import DependencyMatrix
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import CyclicGraphError, HyperAdjacencyGraph
from src.domain.graph.inference_propagator import IncrementalPropagator
from src.domain.graph.matrix_to_hyper_adapter import MatrixToHyperGraphAdapter

__all__ = [
    "Dependency",
    "DependencyGroup",
    "DependencyMatrix",
    "DependencyType",
    "CyclicGraphError",
    "HyperAdjacencyGraph",
    "IncrementalPropagator",
    "MatrixToHyperGraphAdapter",
]
