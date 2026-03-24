from project.inference.question_resolver import QuestionResolver
from project.nodes.comparison_line import ComparisonLine
from project.nodes.iterate_line import IterateLine
from project.nodes.metadata_line import MetadataLine
from project.nodes.value_conclusion_line import ValueConclusionLine
from project.tokens.tokenizer import Tokenizer


def _resolver():
    return QuestionResolver(lambda _: None)


def test_find_next_question_node_returns_leaf_value_conclusion():
    node = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))

    result = _resolver().find_next_question_node(node, {})

    assert result is node


def test_find_next_question_node_skips_resolved_value_conclusion():
    node = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))

    result = _resolver().find_next_question_node(node, {"person qualifies": True})

    assert result is None


def test_find_next_question_node_skips_value_conclusion_with_children():
    node = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))

    result = _resolver().find_next_question_node(node, {}, has_children=True)

    assert result is None


def test_find_next_question_node_accepts_input_metadata():
    node = MetadataLine("INPUT claimant age AS NUMBER", Tokenizer.get_tokens("INPUT claimant age AS NUMBER"))

    result = _resolver().find_next_question_node(node, {})

    assert result is node


def test_find_next_question_node_accepts_iterate_nodes():
    node = IterateLine(0, "ALL service ITERATE: LIST OF service history", Tokenizer.get_tokens("ALL service ITERATE: LIST OF service history"))

    result = _resolver().find_next_question_node(node, {})

    assert result is node


def test_find_next_question_node_skips_comparison_nodes():
    node = ComparisonLine(0, "claimant age >= 18", Tokenizer.get_tokens("claimant age >= 18"))

    result = _resolver().find_next_question_node(node, {})

    assert result is None


def test_find_next_question_node_honours_visited_ids():
    node = ValueConclusionLine(0, "person qualifies", Tokenizer.get_tokens("person qualifies"))

    result = _resolver().find_next_question_node(node, {}, visited={0})

    assert result is None
