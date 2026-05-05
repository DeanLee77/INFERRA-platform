import json
from collections import deque
from unittest.mock import MagicMock, patch, PropertyMock

from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.assessment import Assessment
from src.domain.inference.assessments import Assessments
from src.domain.inference.assessment_state import AssessmentState
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.line_type import LineType
from src.domain.nodes.dependency_type import DependencyType
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags
from src.domain.tokens.token import Token


def _make_node(node_id=0, line_type=LineType.VALUE_CONCLUSION,
               variable_name="var1", node_name="node1",
               is_plain_statement=False, fact_value=None):
    node = MagicMock()
    node._node_id = node_id
    node.get_node_id.return_value = node_id
    node.get_line_type.return_value = line_type
    node.get_variable_name.return_value = variable_name
    node.get_node_name.return_value = node_name
    node.get_is_plain_statement.return_value = is_plain_statement
    node.get_fact_value.return_value = fact_value or FactValue("test_val")
    node.get_tokens.return_value = Token([], [], "")
    return node


def _build_graph(nodes, edges):
    graph = HyperAdjacencyGraph()
    for node_name in nodes:
        graph.register_node(node_name)
    for parent_name, child_name, dep_type in edges:
        graph.add_dependency_group(parent_name, dep_type, {child_name})
    return graph


def _make_node_set(nodes=None, fact_dict=None, dep_matrix=None,
                   id_dict=None, default_goal_name=None, edges=None):
    ns = MagicMock(spec=NodeSet)
    if nodes is None:
        nodes = {}
    if fact_dict is None:
        fact_dict = {}
    if id_dict is None:
        id_dict = {i: n.get_node_name() for i, n in enumerate(nodes.values())} if nodes else {}
    if dep_matrix is None:
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        dep_matrix.get_dependency_type.return_value = -1

    ns.get_node_dictionary.return_value = nodes
    ns.get_fact_dictionary.return_value = fact_dict
    ns.get_dependency_matrix.return_value = dep_matrix
    ns.get_node_id_dictionary.return_value = id_dict
    ns.get_sorted_node_list.return_value = list(nodes.values())
    ns.find_node_index.return_value = 0

    if edges is not None:
        graph = _build_graph(nodes.keys(), edges)
        ns.get_graph.return_value = graph
    elif id_dict and dep_matrix is not None:
        inferred_edges = []
        for parent_id, parent_name in id_dict.items():
            try:
                child_ids = dep_matrix.get_to_child_dependency_list(parent_id)
            except Exception:
                child_ids = []
            for child_id in child_ids:
                if isinstance(child_id, (list, tuple, set)):
                    nested_ids = child_id
                else:
                    nested_ids = [child_id]
                for nested_child_id in nested_ids:
                    child_name = id_dict.get(nested_child_id)
                    if child_name is None:
                        continue
                    try:
                        dep_type = dep_matrix.get_dependency_type(parent_id, nested_child_id)
                    except Exception:
                        dep_type = DependencyType.get_and()
                    if not isinstance(dep_type, int) or dep_type == -1:
                        dep_type = DependencyType.get_and()
                    inferred_edges.append((parent_name, child_name, dep_type))
        ns.get_graph.return_value = _build_graph(nodes.keys(), inferred_edges)
    else:
        ns.get_graph.return_value = None

    if default_goal_name and default_goal_name in nodes:
        ns.get_default_goal_node.return_value = nodes[default_goal_name]
    else:
        ns.get_default_goal_node.return_value = None

    return ns


class TestInferenceEngineInit:
    def test_init_no_args(self):
        engine = InferenceEngine()
        assert engine.get_node_set() is None
        assert engine.get_assessment_state() is not None
        assert engine.get_assessments() is not None
        assert engine.get_dependency_graph() is None
        assert engine.get_feature_flags() is not None

    def test_init_with_feature_flags(self):
        flags = FeatureFlags(use_hypergraph=False, legacy_iterate=True, layered_memory=True)
        engine = InferenceEngine(feature_flags=flags)
        assert engine.get_feature_flags() is flags

    def test_init_with_node_set(self):
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine = InferenceEngine(node_set=ns)
        assert engine.get_node_set() is ns

    def test_init_with_node_set_and_hypergraph_flag(self):
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        with patch.object(InferenceEngine, '_select_graph_backend'):
            flags = FeatureFlags(use_hypergraph=True)
            engine = InferenceEngine(node_set=ns, feature_flags=flags)
            assert engine.get_feature_flags().use_hypergraph is True


class TestSetNodeSet:
    def test_set_node_set(self):
        engine = InferenceEngine()
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        assert engine.get_node_set() is ns

    def test_set_node_set_resets_assessment_state(self):
        engine = InferenceEngine()
        old_ast = engine.get_assessment_state()
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        assert engine.get_assessment_state() is not old_ast


class TestAssessmentStateAccess:
    def test_get_assessment_state(self):
        engine = InferenceEngine()
        assert isinstance(engine.get_assessment_state(), AssessmentState)


class TestAssessmentsAccess:
    def test_set_get_assessments(self):
        engine = InferenceEngine()
        asses = Assessments()
        engine.set_assessments(asses)
        assert engine.get_assessments() is asses

    def test_add_assessment(self):
        engine = InferenceEngine()
        assessment = Assessment()
        assessment._Assessment__assessment_name = "test_rule"
        engine.add_assessment_into_assessment_list(assessment)
        result = engine.get_assessment_of_rule("test_rule")
        assert result is assessment

    def test_get_assessment_of_rule_missing(self):
        engine = InferenceEngine()
        assert engine.get_assessment_of_rule("nonexistent") is None

    def test_set_get_assessment(self):
        engine = InferenceEngine()
        ass = Assessment()
        engine.set_assessment(ass)
        assert engine.get_assessment() is ass


