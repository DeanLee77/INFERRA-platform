import importlib
import sys
import warnings

from src.domain.graph.dependency import Dependency
from src.domain.graph.dependency_matrix import DependencyMatrix
from src.domain.graph.dependency_type import DependencyType


def test_node_dependency_matrix_shim_points_to_graph_matrix():
    from src.domain.nodes.dependency_matrix import DependencyMatrix as NodeDependencyMatrix

    assert NodeDependencyMatrix is DependencyMatrix


def test_node_dependency_matrix_shim_emits_deprecation_warning():
    sys.modules.pop("src.domain.nodes.dependency_matrix", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("src.domain.nodes.dependency_matrix")

    assert any(
        issubclass(item.category, DeprecationWarning)
        and "src.domain.nodes.dependency_matrix is deprecated" in str(item.message)
        for item in caught
    )


def test_node_dependency_shim_points_to_graph_dependency():
    from src.domain.nodes.dependency import Dependency as NodeDependency

    assert NodeDependency is Dependency


def test_node_dependency_type_shim_points_to_graph_dependency_type():
    from src.domain.nodes.dependency_type import DependencyType as NodeDependencyType

    assert NodeDependencyType is DependencyType
