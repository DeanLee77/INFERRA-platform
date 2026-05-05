from unittest.mock import MagicMock

from src.domain.nodes.dependency_matrix import DependencyMatrix
from src.domain.nodes.node_set import NodeSet


def _node(name, stable_id=None, node_id=None, dependencies=None):
    node = MagicMock()
    node.get_node_name.return_value = name
    node.get_stable_node_id.return_value = stable_id
    if node_id is not None:
        node._node_id = node_id
    if dependencies is not None:
        node._dependencies = dependencies
    return node


def test_set_dependency_matrix_ignores_unsupported_value():
    node_set = NodeSet()
    before = node_set.get_dependency_matrix()

    node_set.set_dependency_matrix(object())

    assert node_set.get_dependency_matrix() is before


def test_remove_node_from_graph_noops_when_graph_is_missing():
    node_set = NodeSet()
    node_set._NodeSet__graph = None

    node_set._remove_node_from_graph("missing")

    assert node_set.get_graph() is None


def test_remove_node_by_name_delegates_to_graph_remove_node_when_available():
    node_set = NodeSet()
    node = _node("x", stable_id="stable:x", node_id=3)
    graph = MagicMock()
    node_set.set_graph(graph)
    node_set.register_node(node)
    node_set.set_sorted_node_list([node])

    node_set.remove_node_by_name("x")

    graph.remove_node.assert_called_once_with("x")
    assert node_set.get_node_dictionary() == {}
    assert node_set.get_sorted_node_list() == []


def test_rebuild_dependency_groups_adds_node_dependency_metadata_to_graph():
    node_set = NodeSet()
    node = _node(
        "child",
        dependencies=[
            {"parent_name": "goal", "child_name": "child", "dep_type": 1},
            {"parent_name": "", "child_name": "ignored", "dep_type": 1},
            {"parent_name": "ignored", "child_name": "", "dep_type": 1},
        ],
    )
    node_set.set_node_dictionary({"child": node})

    node_set.rebuild_dependency_groups()

    graph = node_set.get_graph()
    assert graph.get_children_flat("goal") == ("child",)
    assert not graph.has_node("ignored")


def test_rebuild_dependency_groups_skips_nodes_without_dependency_metadata():
    node_set = NodeSet()
    node_set.set_node_dictionary({"x": _node("x")})

    node_set.rebuild_dependency_groups()

    assert node_set.get_graph().all_node_names() == set()


def test_derive_graph_from_matrix_noops_without_node_id_dictionary():
    node_set = NodeSet()
    original_graph = node_set.get_graph()
    node_set.set_dependency_matrix(DependencyMatrix([[0]]))
    node_set.set_node_id_dictionary({})

    node_set._derive_graph_from_matrix()

    assert node_set.get_graph() is original_graph