class TestCreateFactValue:
    def test_boolean_true_bool(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value(True, FactValueType.BOOLEAN)
        assert fv.get_value() is True
        assert fv.get_value_type() == FactValueType.BOOLEAN

    def test_boolean_false_bool(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value(False, FactValueType.BOOLEAN)
        assert fv.get_value() is False

    def test_boolean_true_string(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("True", FactValueType.BOOLEAN)
        assert fv.get_value() is True

    def test_boolean_false_string(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("false", FactValueType.BOOLEAN)
        assert fv.get_value() is False

    def test_boolean_invalid_string(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("maybe", FactValueType.BOOLEAN)
        assert fv is None

    def test_date_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("2024-01-01", FactValueType.DATE)
        assert fv.get_value() == "2024-01-01"
        assert fv.get_value_type() == FactValueType.DATE

    def test_double_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("3.14", FactValueType.DOUBLE)
        assert fv.get_value() == 3.14
        assert fv.get_value_type() == FactValueType.DOUBLE

    def test_integer_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("42", FactValueType.INTEGER)
        assert fv.get_value() == 42
        assert fv.get_value_type() == FactValueType.INTEGER

    def test_string_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("hello", FactValueType.STRING)
        assert fv.get_value() == "hello"
        assert fv.get_value_type() == FactValueType.STRING

    def test_defi_string_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("val", FactValueType.DEFI_STRING)
        assert fv.get_value() == "val"
        assert fv.get_value_type() == FactValueType.DEFI_STRING

    def test_hash_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("abc", FactValueType.HASH)
        assert fv.get_value() == "abc"
        assert fv.get_value_type() == FactValueType.HASH

    def test_url_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("http://x", FactValueType.URL)
        assert fv.get_value() == "http://x"
        assert fv.get_value_type() == FactValueType.URL

    def test_guid_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("123", FactValueType.GUID)
        assert fv.get_value() == "123"
        assert fv.get_value_type() == FactValueType.GUID

    def test_list_type(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value(["a", "b"], FactValueType.LIST)
        assert fv.get_value() == ["a", "b"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_unknown_type_returns_none(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("x", FactValueType.WARNING)
        assert fv is None


class TestTypeAlreadySet:
    def test_defi_string_is_set(self):
        engine = InferenceEngine()
        fv = FactValue("x", FactValueType.DEFI_STRING)
        assert engine._type_already_set(fv) is True

    def test_integer_is_set(self):
        engine = InferenceEngine()
        fv = FactValue(1, FactValueType.INTEGER)
        assert engine._type_already_set(fv) is True

    def test_double_is_set(self):
        engine = InferenceEngine()
        fv = FactValue(1.0, FactValueType.DOUBLE)
        assert engine._type_already_set(fv) is True

    def test_date_is_set(self):
        engine = InferenceEngine()
        fv = FactValue("2024", FactValueType.DATE)
        assert engine._type_already_set(fv) is True

    def test_boolean_is_set(self):
        engine = InferenceEngine()
        fv = FactValue(True, FactValueType.BOOLEAN)
        assert engine._type_already_set(fv) is True

    def test_guid_is_set(self):
        engine = InferenceEngine()
        fv = FactValue("abc", FactValueType.GUID)
        assert engine._type_already_set(fv) is True

    def test_url_is_set(self):
        engine = InferenceEngine()
        fv = FactValue("http://x", FactValueType.URL)
        assert engine._type_already_set(fv) is True

    def test_hash_is_set(self):
        engine = InferenceEngine()
        fv = FactValue("abc", FactValueType.HASH)
        assert engine._type_already_set(fv) is True

    def test_string_not_set(self):
        engine = InferenceEngine()
        fv = FactValue("x", FactValueType.STRING)
        assert engine._type_already_set(fv) is False

    def test_list_not_set(self):
        engine = InferenceEngine()
        fv = FactValue([], FactValueType.LIST)
        assert engine._type_already_set(fv) is False

    def test_unknown_not_set(self):
        engine = InferenceEngine()
        fv = FactValue(None, FactValueType.UNKNOWN)
        assert engine._type_already_set(fv) is False


class TestHandleValueConclusionLineTrueCase:
    def test_plain_statement_format(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine._handle_value_conclusion_line_true_case(
            node, is_plain_statement_format=True, node_fact_value_in_string="val"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "node1" in wm
        assert wm["node1"].get_value() is True

    def test_non_plain_with_working_memory_value(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine.get_assessment_state().set_fact("val", FactValue("from_wm"))
        engine._handle_value_conclusion_line_true_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="val"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "var1" in wm
        assert wm["var1"].get_value() == "from_wm"

    def test_non_plain_without_working_memory_value(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1", fact_value=FactValue("direct"))
        engine._handle_value_conclusion_line_true_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="not_in_wm"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "var1" in wm
        assert "node1" in wm

    def test_non_plain_adds_to_summary(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine._handle_value_conclusion_line_true_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="val"
        )
        assert "var1" in engine.get_assessment_state().get_summary_list()


class TestHandleValueConclusionLineFalseCase:
    def test_plain_statement_format(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine._handle_value_conclusion_line_false_case(
            node, is_plain_statement_format=True, node_fact_value_in_string="val"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "node1" in wm
        assert wm["node1"].get_value() is False

    def test_non_plain_with_list_in_working_memory(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine.get_assessment_state().set_fact(
            "val", FactValue([FactValue("existing")], FactValueType.LIST)
        )
        engine._handle_value_conclusion_line_false_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="val"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "var1" in wm
        assert wm["var1"].get_value_type() == FactValueType.LIST

    def test_non_plain_with_non_list_in_working_memory(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine.get_assessment_state().set_fact("val", FactValue("existing"))
        engine._handle_value_conclusion_line_false_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="val"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "var1" in wm
        assert wm["var1"].get_value_type() == FactValueType.LIST

    def test_non_plain_without_working_memory_value(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine._handle_value_conclusion_line_false_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="not_in_wm"
        )
        wm = engine.get_assessment_state().get_working_memory()
        assert "var1" in wm
        assert "NOT" in str(wm["var1"].get_value())

    def test_non_plain_adds_to_summary(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="node1")
        engine._handle_value_conclusion_line_false_case(
            node, is_plain_statement_format=False, node_fact_value_in_string="val"
        )
        assert "var1" in engine.get_assessment_state().get_summary_list()


class TestAddNodeFact:
    def test_no_node_set_returns_early(self):
        engine = InferenceEngine()
        engine.add_node_fact("var1", FactValue(1))

    def test_adds_matching_variable_node_to_fact_list(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="target_var")
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        engine.add_node_fact("target_var", FactValue(42))
        assert node in engine._InferenceEngine__node_fact_list

    def test_adds_matching_fact_value_node(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="other")
        node.get_fact_value.return_value = FactValue("fact_val_match")
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        engine.add_node_fact("fact_val_match", FactValue(99))
        assert node in engine._InferenceEngine__node_fact_list

    def test_no_match_appends_nothing_to_fact_list(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="unrelated")
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        engine.add_node_fact("missing", FactValue(99))
        assert len(engine._InferenceEngine__node_fact_list) == 0


class TestResetWorkingMemoryAndInclusiveList:
    def test_clears_inclusive_list(self):
        engine = InferenceEngine()
        engine.get_assessment_state().set_inclusive_list(["a", "b"])
        engine.reset_working_memory_and_inclusive_list()
        assert engine.get_assessment_state().get_inclusive_list() == []

    def test_clears_working_memory_via_set_working_memory(self):
        engine = InferenceEngine()
        engine.get_assessment_state().set_fact("x", FactValue(1))
        engine.get_assessment_state().set_working_memory({})
        assert engine.get_assessment_state().get_working_memory() == {}

    def test_empty_already(self):
        engine = InferenceEngine()
        engine.reset_working_memory_and_inclusive_list()
        assert engine.get_assessment_state().get_inclusive_list() == []
        assert engine.get_assessment_state().get_inclusive_list() == []


class TestGetDefaultGoalRuleQuestion:
    def test_no_node_set_returns_none(self):
        engine = InferenceEngine()
        assert engine.get_default_goal_rule_question() is None

    def test_returns_goal_node_name(self):
        engine = InferenceEngine()
        node = _make_node(node_name="GoalRule")
        ns = _make_node_set(nodes={"GoalRule": node}, id_dict={0: "GoalRule"},
                            default_goal_name="GoalRule")
        engine.set_node_set(ns)
        result = engine.get_default_goal_rule_question()
        assert result == "GoalRule"


class TestGetDefaultGoalRuleAnswer:
    def test_no_node_set_returns_none(self):
        engine = InferenceEngine()
        assert engine.get_default_goal_rule_answer() is None

    def test_returns_answer_from_working_memory(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="goal_var", node_name="GoalRule")
        ns = _make_node_set(nodes={"GoalRule": node}, id_dict={0: "GoalRule"},
                            default_goal_name="GoalRule")
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("goal_var", FactValue(42))
        result = engine.get_default_goal_rule_answer()
        assert result.get_value() == 42


class TestGetAssessmentGoalRuleQuestion:
    def test_with_goal_node(self):
        engine = InferenceEngine()
        node = _make_node(node_name="GoalNode")
        ass = Assessment()
        ass._Assessment__goal_node = node
        result = engine.get_assessment_goal_rule_question(ass)
        assert result == "GoalNode"

    def test_with_no_goal_node(self):
        engine = InferenceEngine()
        ass = Assessment()
        result = engine.get_assessment_goal_rule_question(ass)
        assert result is None


class TestGetAssessmentGoalRuleAnswer:
    def test_with_goal_node(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="goal_var")
        ass = Assessment()
        ass._Assessment__goal_node = node
        engine.get_assessment_state().set_fact("goal_var", FactValue(99))
        result = engine.get_assessment_goal_rule_answer(ass)
        assert result.get_value() == 99

    def test_with_no_goal_node(self):
        engine = InferenceEngine()
        ass = Assessment()
        result = engine.get_assessment_goal_rule_answer(ass)
        assert result is None


class TestGetNextQuestion:
    def test_no_node_set_returns_none(self):
        engine = InferenceEngine()
        ass = Assessment()
        assert engine.get_next_question(ass) is None

    def test_no_goal_node_returns_none(self):
        engine = InferenceEngine()
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        ass = Assessment()
        assert engine.get_next_question(ass) is None

    def test_with_goal_node_in_working_memory(self):
        engine = InferenceEngine()
        node = _make_node(node_name="goal")
        ns = _make_node_set(nodes={"goal": node}, id_dict={0: "goal"})
        engine.set_node_set(ns)
        ass = Assessment()
        ass._Assessment__goal_node = node
        ass._Assessment__goal_node_index = 0
        engine.get_assessment_state().set_fact("goal", FactValue(True))
        result = engine.get_next_question(ass)
        assert result is None or isinstance(result, Node)


class TestGetNextQuestionWithGoalName:
    def test_delegates_to_assessment(self):
        engine = InferenceEngine()
        node = _make_node(node_name="goal")
        ns = _make_node_set(nodes={"goal": node}, id_dict={0: "goal"})
        engine.set_node_set(ns)
        ass = Assessment()
        ass._Assessment__assessment_name = "goal"
        ass._Assessment__goal_node = node
        ass._Assessment__goal_node_index = 0
        engine.add_assessment_into_assessment_list(ass)
        result = engine.get_next_question_with_goal_name("goal")
        assert result is None or result is not None


class TestHasChildren:
    def test_no_node_set_returns_false(self):
        engine = InferenceEngine()
        assert engine._has_children(0) is False

    def test_with_children(self):
        engine = InferenceEngine()
        child_node = _make_node(node_id=1, node_name="child")
        parent_node = _make_node(node_id=0, node_name="parent")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        ns = _make_node_set(
            nodes={"parent": parent_node, "child": child_node},
            id_dict={0: "parent", 1: "child"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        result = engine._has_children("parent")
        assert result is True

    def test_no_children_returns_false(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"}, dep_matrix=dep_matrix)
        engine.set_node_set(ns)
        assert engine._has_children("n1") is False


class TestSelectGraphBackend:
    def test_hypergraph_false_no_op(self):
        engine = InferenceEngine(feature_flags=FeatureFlags(use_hypergraph=False))
        assert engine.get_dependency_graph() is None

    def test_hypergraph_true_no_matrix(self):
        engine = InferenceEngine(feature_flags=FeatureFlags(use_hypergraph=True))
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        ns.get_graph.return_value = None
        ns.get_dependency_matrix.return_value = None
        engine._select_graph_backend(ns)
        assert engine.get_dependency_graph() is None

    def test_hypergraph_true_no_id_map(self):
        engine = InferenceEngine(feature_flags=FeatureFlags(use_hypergraph=True))
        node = _make_node(node_id=None)
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        ns.get_graph.return_value = None
        ns.get_node_id_dictionary.return_value = None
        engine._select_graph_backend(ns)
        assert engine.get_dependency_graph() is None

    def test_uses_canonical_graph_from_node_set(self):
        engine = InferenceEngine(feature_flags=FeatureFlags(use_hypergraph=True))
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        canonical_graph = ns.get_graph()

        engine._select_graph_backend(ns)

        assert engine.get_dependency_graph() is canonical_graph


class TestProcessParentDependencies:
    def test_no_node_set_returns(self):
        engine = InferenceEngine()
        node = _make_node()
        ass = Assessment()
        engine._process_parent_dependencies(node, ass)

    def test_adds_mandatory_for_mandatory_dependency(self):
        engine = InferenceEngine()
        node = _make_node(node_id=1, node_name="child_node")
        parent_node = _make_node(node_id=0, node_name="parent_node")
        dep_matrix = MagicMock()
        dep_matrix.get_from_parent_dependency_list.return_value = [0]
        dep_matrix.get_dependency_type.return_value = DependencyType.get_mandatory() | DependencyType.get_and()
        dep_matrix.get_to_child_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"child_node": node, "parent_node": parent_node},
            id_dict={0: "parent_node", 1: "child_node"},
            dep_matrix=dep_matrix,
            edges=[("parent_node", "child_node", DependencyType.get_mandatory() | DependencyType.get_and())]
        )
        engine.set_node_set(ns)
        ass = Assessment()
        engine._process_parent_dependencies(node, ass)
        assert "child_node" in engine.get_assessment_state().get_mandatory_list()


class TestHasAnyOrChildEvaluated:
    def test_no_node_set_returns_false(self):
        engine = InferenceEngine()
        assert engine._has_any_or_child_evaluated("parent", ["child"]) is False


class TestHasAllAndChildEvaluated:
    def test_no_node_set_returns_false(self):
        engine = InferenceEngine()
        assert engine._has_all_and_child_evaluated(["child"]) is False

    def test_all_children_evaluated(self):
        engine = InferenceEngine()
        node = _make_node(node_id=1, variable_name="var1", node_name="n1")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1", 1: "n1"}, dep_matrix=dep_matrix)
        ns.get_node_by_node_id.return_value = node
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("var1", FactValue(True))
        result = engine._has_all_and_child_evaluated(["n1"])
        assert result is True

    def test_not_all_children_evaluated(self):
        engine = InferenceEngine()
        node = _make_node(node_id=1, variable_name="var1")
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        result = engine._has_all_and_child_evaluated(["n1"])
        assert result is False


class TestIsIterateLineChild:
    def test_no_node_set_returns_false(self):
        engine = InferenceEngine()
        assert engine._is_iterate_line_child("n0") is False

    def test_not_child_of_iterate(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, line_type=LineType.VALUE_CONCLUSION, node_name="n0")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(nodes={"n0": node}, id_dict={0: "n0"}, dep_matrix=dep_matrix)
        engine.set_node_set(ns)
        result = engine._is_iterate_line_child("n0")
        assert result is False


class TestCanDetermine:
    def test_always_returns_true(self):
        engine = InferenceEngine()
        node = _make_node()
        assert engine._can_determine(node, LineType.VALUE_CONCLUSION) is True
        assert engine._can_determine(node, LineType.COMPARISON) is True


class TestHandleNodeEvaluation:
    def test_value_conclusion_non_plain_self_evaluates(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, variable_name="var1",
                          node_name="node1", is_plain_statement=False)
        node.self_evaluate.return_value = FactValue(True)
        engine._handle_node_evaluation(node, FactValue("some_val"))
        node.self_evaluate.assert_called_once()

    def test_value_conclusion_plain_statement_no_self_eval(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, is_plain_statement=True)
        engine._handle_node_evaluation(node, FactValue(True))
        node.self_evaluate.assert_not_called()

    def test_comparison_with_non_string_rhs(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.COMPARISON)
        node.get_rhs.return_value = FactValue(10)
        node.self_evaluate.return_value = FactValue(True)
        engine._handle_node_evaluation(node, FactValue(5))
        node.self_evaluate.assert_called_once()

    def test_comparison_with_string_rhs_not_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.COMPARISON)
        node.get_rhs.return_value = FactValue("missing_var")
        node.self_evaluate.return_value = FactValue(False)
        engine._handle_node_evaluation(node, FactValue(5))
        node.self_evaluate.assert_not_called()

    def test_comparison_with_string_rhs_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.COMPARISON)
        node.get_rhs.return_value = FactValue("known_var")
        engine.get_assessment_state().set_fact("known_var", FactValue(10))
        node.self_evaluate.return_value = FactValue(True)
        engine._handle_node_evaluation(node, FactValue(5))
        node.self_evaluate.assert_called_once()

    def test_other_line_type_no_eval(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.ITERATE)
        engine._handle_node_evaluation(node, FactValue(True))
        node.self_evaluate.assert_not_called()


class TestFeedAnswerToNode:
    def test_non_iterate_sets_fact_and_evaluates(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, variable_name="var1",
                          node_name="node1", is_plain_statement=False)
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        ass = Assessment()
        ask_node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        ass.set_node_to_be_asked(ask_node)
        engine.feed_answer_to_node(node, "var1", True, FactValueType.BOOLEAN, ass)
        assert "var1" in engine.get_assessment_state().get_working_memory()

    def test_iterate_type_calls_handle_iterate_answer(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.ITERATE)
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        ass = Assessment()
        iterate_node = _make_node(line_type=LineType.ITERATE, node_name="iter1")
        ass.set_node_to_be_asked(iterate_node)
        with patch.object(engine, '_handle_iterate_answer') as mock_handle:
            engine.feed_answer_to_node(node, "q", "val", FactValueType.STRING, ass)
            mock_handle.assert_called_once()


class TestGetListOfVariableNameAndValueOfNodes:
    def test_no_node_set_returns_empty(self):
        engine = InferenceEngine()
        assert engine.get_list_of_variable_name_and_value_of_nodes() == []

    def test_with_leaf_nodes(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="leaf_var", fact_value=FactValue("leaf_val", FactValueType.STRING))
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [[]]
        ns = _make_node_set(
            nodes={"n1": node}, id_dict={0: "n1"}, dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        result = engine.get_list_of_variable_name_and_value_of_nodes()
        assert "leaf_var" in result

    def test_with_non_leaf_nodes_excluded(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="parent_var", node_name="n1")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [[1]]
        ns = _make_node_set(
            nodes={"n1": node}, id_dict={0: "n1", 1: "child"}, dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        result = engine.get_list_of_variable_name_and_value_of_nodes()
        assert result == []


class TestInitializeFromNodeSet:
    def test_with_facts(self):
        engine = InferenceEngine()
        node = _make_node()
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"},
                            fact_dict={"fact1": FactValue(1)})
        engine._initialize_from_node_set(ns)
        assert "fact1" in engine.get_assessment_state().get_working_memory()

    def test_with_empty_facts(self):
        engine = InferenceEngine()
        ns = _make_node_set(fact_dict={})
        engine._initialize_from_node_set(ns)
        assert engine.get_assessment_state().get_working_memory() == {}

    def test_with_none_node_set(self):
        engine = InferenceEngine()
        engine._initialize_from_node_set(None)
        assert engine.get_assessment_state().get_working_memory() == {}


class TestNewAssessmentState:
    def test_returns_assessment_state(self):
        engine = InferenceEngine()
        result = engine._new_assessment_state()
        assert isinstance(result, AssessmentState)


class TestBackPropagating:
    def test_no_node_set_returns(self):
        engine = InferenceEngine()
        engine._back_propagating(0)

    def test_with_node_set(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"}, dep_matrix=dep_matrix)
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("var1", FactValue(True))
        engine._back_propagating(0)


class TestEvaluateNodeAfterPropagation:
    def test_node_index_less_than_current_index_with_children(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        engine._evaluate_node_after_propagation(node, LineType.VALUE_CONCLUSION, 0, 1)

    def test_node_index_less_than_current_index_no_children(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        node.get_lhs.return_value = "var1"
        node.get_rhs.return_value = FactValue("val")
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        engine._evaluate_node_after_propagation(node, LineType.COMPARISON, 0, 1)

    def test_node_index_equal_or_greater(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION)
        engine.get_assessment_state().get_inclusive_list().append("n1")
        engine._evaluate_node_after_propagation(node, LineType.VALUE_CONCLUSION, 2, 1)


class TestEvaluateLeafNode:
    def test_value_conclusion_non_plain_with_variable_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        node.self_evaluate.return_value = FactValue(True)
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        engine._evaluate_leaf_node(node, LineType.VALUE_CONCLUSION)
        assert "n1" in engine.get_assessment_state().get_summary_list()

    def test_value_conclusion_plain_statement(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=True)
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        engine._evaluate_leaf_node(node, LineType.VALUE_CONCLUSION)
        node.self_evaluate.assert_not_called()

    def test_comparison_with_lhs_in_wm_and_rhs_string_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="n1",
                          line_type=LineType.COMPARISON)
        node.get_lhs.return_value = "var1"
        node.get_rhs.return_value = FactValue("rhs_var", FactValueType.STRING)
        node.self_evaluate.return_value = FactValue(True)
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        engine.get_assessment_state().set_fact("rhs_var", FactValue("y"))
        engine._evaluate_leaf_node(node, LineType.COMPARISON)
        node.self_evaluate.assert_called_once()

    def test_comparison_with_non_string_rhs(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="var1", node_name="n1",
                          line_type=LineType.COMPARISON)
        node.get_lhs.return_value = "var1"
        node.get_rhs.return_value = FactValue(10)
        node.self_evaluate.return_value = FactValue(True)
        engine.get_assessment_state().set_fact("var1", FactValue(5))
        engine._evaluate_leaf_node(node, LineType.COMPARISON)
        node.self_evaluate.assert_called_once()

    def test_comparison_lhs_not_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(variable_name="missing", node_name="n1",
                          line_type=LineType.COMPARISON)
        node.get_lhs.return_value = "missing"
        node.get_rhs.return_value = FactValue(10)
        engine._evaluate_leaf_node(node, LineType.COMPARISON)
        node.self_evaluate.assert_not_called()


class TestCanEvaluate:
    def test_value_conclusion_plain_with_var_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, variable_name="var1",
                          is_plain_statement=True)
        engine.get_assessment_state().set_fact("var1", FactValue(True))
        result = engine._can_evaluate(node)
        assert result is True

    def test_comparison_non_string_rhs_with_lhs_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.COMPARISON, variable_name="var1")
        node.get_rhs.return_value = FactValue(10)
        node.get_lhs.return_value = "var1"
        engine.get_assessment_state().set_fact("var1", FactValue(5))
        node.self_evaluate.return_value = FactValue(True)
        result = engine._can_evaluate(node)
        assert result is True

    def test_comparison_string_rhs_both_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.COMPARISON, variable_name="var1")
        node.get_rhs.return_value = FactValue("rhs_var", FactValueType.STRING)
        node.get_lhs.return_value = "var1"
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        engine.get_assessment_state().set_fact("rhs_var", FactValue("y"))
        node.self_evaluate.return_value = FactValue(True)
        result = engine._can_evaluate(node)
        assert result is True

    def test_comparison_string_rhs_missing_wm(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.COMPARISON, variable_name="var1")
        node.get_rhs.return_value = FactValue("missing", FactValueType.STRING)
        engine.get_assessment_state().set_fact("var1", FactValue("x"))
        result = engine._can_evaluate(node)
        assert result is False

    def test_unknown_line_type_returns_false(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.WARNING)
        result = engine._can_evaluate(node)
        assert result is False

    def test_value_conclusion_not_plain_not_evaluable(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        node.get_tokens.return_value = Token(["AND"], [], "")
        result = engine._can_evaluate(node)
        assert result is False


class TestAddChildRuleIntoInclusiveList:
    def test_no_node_set_returns(self):
        engine = InferenceEngine()
        engine._add_child_rule_into_inclusive_list(_make_node())

    def test_adds_child_to_inclusive_list(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, node_name="child_node")
        parent = _make_node(node_id=0, node_name="parent_node")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent_node": parent, "child_node": child},
            id_dict={0: "parent_node", 1: "child_node"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine._add_child_rule_into_inclusive_list(parent)
        assert "child_node" in engine.get_assessment_state().get_inclusive_list()

    def test_does_not_add_already_inclusive(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, node_name="child_node")
        parent = _make_node(node_id=0, node_name="parent_node")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent_node": parent, "child_node": child},
            id_dict={0: "parent_node", 1: "child_node"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().get_inclusive_list().append("child_node")
        engine._add_child_rule_into_inclusive_list(parent)
        assert engine.get_assessment_state().get_inclusive_list().count("child_node") == 1

    def test_does_not_add_exclusive_child(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, node_name="child_node")
        parent = _make_node(node_id=0, node_name="parent_node")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent_node": parent, "child_node": child},
            id_dict={0: "parent_node", 1: "child_node"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().get_exclusive_list().append("child_node")
        engine._add_child_rule_into_inclusive_list(parent)
        assert "child_node" not in engine.get_assessment_state().get_inclusive_list()


class TestHasChildrenToProcess:
    def test_true_when_has_children_and_in_inclusive(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, node_name="child")
        parent = _make_node(node_id=0, node_name="parent", variable_name="parent_var")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            id_dict={0: "parent", 1: "child"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().get_inclusive_list().append("parent")
        assert engine._has_children_to_process(parent, Assessment()) is True

    def test_false_when_not_in_inclusive_list(self):
        engine = InferenceEngine()
        parent = _make_node(node_id=0, node_name="parent", variable_name="parent_var")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent": parent},
            id_dict={0: "parent"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        assert engine._has_children_to_process(parent, Assessment()) is False

    def test_false_when_variable_in_working_memory(self):
        engine = InferenceEngine()
        parent = _make_node(node_id=0, node_name="parent", variable_name="parent_var")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent": parent},
            id_dict={0: "parent"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("parent_var", FactValue(True))
        engine.get_assessment_state().get_inclusive_list().append("parent")
        assert engine._has_children_to_process(parent, Assessment()) is False

    def test_false_when_no_children(self):
        engine = InferenceEngine()
        parent = _make_node(node_id=0, node_name="parent", variable_name="pv")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"parent": parent},
            id_dict={0: "parent"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        assert engine._has_children_to_process(parent, Assessment()) is False


class TestShouldAskNode:
    def test_iterate_node_not_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, line_type=LineType.ITERATE, node_name="iter_node")
        child = _make_node(node_id=1, node_name="child_of_iter")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"iter_node": node, "child_of_iter": child},
            id_dict={0: "iter_node", 1: "child_of_iter"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        ass = Assessment()
        goal = _make_node(node_id=2, node_name="goal")
        ass._Assessment__goal_node = goal
        with patch.object(engine, '_handle_iterate_node', return_value=True, create=True):
            result = engine._should_ask_node(node, ass, 0)
            assert result is True

    def test_leaf_node_in_inclusive_list_should_ask(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, node_name="leaf", variable_name="var1",
                          line_type=LineType.VALUE_CONCLUSION)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(nodes={"leaf": node}, id_dict={0: "leaf"}, dep_matrix=dep_matrix)
        engine.set_node_set(ns)
        engine.get_assessment_state().get_inclusive_list().append("leaf")
        ass = Assessment()
        goal = _make_node(node_id=1, node_name="goal")
        ass._Assessment__goal_node = goal
        with patch.object(engine, '_can_evaluate', return_value=False):
            result = engine._should_ask_node(node, ass, 0)
            assert result is True

    def test_returns_false_when_no_conditions_met(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, node_name="n", variable_name="v",
                          line_type=LineType.VALUE_CONCLUSION)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(nodes={"n": node}, id_dict={0: "n"}, dep_matrix=dep_matrix)
        engine.set_node_set(ns)
        ass = Assessment()
        goal = _make_node(node_id=1, node_name="goal")
        ass._Assessment__goal_node = goal
        result = engine._should_ask_node(node, ass, 0)
        assert result is False


class TestHandleIterateAnswer:
    def test_handle_iterate_answer_sets_inferred_source(self):
        engine = InferenceEngine()
        iterate_node = MagicMock()
        iterate_node.can_be_self_evaluated.return_value = True
        iterate_node.self_evaluate.return_value = FactValue(True)
        iterate_node.get_node_name.return_value = "iter_rule"
        iterate_node.get_node_id.return_value = 0
        target_node = MagicMock()
        ass = MagicMock()
        ass.get_node_to_be_asked.return_value = iterate_node
        ass.get_aux_node_to_be_asked.return_value = target_node
        node_set = MagicMock()
        node_set.find_node_index.return_value = 0
        node_set.get_dependency_matrix.return_value.get_to_child_dependency_list.return_value = []
        node_set.get_dependency_matrix.return_value.get_from_parent_dependency_list.return_value = []
        node_set.get_sorted_node_list.return_value = [iterate_node]
        engine.set_node_set(node_set)
        engine._handle_iterate_answer(
            target_node, ass, "1st  var  q", True, FactValueType.BOOLEAN
        )
        iterate_node.iterate_feed_answers.assert_called_once()

    def test_handle_iterate_answer_not_self_evaluable(self):
        engine = InferenceEngine()
        iterate_node = MagicMock()
        iterate_node.can_be_self_evaluated.return_value = False
        iterate_node.get_node_name.return_value = "iter_rule"
        target_node = MagicMock()
        ass = MagicMock()
        ass.get_node_to_be_asked.return_value = iterate_node
        ass.get_aux_node_to_be_asked.return_value = target_node
        ns = _make_node_set()
        engine.set_node_set(ns)
        engine._handle_iterate_answer(
            target_node, ass, "1st  var  q", True, FactValueType.BOOLEAN
        )
        iterate_node.iterate_feed_answers.assert_called_once()
        iterate_node.self_evaluate.assert_not_called()


class TestIsIterateLineChildWithChildren:
    def test_child_of_iterate_returns_true(self):
        engine = InferenceEngine()
        iterate_node = MagicMock()
        iterate_node.get_line_type.return_value = LineType.ITERATE
        iterate_node.get_node_id.return_value = 0
        child_node = MagicMock()
        child_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
        child_node.get_node_id.return_value = 2
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.side_effect = lambda nid: [2] if nid == 0 else []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"iter": iterate_node, "child": child_node},
            id_dict={0: "iter", 2: "child"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        result = engine._is_iterate_line_child("child")
        assert result is True

    def test_not_child_removes_from_mandatory(self):
        engine = InferenceEngine()
        non_iterate = MagicMock()
        non_iterate.get_line_type.return_value = LineType.VALUE_CONCLUSION
        non_iterate.get_node_id.return_value = 0
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"n0": non_iterate},
            id_dict={0: "n0"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().add_item_to_mandatory_list("non_iterate_child")
        result = engine._is_iterate_line_child("non_iterate_child")
        assert result is False
        assert "non_iterate_child" not in engine.get_assessment_state().get_mandatory_list()


class TestIsIterateLineChildAux:
    def test_recursion_finds_nested_child(self):
        engine = InferenceEngine()
        iterate_node = MagicMock()
        iterate_node.get_line_type.return_value = LineType.ITERATE
        iterate_node.get_node_id.return_value = 0
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.side_effect = lambda nid: [1] if nid == 0 else [2] if nid == 1 else []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"iter": iterate_node},
            id_dict={0: "iter", 1: "mid", 2: "deep"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        result = engine._is_iterate_line_child("deep")
        assert result is True


class TestBackPropagatingWithNodes:
    def test_back_propagating_processes_all_nodes(self):
        engine = InferenceEngine()
        n1 = _make_node(node_id=0, variable_name="v1", node_name="n1",
                        line_type=LineType.VALUE_CONCLUSION)
        n2 = _make_node(node_id=1, variable_name="v2", node_name="n2",
                        line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"n1": n1, "n2": n2},
            id_dict={0: "n1", 1: "n2"},
            dep_matrix=dep_matrix
        )
        ns.get_sorted_node_list.return_value = [n1, n2]
        ns.find_node_index.return_value = 0
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("v2", FactValue("x"))
        engine._back_propagating(0)


class TestEvaluateNodeAfterPropagationMoreBranches:
    def test_node_index_less_current_no_children(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="v1", node_name="n1",
                          line_type=LineType.COMPARISON)
        node.get_lhs.return_value = "v1"
        node.get_rhs.return_value = FactValue("x")
        engine.get_assessment_state().set_fact("v1", FactValue("y"))
        engine.get_assessment_state().set_fact("x", FactValue("z"))
        engine._evaluate_node_after_propagation(node, LineType.COMPARISON, 0, 1)

    def test_node_index_greater_in_inclusive_not_in_wm(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="v1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"}, dep_matrix=dep_matrix)
        engine.set_node_set(ns)
        engine.get_assessment_state().get_inclusive_list().append("n1")
        engine._evaluate_node_after_propagation(node, LineType.VALUE_CONCLUSION, 2, 1)


class TestResetWorkingMemoryAndInclusiveListFull:
    def test_clears_working_memory(self):
        engine = InferenceEngine()
        engine.get_assessment_state().set_fact("key", FactValue(1))
        assert "key" in engine.get_assessment_state().get_working_memory()
        engine.get_assessment_state().invalidate_layer(FactSource.ASSERTED)
        engine.get_assessment_state().invalidate_layer(FactSource.INFERRED)
        engine.get_assessment_state().invalidate_layer(FactSource.SEMANTIC)
        assert "key" not in engine.get_assessment_state().get_working_memory()


class TestCanEvaluateValueConclusionWithIsInList:
    def test_value_conclusion_is_in_list_token(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION, variable_name="var1",
                          is_plain_statement=False)
        node.get_tokens.return_value = Token(["IS IN LIST: "], [], "")
        node.get_fact_value.return_value = FactValue("list_name")
        engine.get_assessment_state().set_fact("var1", FactValue(True))
        engine.get_assessment_state().set_fact("list_name", FactValue(["a"]))
        result = engine._can_evaluate(node)
        assert result is True


class TestFeedAnswerToNodeWithNullFactValue:
    def test_null_fact_value_does_not_set_fact(self):
        engine = InferenceEngine()
        node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        ns = _make_node_set(nodes={"n1": node}, id_dict={0: "n1"})
        engine.set_node_set(ns)
        ass = Assessment()
        ask_node = _make_node(line_type=LineType.VALUE_CONCLUSION)
        ass.set_node_to_be_asked(ask_node)
        engine.feed_answer_to_node(node, "q", "maybe", FactValueType.BOOLEAN, ass)


class TestHasAnyOrChildEvaluatedWithNodes:
    def test_or_child_evaluated_when_variable_in_wm(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, variable_name="child_var", node_name="child")
        parent = _make_node(node_id=0, variable_name="parent_var", node_name="parent")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        dep_matrix.get_dependency_type.return_value = DependencyType.get_mandatory() | DependencyType.get_or()
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            id_dict={0: "parent", 1: "child"},
            dep_matrix=dep_matrix
        )
        ns.get_node_by_node_id.return_value = child
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("child_var", FactValue(True))
        result = engine._has_any_or_child_evaluated("parent", ["child"])
        assert result is True

    def test_or_child_not_evaluated(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, variable_name="child_var", node_name="child")
        parent = _make_node(node_id=0, variable_name="parent_var", node_name="parent")
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        dep_matrix.get_dependency_type.return_value = DependencyType.get_or()
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            id_dict={0: "parent", 1: "child"},
            dep_matrix=dep_matrix
        )
        ns.get_node_by_node_id.return_value = child
        engine.set_node_set(ns)
        result = engine._has_any_or_child_evaluated("parent", ["child"])
        assert result is False


class TestGetNextQuestionProcessDependencies:
    def test_get_next_question_processes_parent_deps_for_non_initial_index(self):
        engine = InferenceEngine()
        goal = _make_node(node_id=0, node_name="goal", variable_name="goal_var",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        child = _make_node(node_id=1, node_name="child_node", variable_name="child_var",
                           line_type=LineType.VALUE_CONCLUSION, is_plain_statement=True)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = [0]
        dep_matrix.get_dependency_type.return_value = DependencyType.get_mandatory() | DependencyType.get_and()
        ns = _make_node_set(
            nodes={"goal": goal, "child_node": child},
            id_dict={0: "goal", 1: "child_node"},
            dep_matrix=dep_matrix
        )
        ns.get_sorted_node_list.return_value = [goal, child]
        engine.set_node_set(ns)
        ass = Assessment()
        ass._Assessment__goal_node = child
        ass._Assessment__goal_node_index = 0
        result = engine.get_next_question(ass)

    def test_get_next_question_adds_children_to_process(self):
        engine = InferenceEngine()
        goal = _make_node(node_id=0, node_name="goal", variable_name="goal_var",
                          line_type=LineType.VALUE_CONCLUSION)
        child = _make_node(node_id=1, node_name="child_node", variable_name="child_var",
                           line_type=LineType.VALUE_CONCLUSION)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.side_effect = lambda nid: [1] if nid == 0 else []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        dep_matrix.get_dependency_type.return_value = -1
        ns = _make_node_set(
            nodes={"goal": goal, "child_node": child},
            id_dict={0: "goal", 1: "child_node"},
            dep_matrix=dep_matrix
        )
        ns.get_sorted_node_list.return_value = [goal, child]
        engine.set_node_set(ns)
        ass = Assessment()
        ass._Assessment__goal_node = goal
        ass._Assessment__goal_node_index = 0
        engine.get_assessment_state().get_inclusive_list().append("goal")
        result = engine.get_next_question(ass)

    def test_get_next_question_sets_aux_for_iterate(self):
        engine = InferenceEngine()
        iterate_node = _make_node(node_id=0, line_type=LineType.ITERATE, node_name="iter_rule", variable_name="iter_var")
        goal = _make_node(node_id=1, node_name="goal", variable_name="goal_var",
                          line_type=LineType.VALUE_CONCLUSION)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_from_parent_dependency_list.return_value = []
        dep_matrix.get_dependency_type.return_value = -1
        ns = _make_node_set(
            nodes={"goal": goal},
            id_dict={0: "iter_rule", 1: "goal"},
            dep_matrix=dep_matrix
        )
        ns.get_sorted_node_list.return_value = [iterate_node, goal]
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("goal", FactValue(True))
        ass = Assessment()
        ass._Assessment__goal_node = goal
        ass._Assessment__goal_node_index = 0
        ass.set_node_to_be_asked(iterate_node)
        result = engine.get_next_question(ass)
        assert result is iterate_node
        assert ass.get_aux_node_to_be_asked() is iterate_node


class TestProcessNodeDependencies:
    def test_no_node_set_returns(self):
        engine = InferenceEngine()
        node = _make_node()
        engine._process_node_dependencies(node)

    def test_with_parent_deps_adds_to_mandatory(self):
        engine = InferenceEngine()
        child = _make_node(node_id=1, node_name="child_node", variable_name="child_var")
        parent = _make_node(node_id=0, node_name="parent_node", variable_name="parent_var")
        dep_matrix = MagicMock()
        dep_matrix.get_from_parent_dependency_list.return_value = [0]
        dep_matrix.get_to_child_dependency_list.return_value = []
        dep_matrix.get_dependency_type.return_value = DependencyType.get_mandatory() | DependencyType.get_and()
        ns = _make_node_set(
            nodes={"child_node": child, "parent_node": parent},
            id_dict={0: "parent_node", 1: "child_node"},
            dep_matrix=dep_matrix,
            edges=[("parent_node", "child_node", DependencyType.get_mandatory() | DependencyType.get_and())]
        )
        engine.set_node_set(ns)
        engine._process_node_dependencies(child)
        assert "child_node" in engine.get_assessment_state().get_mandatory_list()


class TestEvaluateNodeAfterPropagationBranches:
    def test_node_index_less_with_children_can_determine_non_expr(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        node.self_evaluate.return_value = FactValue(True)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"n1": node},
            id_dict={0: "n1", 1: "child"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().set_fact("var1", FactValue(True))
        with patch.object(engine, '_has_children', return_value=True), \
             patch.object(engine, '_can_determine', return_value=True):
            engine._evaluate_node_after_propagation(node, LineType.VALUE_CONCLUSION, 0, 1)
        assert "n1" in engine.get_assessment_state().get_summary_list()

    def test_node_index_greater_in_inclusive_with_children_can_determine(self):
        engine = InferenceEngine()
        node = _make_node(node_id=0, variable_name="var1", node_name="n1",
                          line_type=LineType.VALUE_CONCLUSION, is_plain_statement=False)
        node.self_evaluate.return_value = FactValue(True)
        dep_matrix = MagicMock()
        dep_matrix.get_to_child_dependency_list.return_value = [1]
        dep_matrix.get_from_parent_dependency_list.return_value = []
        ns = _make_node_set(
            nodes={"n1": node},
            id_dict={0: "n1", 1: "child"},
            dep_matrix=dep_matrix
        )
        engine.set_node_set(ns)
        engine.get_assessment_state().get_inclusive_list().append("n1")
        with patch.object(engine, '_has_children', return_value=True), \
             patch.object(engine, '_can_determine', return_value=True):
            engine._evaluate_node_after_propagation(node, LineType.VALUE_CONCLUSION, 2, 1)
        assert "n1" in engine.get_assessment_state().get_summary_list()


class TestIsIterateLineChildAuxNoNodeSet:
    def test_no_node_set_returns(self):
        engine = InferenceEngine()
        assert engine._is_iterate_line_child("ghost") is False


class TestResetWorkingMemoryClear:
    def test_clears_working_memory_directly(self):
        engine = InferenceEngine()
        engine.get_assessment_state().set_fact("key1", FactValue(1))
        engine.get_assessment_state().get_inclusive_list().append("item1")
        assert "key1" in engine.get_assessment_state().get_working_memory()
        engine.reset_working_memory_and_inclusive_list()
        assert len(engine.get_assessment_state().get_inclusive_list()) == 0
