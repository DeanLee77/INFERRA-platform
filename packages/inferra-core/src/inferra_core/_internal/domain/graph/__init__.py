"""Private graph implementation without legacy matrix exports."""

from .dependency import Dependency
from .graph_dependency_builder import GraphDependencyBuilder
from .hyper_adjacency_graph import CyclicGraphError, HyperAdjacencyGraph

__all__ = [
    "CyclicGraphError",
    "Dependency",
    "GraphDependencyBuilder",
    "HyperAdjacencyGraph",
]

