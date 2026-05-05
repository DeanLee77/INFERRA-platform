from __future__ import annotations

from src.domain.fact_values import FactValue
from src.domain.nodes.dependency_type import DependencyType
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.rule_parser.rule_set_parser import RuleSetParser


class DummyNode(Node):
    def __init__(self, node_id: int, node_name: str, variable_name: str, line_number: int):
        super().__init__(id=node_id)
        self._node_name = node_name
        self._variable_name = variable_name
        self._line_type = LineType.VALUE_CONCLUSION
        self._node_line = line_number

    def initialisation(self, parent_text: str, tokens) -> None:
        pass

    def get_line_type(self) -> LineType:
        return self._line_type

    def self_evaluate(self, working_memory: dict) -> FactValue:
        return FactValue(True)


def test_stable_node_id_is_deterministic_for_same_context():
    left = DummyNode(0, "applicant is eligible", "applicant is eligible", 12)
    right = DummyNode(0, "applicant is eligible", "applicant is eligible", 12)

    left.refresh_stable_node_id("Eligibility Module")
    right.refresh_stable_node_id("Eligibility Module")

    assert left.get_stable_node_id() == right.get_stable_node_id()


def test_stable_node_id_changes_when_module_changes():
    left = DummyNode(0, "applicant is eligible", "applicant is eligible", 12)
    right = DummyNode(0, "applicant is eligible", "applicant is eligible", 12)

    left.refresh_stable_node_id("Eligibility Module")
    right.refresh_stable_node_id("Assessment Module")

    assert left.get_stable_node_id() != right.get_stable_node_id()


def test_node_set_registers_runtime_and_stable_ids():
    node = DummyNode(4, "applicant is eligible", "applicant is eligible", 8)
    node.refresh_stable_node_id("Eligibility Module")

    node_set = NodeSet()
    node_set.register_node(node)

    assert node_set.get_node_by_node_id(4) is node
    assert node_set.get_node_by_stable_node_id(node.get_stable_node_id()) is node
    assert node_set.get_next_node_id() == 5


def test_rule_set_parser_sizes_dependency_matrix_from_runtime_ids_not_static_counter():
    parent = DummyNode(3, "parent rule", "parent rule", 10)
    child = DummyNode(5, "child rule", "child rule", 11)
    parent.refresh_stable_node_id("Eligibility Module")
    child.refresh_stable_node_id("Eligibility Module")

    parser = RuleSetParser()
    parser.create()
    parser.set_source_name("Eligibility Module")
    parser.get_node_set().register_node(parent)
    parser.get_node_set().register_node(child)

    parser._add_dependency(parent, child, DependencyType.get_and())

    dependency_matrix = parser.create_dependency_matrix().get_dependency_two_dimension_list()

    assert len(dependency_matrix) == 6
    assert dependency_matrix[3][5] == DependencyType.get_and()
