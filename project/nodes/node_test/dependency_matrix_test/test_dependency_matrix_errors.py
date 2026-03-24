import pytest

from project.nodes.dependency_matrix import DependencyMatrix


def test_get_to_child_dependency_list_raises_for_invalid_node_id():
    matrix = DependencyMatrix([[-1]])

    with pytest.raises(IndexError):
        matrix.get_to_child_dependency_list(2)


def test_get_dependency_type_raises_for_negative_index():
    matrix = DependencyMatrix([[-1]])

    with pytest.raises(IndexError):
        matrix.get_dependency_type(-1, 0)
