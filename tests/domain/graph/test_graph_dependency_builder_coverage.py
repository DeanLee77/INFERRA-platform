from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.graph_dependency_builder import GraphDependencyBuilder
class _Node:
    def __init__(self, name, node_id=None):
        self._name = name
        self._node_id = node_id

    def get_node_name(self):
        return self._name


def test_register_node_tracks_bidirectional_maps_and_graph_metadata():
    builder = GraphDependencyBuilder()

    builder.register_node(7, "income", {"stable_id": "rule:income"})

    assert builder.get_id_to_name_map() == {7: "income"}
    assert builder.get_name_to_id_map() == {"income": 7}
    assert builder.graph.has_node("income")


def test_add_dependency_uses_registered_names():
    builder = GraphDependencyBuilder()
    builder.register_node(1, "parent")
    builder.register_node(2, "child")

    builder.add_dependency(1, 2, int(DependencyType.AND))

    assert builder.graph.get_children_flat("parent") == ("child",)


def test_add_dependency_falls_back_to_synthetic_names_for_unknown_ids():
    builder = GraphDependencyBuilder()

    builder.add_dependency(100, 200, int(DependencyType.OR))

    assert builder.graph.get_children_flat("__node_100__") == ("__node_200__",)


def test_add_dependencies_from_nodes_uses_registered_ids_when_available():
    builder = GraphDependencyBuilder()
    parent = _Node("parent")
    child = _Node("child")
    builder.register_node(1, "parent")
    builder.register_node(2, "child")

    builder.add_dependencies_from_nodes(parent, child, int(DependencyType.AND))

    assert builder.get_id_to_name_map()[1] == "parent"
    assert builder.get_id_to_name_map()[2] == "child"
    assert builder.graph.get_children_flat("parent") == ("child",)


def test_add_dependencies_from_nodes_falls_back_to_node_private_ids():
    builder = GraphDependencyBuilder()
    parent = _Node("parent", 10)
    child = _Node("child", 11)

    builder.add_dependencies_from_nodes(parent, child, int(DependencyType.AND))

    assert builder.get_id_to_name_map()[10] == "parent"
    assert builder.get_id_to_name_map()[11] == "child"
    assert builder.graph.get_children_flat("parent") == ("child",)


def test_add_dependencies_from_nodes_without_ids_still_builds_graph():
    builder = GraphDependencyBuilder()
    parent = _Node("parent")
    child = _Node("child")

    builder.add_dependencies_from_nodes(parent, child, int(DependencyType.AND))

    assert builder.get_name_to_id_map() == {"parent": -1, "child": -1}
    assert builder.graph.get_children_flat("parent") == ("child",)
