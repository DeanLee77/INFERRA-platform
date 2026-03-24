# nodes/dependency_builder.py
from typing import List

from project.nodes import Node, Dependency, DependencyMatrix


class DependencyBuilder:
    """
    Collects parent-child dependency relationships during parsing
    and builds the final DependencyMatrix.

    Reduces size and complexity of RuleSetParser and NodeSet.
    """

    def __init__(self):
        self._dependencies: List[Dependency] = []

    def add(self, parent: Node, child: Node, dep_type: int) -> None:
        """Record one dependency relationship"""
        self._dependencies.append(Dependency(parent, child, dep_type))

    def build_matrix(self, total_nodes: int) -> DependencyMatrix:
        """Convert collected dependencies into matrix format"""
        matrix = [[-1 for _ in range(total_nodes)] for _ in range(total_nodes)]

        for dep in self._dependencies:
            p_id = dep.get_parent_node().get_node_id()
            c_id = dep.get_child_node().get_node_id()
            if 0 <= p_id < total_nodes and 0 <= c_id < total_nodes:
                matrix[p_id][c_id] = dep.get_dependency_type()

        return DependencyMatrix(matrix)

    def get_all_dependencies(self) -> List[Dependency]:
        """For debugging / inspection"""
        return self._dependencies.copy()