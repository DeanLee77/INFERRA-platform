"""
Additional coverage tests for iterate_line.py — targeting MISSED lines:
213-292 (create_iterate_node_set), 316-350 (iterate_feed_answers_with_json),
403-430 (_iterate_feed_answers_legacy), 455/457 (via_context bool/str type branches),
493-508 (can_be_self_evaluated legacy engine path), 654-694 (_create_iterate_node_set_aux),
739 (_number_of_true_children).
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.nodes.dependency_type import DependencyType
from src.domain.nodes.iterate_line import IterateLine
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.state.feature_flags import FeatureFlags


class ConcreteIterateLine(IterateLine):
    def __init__(self):
        super().__init__()
        self._line_type = LineType.ITERATE
        self._node_name = "ALL  services  eligibility"
        self._variable_name = "services"

    def initialisation(self, parent_text: str, tokens) -> None:
        pass

    def get_iterate_next_question(self, parent_node_set, parent_assessment_state):
        return MagicMock()


def _make_iterate_line(quantifier="ALL", list_name="services", list_size=0, node_id=0):
    line = ConcreteIterateLine()
    line._node_id = node_id
    line._IterateLine__number_of_target = quantifier
    line._IterateLine__given_list_name = list_name
    line._IterateLine__given_list_size = list_size
    return line


def _make_mock_node(node_id, node_name, line_type, variable_name=None):
    n = MagicMock(spec=Node)
    n.get_node_id.return_value = node_id
    n.get_node_name.return_value = node_name
    n.get_line_type.return_value = line_type
    n.get_variable_name.return_value = variable_name or node_name
    n.get_tokens.return_value = MagicMock()
    n.get_node_line.return_value = 1
    n._node_id = node_id
    n._node_name = node_name
    n._variable_name = variable_name or node_name
    return n


def _build_parent_node_set(iterate_line, child_nodes_by_id, dep_children, child_dep_lists=None):
    parent_ns = MagicMock(spec=NodeSet)
    parent_ns.get_node_set_name.return_value = "test_module"

    iterate_runtime_id = getattr(iterate_line, "_node_id", 0)
    node_dict = {iterate_line.get_node_name(): iterate_line}
    node_id_dict = {iterate_runtime_id: iterate_line.get_node_name()}
    for cid, cn in child_nodes_by_id.items():
        node_dict[cn.get_node_name()] = cn
        node_id_dict[cid] = cn.get_node_name()

    def _node_name(node_id):
        if node_id == iterate_runtime_id:
            return iterate_line.get_node_name()
        if node_id in node_id_dict:
            return node_id_dict[node_id]
        node = _make_mock_node(node_id, f"node_{node_id}", LineType.COMPARISON, f"node_{node_id}")
        node_dict[node.get_node_name()] = node
        node_id_dict[node_id] = node.get_node_name()
        return node.get_node_name()

    graph = HyperAdjacencyGraph()
    graph.register_node(iterate_line.get_node_name(), {"runtime_id": iterate_runtime_id})
    for child_id in dep_children:
        graph.register_node(_node_name(child_id), {"runtime_id": child_id})
    if dep_children:
        graph.add_dependency_group(
            iterate_line.get_node_name(),
            DependencyType.get_or(),
            {_node_name(child_id) for child_id in dep_children},
        )

    for parent_id, children in (child_dep_lists or {}).items():
        parent_name = _node_name(parent_id)
        graph.register_node(parent_name, {"runtime_id": parent_id})
        for child_id in children:
            graph.register_node(_node_name(child_id), {"runtime_id": child_id})
        if children:
            graph.add_dependency_group(
                parent_name,
                DependencyType.get_or(),
                {_node_name(child_id) for child_id in children},
            )

    parent_ns.get_node_dictionary.return_value = node_dict
    parent_ns.get_node_id_dictionary.return_value = node_id_dict
    parent_ns.get_graph.return_value = graph
    parent_ns.get_fact_dictionary.return_value = {}
    parent_ns.get_input_dictionary.return_value = {}
    return parent_ns


def _build_iterate_result_node_set(iterate_line, answer_name="1st  services  q"):
    first_child = _make_mock_node(1, "list_size_question", LineType.COMPARISON, "list_size_question")
    answer_child = _make_mock_node(2, answer_name, LineType.COMPARISON, answer_name)
    return _build_parent_node_set(
        iterate_line,
        {1: first_child, 2: answer_child},
        [1, 2],
    )


# ===================================================================
# create_iterate_node_set (213-292)
# ===================================================================


class TestCreateIterateNodeSet:
    @patch('src.domain.nodes.iterate_line.ValueConclusionLine')
    def test_create_iterate_node_set_value_conclusion_child(self, MockVC):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "1st  services  eligible IS True"
        mock_node.get_node_id.return_value = 1
        MockVC.return_value = mock_node

        line = _make_iterate_line(node_id=0, list_size=2)
        child = _make_mock_node(2, "eligible IS True", LineType.VALUE_CONCLUSION, "eligible")
        parent_ns = _build_parent_node_set(line, {2: child}, [1, 2])

        result = line.create_iterate_node_set(parent_ns)
        assert result is not None
        assert isinstance(result, NodeSet)

    @patch('src.domain.nodes.iterate_line.ComparisonLine')
    def test_create_iterate_node_set_comparison_child(self, MockCL):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "1st  services  age > 18"
        mock_node.get_node_id.return_value = 1
        mock_rhs = MagicMock()
        mock_rhs.get_value_type.return_value = FactValueType.INTEGER
        mock_node.get_rhs.return_value = mock_rhs
        MockCL.return_value = mock_node

        line = _make_iterate_line(node_id=0, list_size=1)
        child = _make_mock_node(2, "age > 18", LineType.COMPARISON, "age")
        parent_ns = _build_parent_node_set(line, {2: child}, [1, 2])

        result = line.create_iterate_node_set(parent_ns)
        assert result is not None

    @patch('src.domain.nodes.iterate_line.ComparisonLine')
    def test_create_iterate_node_set_comparison_string_rhs(self, MockCL):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "1st  services  age > eligible"
        mock_node.get_node_id.return_value = 1
        mock_rhs = MagicMock()
        mock_rhs.get_value_type.return_value = FactValueType.STRING
        mock_rhs.get_value.return_value = "eligible"
        mock_node.get_rhs.return_value = mock_rhs
        mock_node.set_value = MagicMock()
        MockCL.return_value = mock_node

        line = _make_iterate_line(node_id=0, list_size=1)
        child = _make_mock_node(2, "age > eligible", LineType.COMPARISON, "age")
        parent_ns = _build_parent_node_set(line, {2: child}, [1, 2])

        result = line.create_iterate_node_set(parent_ns)
        assert result is not None

    @patch('src.domain.nodes.iterate_line.ExprConclusionLine')
    def test_create_iterate_node_set_expr_conclusion_child(self, MockEC):
        mock_node = MagicMock()
        mock_node.get_node_name.return_value = "1st  services  total IS CALC x + y"
        mock_node.get_node_id.return_value = 1
        MockEC.return_value = mock_node

        line = _make_iterate_line(node_id=0, list_size=1)
        child = _make_mock_node(2, "total IS CALC x + y", LineType.EXPR_CONCLUSION, "total")
        parent_ns = _build_parent_node_set(line, {2: child}, [1, 2])

        result = line.create_iterate_node_set(parent_ns)
        assert result is not None

    def test_create_iterate_node_set_empty_list_size(self):
        line = _make_iterate_line(node_id=0, list_size=0)
        parent_ns = MagicMock(spec=NodeSet)
        graph = HyperAdjacencyGraph()
        graph.register_node(line.get_node_name(), {"runtime_id": 0})
        parent_ns.get_graph.return_value = graph
        parent_ns.get_node_dictionary.return_value = {line.get_node_name(): line}
        parent_ns.get_node_id_dictionary.return_value = {0: line.get_node_name()}
        parent_ns.get_node_set_name.return_value = "test"
        parent_ns.get_fact_dictionary.return_value = {}

        result = line.create_iterate_node_set(parent_ns)
        assert result is not None


# ===================================================================
# iterate_feed_answers_with_json (316-350)
# ===================================================================


class TestIterateFeedAnswersWithJson:
    def test_iterate_feed_answers_with_json_creates_node_set(self):
        line = _make_iterate_line(node_id=0, list_size=0)
        line._variable_name = "services"
        line._node_name = "ALL  services  eligibility"

        mock_iterate_ie = MagicMock()
        mock_assessment = MagicMock()
        mock_iterate_ie.get_assessment_of_rule.return_value = mock_assessment

        mock_next_q = MagicMock()
        mock_next_q.get_variable_name.return_value = "1st  services  q"
        mock_next_q.get_node_name.return_value = "1st  services  q"

        mock_iterate_ie.get_assessment_state.return_value.get_working_memory.return_value = {
            "ALL  services  eligibility": "val"
        }
        mock_iterate_ie.find_type_of_element_to_be_asked.return_value = {}
        mock_iterate_ie.get_questions_from_node_to_be_asked.return_value = []

        mock_node_set = MagicMock(spec=NodeSet)

        with patch.object(line, 'create_iterate_node_set', return_value=mock_node_set), \
             patch('src.domain.nodes.iterate_line.InferenceEngine', return_value=mock_iterate_ie), \
             patch.object(line, 'get_iterate_next_question', return_value=mock_next_q), \
             patch.object(line, 'self_evaluate', return_value=FactValue(True)), \
             patch.object(line, '_transfer_fact_value'):

            json_data = json.dumps({"services": [{"q": "yes"}]})
            parent_ast = MagicMock()
            parent_ast.get_working_memory.return_value = {}
            parent_ast.set_fact = MagicMock()

            line.iterate_feed_answers_with_json(json_data, MagicMock(), parent_ast, MagicMock())
            assert line._IterateLine__given_list_size == 1

    def test_iterate_feed_answers_with_json_reuses_existing_node_set(self):
        line = _make_iterate_line(node_id=0, list_size=0)
        line._variable_name = "services"
        line._node_name = "ALL  services  eligibility"

        existing_ns = MagicMock(spec=NodeSet)
        mock_iterate_ie = MagicMock()
        mock_assessment = MagicMock()
        mock_iterate_ie.get_assessment_of_rule.return_value = mock_assessment
        mock_iterate_ie.get_assessment_state.return_value.get_working_memory.return_value = {
            "ALL  services  eligibility": "val"
        }

        line._IterateLine__iterate_node_set = existing_ns
        line._IterateLine__iterate_ie = mock_iterate_ie

        mock_next_q = MagicMock()
        mock_next_q.get_variable_name.return_value = "1st  services  q"
        mock_next_q.get_node_name.return_value = "1st  services  q"

        with patch.object(line, 'get_iterate_next_question', return_value=mock_next_q), \
             patch.object(line, 'self_evaluate', return_value=FactValue(True)), \
             patch.object(line, '_transfer_fact_value'):

            json_data = json.dumps({"services": [{"q": "yes"}]})
            parent_ast = MagicMock()
            parent_ast.get_working_memory.return_value = {}
            parent_ast.set_fact = MagicMock()

            line.iterate_feed_answers_with_json(json_data, MagicMock(), parent_ast, MagicMock())
            assert line._IterateLine__given_list_size == 1


# ===================================================================
# _iterate_feed_answers_legacy (403-430)
# ===================================================================


class TestIterateFeedAnswersLegacy:
    def test_legacy_first_question_sets_list_size(self):
        line = _make_iterate_line(node_id=0, list_size=0)

        first_child = _make_mock_node(1, "first_child", LineType.COMPARISON, "first_child")
        parent_ns = _build_parent_node_set(line, {1: first_child}, [1])

        mock_iterate_ie = MagicMock()
        mock_assessment = MagicMock()
        mock_iterate_ie.get_assessment_of_rule.return_value = mock_assessment
        mock_iterate_ie.get_assessment_state.return_value.get_working_memory.return_value = {}

        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        ass = MagicMock()

        with patch('src.domain.nodes.iterate_line.InferenceEngine', return_value=mock_iterate_ie), \
             patch.object(line, 'create_iterate_node_set', return_value=MagicMock()), \
             patch.object(line, 'can_be_self_evaluated', return_value=False), \
             patch.object(line, '_transfer_fact_value'):

            target_node = MagicMock()
            line._iterate_feed_answers_legacy(
                target_node, "first_child", 3, FactValueType.INTEGER,
                parent_ns, parent_ast, ass,
            )

        assert line._IterateLine__given_list_size == 3

    def test_legacy_subsequent_feed(self):
        line = _make_iterate_line(node_id=0, list_size=2)

        mock_iterate_ie = MagicMock()
        mock_assessment = MagicMock()
        mock_iterate_ie.get_assessment_of_rule.return_value = mock_assessment
        mock_iterate_ie.get_assessment_state.return_value.get_working_memory.return_value = {"key": "val"}

        line._IterateLine__iterate_node_set = MagicMock()
        line._IterateLine__iterate_ie = mock_iterate_ie

        parent_ns = MagicMock()
        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        ass = MagicMock()
        target_node = MagicMock()

        with patch.object(line, 'can_be_self_evaluated', return_value=True), \
             patch.object(line, 'self_evaluate', return_value=FactValue(True)), \
             patch.object(line, '_transfer_fact_value'):

            line._iterate_feed_answers_legacy(
                target_node, "1st  services  q", True, FactValueType.BOOLEAN,
                parent_ns, parent_ast, ass,
            )

        mock_iterate_ie.feed_answer_to_node.assert_called_once()
        parent_ast.set_fact.assert_called_once()

    def test_legacy_no_self_eval(self):
        line = _make_iterate_line(node_id=0, list_size=2)

        mock_iterate_ie = MagicMock()
        mock_assessment = MagicMock()
        mock_iterate_ie.get_assessment_of_rule.return_value = mock_assessment
        mock_iterate_ie.get_assessment_state.return_value.get_working_memory.return_value = {}

        line._IterateLine__iterate_node_set = MagicMock()
        line._IterateLine__iterate_ie = mock_iterate_ie

        parent_ns = MagicMock()
        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        ass = MagicMock()
        target_node = MagicMock()

        with patch.object(line, 'can_be_self_evaluated', return_value=False), \
             patch.object(line, '_transfer_fact_value'):

            line._iterate_feed_answers_legacy(
                target_node, "1st  services  q", True, FactValueType.BOOLEAN,
                parent_ns, parent_ast, ass,
            )

        parent_ast.set_fact.assert_not_called()

    def test_legacy_first_question_different_name(self):
        line = _make_iterate_line(node_id=0, list_size=0)

        first_child = _make_mock_node(1, "first_child", LineType.COMPARISON, "first_child")
        parent_ns = _build_parent_node_set(line, {1: first_child}, [1])

        mock_iterate_ie = MagicMock()
        mock_assessment = MagicMock()
        mock_iterate_ie.get_assessment_of_rule.return_value = mock_assessment
        mock_iterate_ie.get_assessment_state.return_value.get_working_memory.return_value = {}

        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        ass = MagicMock()

        with patch('src.domain.nodes.iterate_line.InferenceEngine', return_value=mock_iterate_ie), \
             patch.object(line, 'create_iterate_node_set', return_value=MagicMock()), \
             patch.object(line, 'can_be_self_evaluated', return_value=False), \
             patch.object(line, '_transfer_fact_value'):

            target_node = MagicMock()
            line._iterate_feed_answers_legacy(
                target_node, "other_question", 5, FactValueType.INTEGER,
                parent_ns, parent_ast, ass,
            )

        assert line._IterateLine__given_list_size == 0


# ===================================================================
# _iterate_feed_answers_via_context — missed bool/str type branches (455, 457)
# ===================================================================


class TestIterateFeedAnswersViaContextTypeBranches:
    def test_via_context_isinstance_bool_branch(self):
        line = _make_iterate_line(node_id=0, list_size=2)
        line._ensure_iterate_context(list_size=2)

        parent_ns = MagicMock()
        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        target_node = MagicMock()

        with patch.object(line, 'can_be_self_evaluated', return_value=False):
            line._iterate_feed_answers_via_context(
                target_node, "1st  services  q", True, FactValueType.STRING,
                parent_ns, parent_ast, MagicMock(),
            )
        assert line._IterateLine__context.progress[1] is True

    def test_via_context_isinstance_str_true(self):
        line = _make_iterate_line(node_id=0, list_size=1)
        line._ensure_iterate_context(list_size=1)

        parent_ns = MagicMock()
        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        target_node = MagicMock()

        with patch.object(line, 'can_be_self_evaluated', return_value=False):
            line._iterate_feed_answers_via_context(
                target_node, "1st  services  q", "true", FactValueType.INTEGER,
                parent_ns, parent_ast, MagicMock(),
            )
        assert line._IterateLine__context.progress[1] is True

    def test_via_context_isinstance_str_false(self):
        line = _make_iterate_line(node_id=0, list_size=1)
        line._ensure_iterate_context(list_size=1)

        parent_ns = MagicMock()
        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        target_node = MagicMock()

        with patch.object(line, 'can_be_self_evaluated', return_value=False):
            line._iterate_feed_answers_via_context(
                target_node, "1st  services  q", "false", FactValueType.INTEGER,
                parent_ns, parent_ast, MagicMock(),
            )
        assert line._IterateLine__context.progress[1] is False

    def test_via_context_int_value_coerced(self):
        line = _make_iterate_line(node_id=0, list_size=1)
        line._ensure_iterate_context(list_size=1)

        parent_ns = MagicMock()
        parent_ast = MagicMock()
        parent_ast.get_working_memory.return_value = {}
        target_node = MagicMock()

        with patch.object(line, 'can_be_self_evaluated', return_value=False):
            line._iterate_feed_answers_via_context(
                target_node, "1st  services  q", 0, FactValueType.INTEGER,
                parent_ns, parent_ast, MagicMock(),
            )
        assert line._IterateLine__context.progress[1] is False


# ===================================================================
# can_be_self_evaluated — legacy InferenceEngine path (493-508)
# ===================================================================


class TestCanBeSelfEvaluatedLegacyEngine:
    def test_legacy_engine_all_determined(self):
        line = _make_iterate_line(node_id=0, list_size=1)

        mock_iterate_ie = MagicMock()
        mock_node_set = _build_iterate_result_node_set(line)
        mock_iterate_ie.get_node_set.return_value = mock_node_set
        mock_iterate_ie.has_all_mandatory_child_answered.return_value = True

        line._IterateLine__iterate_ie = mock_iterate_ie
        line._IterateLine__given_list_size = 1
        line._node_id = 0

        working_memory = {"1st  services  q": FactValue(True, FactValueType.BOOLEAN)}
        result = line.can_be_self_evaluated(working_memory)
        assert result is True

    def test_legacy_engine_not_all_determined(self):
        line = _make_iterate_line(node_id=0, list_size=2)

        mock_iterate_ie = MagicMock()
        mock_node_set = _build_iterate_result_node_set(line)
        mock_iterate_ie.get_node_set.return_value = mock_node_set
        mock_iterate_ie.has_all_mandatory_child_answered.return_value = True

        line._IterateLine__iterate_ie = mock_iterate_ie
        line._IterateLine__given_list_size = 2
        line._node_id = 0

        working_memory = {"1st  services  q": FactValue(True, FactValueType.BOOLEAN)}
        result = line.can_be_self_evaluated(working_memory)
        assert result is False

    def test_legacy_engine_value_is_none(self):
        line = _make_iterate_line(node_id=0, list_size=1)

        mock_iterate_ie = MagicMock()
        mock_node_set = _build_iterate_result_node_set(line)
        mock_iterate_ie.get_node_set.return_value = mock_node_set
        mock_iterate_ie.has_all_mandatory_child_answered.return_value = True

        line._IterateLine__iterate_ie = mock_iterate_ie
        line._IterateLine__given_list_size = 1
        line._node_id = 0

        fv_none = FactValue(None)
        working_memory = {"1st  services  q": fv_none}
        result = line.can_be_self_evaluated(working_memory)
        assert result is False


# ===================================================================
# _create_iterate_node_set_aux (654-694)
# ===================================================================


class TestCreateIterateNodeSetAux:
    @patch('src.domain.nodes.iterate_line.ValueConclusionLine')
    def test_aux_with_value_conclusion_child(self, MockVC):
        line = _make_iterate_line(node_id=0, list_size=1)

        mock_new_node = MagicMock()
        mock_new_node.get_node_name.return_value = "1st  services  eligible IS True"
        mock_new_node.get_node_id.return_value = 1
        MockVC.return_value = mock_new_node

        child = _make_mock_node(2, "eligible IS True", LineType.VALUE_CONCLUSION, "eligible")
        parent_ns = _build_parent_node_set(line, {2: child}, [2])

        iterate_ns = MagicMock(spec=NodeSet)
        this_node_dict = {line.get_node_name(): line}
        this_id_dict = {0: line.get_node_name()}

        line._create_iterate_node_set_aux(
            parent_ns,
            iterate_ns,
            this_node_dict,
            this_id_dict,
            line.get_node_name(),
            line.get_node_name(),
            "1st",
        )

        assert len(this_node_dict) > 1

    @patch('src.domain.nodes.iterate_line.ComparisonLine')
    def test_aux_with_comparison_child(self, MockCL):
        line = _make_iterate_line(node_id=0, list_size=1)

        mock_new_node = MagicMock()
        mock_new_node.get_node_name.return_value = "1st  services  age > 18"
        mock_new_node.get_node_id.return_value = 2
        MockCL.return_value = mock_new_node

        child = _make_mock_node(2, "age > 18", LineType.COMPARISON, "age")
        parent_ns = _build_parent_node_set(line, {2: child}, [2])

        iterate_ns = MagicMock(spec=NodeSet)
        this_node_dict = {line.get_node_name(): line}
        this_id_dict = {0: line.get_node_name()}

        line._create_iterate_node_set_aux(
            parent_ns,
            iterate_ns,
            this_node_dict,
            this_id_dict,
            line.get_node_name(),
            line.get_node_name(),
            "1st",
        )

    @patch('src.domain.nodes.iterate_line.ExprConclusionLine')
    def test_aux_with_expr_conclusion_child(self, MockEC):
        line = _make_iterate_line(node_id=0, list_size=1)

        mock_new_node = MagicMock()
        mock_new_node.get_node_name.return_value = "1st  services  total IS CALC x + y"
        mock_new_node.get_node_id.return_value = 2
        MockEC.return_value = mock_new_node

        child = _make_mock_node(2, "total IS CALC x + y", LineType.EXPR_CONCLUSION, "total")
        parent_ns = _build_parent_node_set(line, {2: child}, [2])

        iterate_ns = MagicMock(spec=NodeSet)
        this_node_dict = {line.get_node_name(): line}
        this_id_dict = {0: line.get_node_name()}

        line._create_iterate_node_set_aux(
            parent_ns,
            iterate_ns,
            this_node_dict,
            this_id_dict,
            line.get_node_name(),
            line.get_node_name(),
            "1st",
        )

    def test_aux_empty_child_list(self):
        line = _make_iterate_line(node_id=0, list_size=1)

        parent_ns = _build_parent_node_set(line, {}, [])
        iterate_ns = MagicMock(spec=NodeSet)
        this_node_dict = {}
        this_id_dict = {}

        line._create_iterate_node_set_aux(
            parent_ns,
            iterate_ns,
            this_node_dict,
            this_id_dict,
            line.get_node_name(),
            line.get_node_name(),
            "1st",
        )

        assert this_node_dict == {}

    def test_aux_node_already_exists_in_dict(self):
        line = _make_iterate_line(node_id=0, list_size=1)

        child = _make_mock_node(2, "eligible IS True", LineType.VALUE_CONCLUSION, "eligible")
        parent_ns = _build_parent_node_set(line, {2: child}, [2])

        iterate_ns = MagicMock(spec=NodeSet)
        pre_existing_key = "1st  services  eligible IS True"
        existing_clone = _make_mock_node(2, pre_existing_key, LineType.VALUE_CONCLUSION, "eligible")
        this_node_dict = {line.get_node_name(): line, pre_existing_key: existing_clone}
        this_id_dict = {0: line.get_node_name(), 2: pre_existing_key}

        line._create_iterate_node_set_aux(
            parent_ns,
            iterate_ns,
            this_node_dict,
            this_id_dict,
            line.get_node_name(),
            line.get_node_name(),
            "1st",
        )

        assert pre_existing_key in this_node_dict


# ===================================================================
# _number_of_true_children (739)
# ===================================================================


class TestNumberOfTrueChildren:
    def test_number_of_true_children_with_true(self):
        line = _make_iterate_line(node_id=0, list_size=2)

        mock_iterate_ie = MagicMock()
        mock_node_set = _build_iterate_result_node_set(line)
        mock_iterate_ie.get_node_set.return_value = mock_node_set

        line._IterateLine__iterate_ie = mock_iterate_ie
        line._node_id = 0

        working_memory = {
            "1st  services  q": FactValue(True, FactValueType.BOOLEAN),
        }
        result = line._number_of_true_children(working_memory)
        assert result == 1

    def test_number_of_true_children_with_false(self):
        line = _make_iterate_line(node_id=0, list_size=2)

        mock_iterate_ie = MagicMock()
        mock_node_set = _build_iterate_result_node_set(line)
        mock_iterate_ie.get_node_set.return_value = mock_node_set

        line._IterateLine__iterate_ie = mock_iterate_ie
        line._node_id = 0

        working_memory = {
            "1st  services  q": FactValue(False, FactValueType.BOOLEAN),
        }
        result = line._number_of_true_children(working_memory)
        assert result == 0


# ===================================================================
# get_iterate_node_set with value set
# ===================================================================


class TestGetIterateNodeSetWithValue:
    def test_get_iterate_node_set_after_set(self):
        line = _make_iterate_line()
        mock_ns = MagicMock(spec=NodeSet)
        line._IterateLine__iterate_node_set = mock_ns
        assert line.get_iterate_node_set() is mock_ns
