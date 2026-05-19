"""Compatibility shim for graph-owned DependencyMatrix."""

import warnings

from src.domain.graph.dependency_matrix import DependencyMatrix

warnings.warn(
    "src.domain.nodes.dependency_matrix is deprecated; import "
    "src.domain.graph.dependency_matrix only inside sanctioned legacy adapters/tests.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DependencyMatrix"]
