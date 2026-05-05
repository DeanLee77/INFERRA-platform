from unittest.mock import MagicMock

from src.domain.fact_values import FactValue
from src.domain.inference.question_resolver import QuestionResolver
from src.domain.nodes.line_type import LineType
from src.domain.nodes.meta_type import MetaType
from src.domain.nodes.metadata_line import MetadataLine


def _make_node(node_id=0, line_type=LineType.VALUE_CONCLUSION,
               var_name="var1", node_name="node1", has_children=False,
               meta_type=None):
    node = MagicMock()
    node.get_node_id.return_value = node_id
    node.get_line_type.return_value = line_type
    node.get_variable_name.return_value = var_name
    node.get_node_name.return_value = node_name
    node.has_children = has_children
    if meta_type is not None:
        node.get_meta_type.return_value = meta_type
    return node


class TestQuestionResolverInit:
    def test_stores_callback(self):
        cb = MagicMock(return_value=FactValue(True))
        qr = QuestionResolver(cb)
        node = _make_node()
        result = qr.resolve_answer(node)
        cb.assert_called_once_with(node)
        assert result == cb.return_value

    def test_callback_returns_none(self):
        qr = QuestionResolver(lambda _: None)
        assert qr.resolve_answer(_make_node()) is None


class TestFindNextQuestionNode:
    def test_returns_node_when_user_input_required(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, var_name="x")
        result = qr.find_next_question_node(node, {})
        assert result is node

    def test_returns_none_when_variable_in_working_memory(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(var_name="x")
        result = qr.find_next_question_node(node, {"x": FactValue(True)})
        assert result is None

    def test_returns_none_when_node_name_in_working_memory(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(var_name="x", node_name="n1")
        result = qr.find_next_question_node(node, {"n1": FactValue(True)})
        assert result is None

    def test_already_visited_returns_none(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(node_name="visited_node")
        visited = {"visited_node"}
        result = qr.find_next_question_node(node, {}, visited=visited)
        assert result is None

    def test_adds_node_to_visited_set(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(node_name="node_7")
        visited = set()
        qr.find_next_question_node(node, {}, visited=visited)
        assert "node_7" in visited

    def test_iterate_line_type_returns_node(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.ITERATE)
        result = qr.find_next_question_node(node, {})
        assert result is node

    def test_meta_line_input_returns_node(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.META, meta_type=MetaType.INPUT)
        node.__class__ = MetadataLine
        node.get_meta_type.return_value = MetaType.INPUT
        result = qr.find_next_question_node(node, {})
        assert result is node

    def test_meta_line_non_input_returns_none(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.META, meta_type=MetaType.FIXED)
        result = qr.find_next_question_node(node, {})
        assert result is None

    def test_meta_non_metadata_line_returns_none(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.META)
        result = qr.find_next_question_node(node, {})
        assert result is None

    def test_value_conclusion_with_children_returns_none(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        result = qr.find_next_question_node(node, {}, has_children=True)
        assert result is None

    def test_value_conclusion_no_children_returns_node(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        result = qr.find_next_question_node(node, {}, has_children=False)
        assert result is node

    def test_unknown_line_type_returns_none(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.WARNING)
        result = qr.find_next_question_node(node, {})
        assert result is None

    def test_visited_default_is_fresh_set(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(node_name="node_1")
        visited = set()
        result1 = qr.find_next_question_node(node, {}, visited=visited)
        assert result1 is node
        assert "node_1" in visited
        result2 = qr.find_next_question_node(node, {}, visited=visited)
        assert result2 is None


class TestRequiresUserInput:
    def test_variable_in_memory_returns_false(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(var_name="known")
        assert qr._requires_user_input(node, {"known": FactValue(1)}) is False

    def test_node_name_in_memory_returns_false(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(node_name="known")
        assert qr._requires_user_input(node, {"known": FactValue(1)}) is False

    def test_iterate_always_true(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.ITERATE)
        assert qr._requires_user_input(node, {}) is True

    def test_value_conclusion_no_children_true(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        assert qr._requires_user_input(node, {}, has_children=False) is True

    def test_value_conclusion_with_children_false(self):
        qr = QuestionResolver(lambda _: None)
        node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        assert qr._requires_user_input(node, {}, has_children=True) is False


class TestResolveAnswer:
    def test_delegates_to_callback(self):
        cb = MagicMock(return_value=FactValue(42))
        qr = QuestionResolver(cb)
        node = _make_node()
        result = qr.resolve_answer(node)
        assert result.get_value() == 42

    def test_none_callback_result(self):
        qr = QuestionResolver(lambda _: None)
        assert qr.resolve_answer(_make_node()) is None
