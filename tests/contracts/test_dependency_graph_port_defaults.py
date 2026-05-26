from collections import deque
from typing import Iterator, Set, Tuple

from src.ports.dependency_graph_port import DependencyGraphPort


class _DefaultGraph(DependencyGraphPort):
    def __init__(self):
        self.groups = {}
        self.nodes = set()

    def add_dependency_group(self, parent: str, dep_type: int, children: Set[str]) -> None:
        self.nodes.add(parent)
        self.nodes.update(children)
        self.groups.setdefault(parent, []).append((dep_type, tuple(sorted(children))))

    def get_parent_edges(self, node_name: str) -> Set[str]:
        return {
            parent
            for parent, groups in self.groups.items()
            for _, children in groups
            if node_name in children
        }

    def get_child_groups(self, node_name: str) -> Tuple[Tuple[int, Tuple[str, ...]], ...]:
        return tuple(self.groups.get(node_name, ()))

    def back_propagate(self, changed_node: str, max_steps: int = 0):
        return deque(self.get_parent_edges(changed_node))

    def topological_sort(self) -> Tuple[str, ...]:
        return tuple(sorted(self.nodes))

    def all_node_names(self) -> Set[str]:
        return set(self.nodes)

    def has_node(self, node_name: str) -> bool:
        return node_name in self.nodes

    def register_node(self, name: str, metadata=None) -> int:
        self.nodes.add(name)
        return len(self.nodes) - 1

    def edges(self) -> Iterator[Tuple[str, str, int]]:
        for parent, groups in self.groups.items():
            for dep_type, children in groups:
                for child in children:
                    yield parent, child, dep_type


def test_dependency_graph_port_default_child_queries():
    graph = _DefaultGraph()
    graph.add_dependency_group("goal", 1, {"a", "b"})
    graph.add_dependency_group("goal", 3, {"c"})

    assert graph.get_children_by_type("goal", 1) == ("a", "b", "c")
    assert graph.get_children_by_type("goal", 3) == ("c",)
    assert graph.get_children_flat("goal") == ("a", "b", "c")
    assert graph.get_dependency_type("goal", "b") == 1
    assert graph.get_dependency_type("goal", "missing") == -1
    assert graph.has_children_of_type("goal", 1) is True
    assert graph.has_children_of_type("goal", 4) is False


def test_dependency_graph_port_default_subgraph_preserves_internal_edges_only():
    graph = _DefaultGraph()
    graph.add_dependency_group("goal", 1, {"a", "b"})
    graph.add_dependency_group("a", 1, {"leaf"})

    subgraph = graph.subgraph({"goal", "a"})

    assert isinstance(subgraph, _DefaultGraph)
    assert subgraph.get_children_flat("goal") == ("a",)
    assert subgraph.get_children_flat("a") == ()
    assert subgraph.lookup_by_id(1) is None
    assert subgraph.lookup_by_name("goal") is None
