from project.nodes.dependency_builder import DependencyBuilder
from project.nodes.dependency_type import DependencyType
from project.nodes.value_conclusion_line import ValueConclusionLine
from project.tokens.tokenizer import Tokenizer


def test_build_matrix_records_dependencies():
    parent = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))
    child = ValueConclusionLine(1, "service requirement met", Tokenizer.get_tokens("service requirement met"))
    builder = DependencyBuilder()

    builder.add(parent, child, DependencyType.get_and())
    matrix = builder.build_matrix(2)

    assert matrix.get_dependency_type(0, 1) == DependencyType.get_and()
    assert matrix.get_to_child_dependency_list(0) == [1]
    assert matrix.get_from_parent_dependency_list(1) == [0]


def test_build_matrix_ignores_out_of_range_dependencies():
    parent = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))
    child = ValueConclusionLine(5, "service requirement met", Tokenizer.get_tokens("service requirement met"))
    builder = DependencyBuilder()

    builder.add(parent, child, DependencyType.get_or())
    matrix = builder.build_matrix(2)

    assert matrix.get_to_child_dependency_list(0) == []


def test_get_all_dependencies_returns_copy():
    parent = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))
    child = ValueConclusionLine(1, "service requirement met", Tokenizer.get_tokens("service requirement met"))
    builder = DependencyBuilder()

    builder.add(parent, child, DependencyType.get_and())
    dependencies = builder.get_all_dependencies()
    dependencies.clear()

    assert len(builder.get_all_dependencies()) == 1
