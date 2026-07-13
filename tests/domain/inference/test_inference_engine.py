import json
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.question_strategy import (
    OntologyReachabilityQuestionStrategy,
    ReachabilityEvidence,
)
from src.domain.inference.semantic_question_strategy import SemanticQuestionStrategy
from src.domain.inference.assessment import Assessment
from src.domain.inference.assessments import Assessments
from src.domain.inference.assessment_state import AssessmentState
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.line_type import LineType
from src.domain.graph.dependency_type import DependencyType
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.reasoning.semantic_fact_enricher import (
    INF_CONFIDENCE,
    INF_NAME,
    RDF_TYPE,
    RDFS_SUBCLASS_OF,
    OntologyIndex,
)
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags
from src.domain.tokens.token import Token


INF = "http://inferra.ai/schema#"
SYN = "http://inferra.ai/synthetic#"


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
    ns.get_input_dictionary.return_value = {}
    ns.get_type_dictionary.return_value = {}
    ns.get_collection_dictionary.return_value = {}
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


def _parse_node_set(rule_text, source_name="synthetic_rule"):
    from src.domain.rule_parser.rule_set_parser import RuleSetParser
    from src.domain.rule_parser.rule_set_reader import RuleSetReader
    from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

    reader = RuleSetReader()
    reader.create()
    reader.set_file_with_text(rule_text)
    parser = RuleSetParser()
    parser.create()
    parser.set_source_name(source_name)
    scanner = RuleSetScanner(reader, parser)
    scanner.scan_rule_set()
    return scanner.establish_node_set()


def _test_ontology_reasoner():
    return OntologyReasoner(
        source_graph_uri="urn:test:graph",
        ontology_snapshot_ref="test_rule:hash",
        ontology_snapshot_hash="hash",
        confidence_threshold=0.85,
    )


def _test_vehicle_ontology_index():
    return OntologyIndex(
        [
            (f"{SYN}forklift", INF_NAME, "forklift"),
            (f"{SYN}forklift", RDF_TYPE, f"{INF}IndustrialVehicle"),
            (f"{INF}IndustrialVehicle", RDFS_SUBCLASS_OF, f"{INF}TypeApprovedEquipment"),
            (f"{INF}TypeApprovedEquipment", INF_NAME, "vehicle is type approved"),
            (f"{INF}TypeApprovedEquipment", INF_CONFIDENCE, "0.95"),
        ]
    )


def _test_question_strategy_ontology_index():
    return OntologyIndex(
        [
            (f"{SYN}order", INF_NAME, "medical order signed"),
            (f"{SYN}order", RDF_TYPE, f"{INF}DmeEvidence"),
            (f"{INF}DmeEvidence", RDFS_SUBCLASS_OF, f"{INF}EligibleEvidence"),
            (f"{INF}EligibleEvidence", INF_NAME, "benefit evidence available"),
            (f"{INF}EligibleEvidence", INF_CONFIDENCE, "0.95"),
        ]
    )


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
        assert engine.get_assessment() is assessment

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

    def test_list_type_wraps_scalar_answer(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("current employee", FactValueType.LIST)
        assert fv.get_value() == ["current employee"]
        assert fv.get_value_type() == FactValueType.LIST

    def test_unknown_type_returns_none(self):
        engine = InferenceEngine()
        fv = engine._create_fact_value("x", FactValueType.WARNING)
        assert fv is None


class TestQuestionShape:
    def test_value_conclusion_question_uses_declared_input_type(self):
        node = _make_node(
            node_name="person agrees",
            variable_name="person agrees",
            line_type=LineType.VALUE_CONCLUSION,
            is_plain_statement=True,
        )
        ns = _make_node_set(
            nodes={"person agrees": node},
            fact_dict={},
            id_dict={0: "person agrees"},
        )
        ns.get_input_dictionary.return_value = {
            "person agrees": FactValue(None, FactValueType.BOOLEAN)
        }
        engine = InferenceEngine(ns)

        assert engine.get_questions_from_node_to_be_asked(node) == ["person agrees"]
        assert engine.find_type_of_element_to_be_asked(node)["person agrees"] == FactValueType.BOOLEAN

    def test_is_in_list_question_uses_variable_name_not_node_name(self):
        node = _make_node(
            node_name="service type IS IN LIST: DVA operational service type",
            variable_name="service type",
            line_type=LineType.VALUE_CONCLUSION,
            is_plain_statement=False,
            fact_value=FactValue("DVA operational service type"),
        )
        ns = _make_node_set(
            nodes={node.get_node_name(): node},
            fact_dict={},
            id_dict={0: node.get_node_name()},
        )
        ns.get_input_dictionary.return_value = {
            "service type": FactValue([], FactValueType.LIST)
        }
        engine = InferenceEngine(ns)

        assert engine.get_questions_from_node_to_be_asked(node) == ["service type"]
        assert engine.find_type_of_element_to_be_asked(node)["service type"] == FactValueType.LIST

    def test_comparison_question_uses_lhs_declared_type(self):
        node = _make_node(
            node_name="period of service in days >= threshold",
            variable_name="period of service in days",
            line_type=LineType.COMPARISON,
            fact_value=FactValue(True, FactValueType.BOOLEAN),
        )
        node.get_lhs.return_value = "period of service in days"
        node.get_rhs.return_value = FactValue("threshold")
        ns = _make_node_set(
            nodes={node.get_node_name(): node},
            fact_dict={"threshold": FactValue(365, FactValueType.INTEGER)},
            id_dict={0: node.get_node_name()},
        )
        ns.get_input_dictionary.return_value = {
            "period of service in days": FactValue(None, FactValueType.DOUBLE)
        }
        engine = InferenceEngine(ns)

        question_types = engine.find_type_of_element_to_be_asked(node)

        assert engine.get_questions_from_node_to_be_asked(node) == ["period of service in days"]
        assert question_types["period of service in days"] == FactValueType.DOUBLE
        assert question_types["period of service in days >= threshold"] == FactValueType.BOOLEAN

    def test_iterate_prefixed_question_uses_base_declared_type(self):
        node = _make_node(
            node_name="1st  service period  period of service in days >= threshold",
            variable_name="1st  service period  period of service in days",
            line_type=LineType.COMPARISON,
            fact_value=FactValue(True, FactValueType.BOOLEAN),
        )
        node.get_lhs.return_value = "1st  service period  period of service in days"
        node.get_rhs.return_value = FactValue("threshold")
        ns = _make_node_set(
            nodes={node.get_node_name(): node},
            fact_dict={"threshold": FactValue(30, FactValueType.INTEGER)},
            id_dict={0: node.get_node_name()},
        )
        ns.get_input_dictionary.return_value = {
            "period of service in days": FactValue(None, FactValueType.DOUBLE)
        }
        engine = InferenceEngine(ns)

        question_types = engine.find_type_of_element_to_be_asked(node)

        assert question_types["1st  service period  period of service in days"] == FactValueType.DOUBLE


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
        assert engine.get_assessment_state().get_working_memory()["target_var"].get_value() == 42

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
        engine.reset_working_memory_and_inclusive_list()
        assert engine.get_assessment_state().get_working_memory() == {}

    def test_empty_already(self):
        engine = InferenceEngine()
        engine.reset_working_memory_and_inclusive_list()
        assert engine.get_assessment_state().get_inclusive_list() == []
        assert engine.get_assessment_state().get_inclusive_list() == []


class TestEditAnswer:
    def test_removes_answer_and_downstream_facts_from_layered_memory(self):
        engine = InferenceEngine()
        goal = _make_node(node_name="goal", variable_name="goal")
        assessment = Assessment()
        assessment._Assessment__assessment_name = "goal"
        assessment._Assessment__goal_node = goal
        assessment.set_node_to_be_asked(_make_node(node_name="stale"))
        assessment.set_aux_node_to_be_asked(_make_node(node_name="stale_aux"))
        engine.add_assessment_into_assessment_list(assessment)
        state = engine.get_assessment_state()
        state.set_fact("first question", FactValue(True))
        state.set_fact("edited question", FactValue(False))
        state.set_fact("goal", FactValue(False), source=FactSource.INFERRED)
        state.set_summary_list(["first question", "edited question", "goal"])
        state.set_inclusive_list(["goal", "edited question"])
        state.set_exclusive_list(["unused branch"])
        state.set_mandatory_list(["edited question"])

        engine.edit_answer("edited question")

        working_memory = state.get_working_memory()
        assert "first question" in working_memory
        assert "edited question" not in working_memory
        assert "goal" not in working_memory
        assert state.get_summary_list() == ["first question"]
        assert state.get_inclusive_list() == []
        assert state.get_exclusive_list() == []
        assert state.get_mandatory_list() == []
        assert assessment.get_node_to_be_asked() is None
        assert assessment.get_aux_node_to_be_asked() is None

    def test_unknown_question_raises_value_error(self):
        engine = InferenceEngine()
        try:
            engine.edit_answer("missing")
        except ValueError as exc:
            assert "has not been answered" in str(exc)
        else:
            raise AssertionError("Expected ValueError")


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

    def test_goal_fact_clears_stale_node_to_be_asked(self):
        goal = _make_node(node_id=0, node_name="goal", variable_name="goal")
        stale_question = _make_node(
            node_id=1,
            node_name="service type",
            variable_name="service type",
        )
        ns = _make_node_set(
            nodes={"goal": goal, "service type": stale_question},
            id_dict={0: "goal", 1: "service type"},
        )
        ns.get_sorted_node_list.return_value = [goal, stale_question]
        engine = InferenceEngine(ns)
        ass = Assessment()
        ass._Assessment__goal_node = goal
        ass._Assessment__goal_node_index = 0
        ass.set_node_to_be_asked(stale_question)
        ass.set_aux_node_to_be_asked(stale_question)
        engine.get_assessment_state().set_fact("goal", FactValue(True))

        result = engine.get_next_question(ass)

        assert result is None
        assert ass.get_node_to_be_asked() is None
        assert ass.get_aux_node_to_be_asked() is None

    def test_false_goal_fact_converges_when_mandatory_nodes_are_done(self):
        goal = _make_node(node_id=0, node_name="goal", variable_name="goal")
        ns = _make_node_set(nodes={"goal": goal}, id_dict={0: "goal"})
        engine = InferenceEngine(ns)
        ass = Assessment()
        ass._Assessment__goal_node = goal
        ass._Assessment__goal_node_index = 0
        engine.get_assessment_state().set_fact("goal", FactValue(False))

        assert engine._assessment_has_converged(ass) is True

    def test_answered_stale_question_is_not_returned_again(self):
        goal = _make_node(node_id=0, node_name="eligible", variable_name="eligible")
        stale_question = _make_node(
            node_id=1,
            node_name="service type IS IN LIST: allowed service types",
            variable_name="service type",
        )
        ns = _make_node_set(
            nodes={
                "eligible": goal,
                "service type IS IN LIST: allowed service types": stale_question,
            },
            id_dict={
                0: "eligible",
                1: "service type IS IN LIST: allowed service types",
            },
            edges=[
                (
                    "eligible",
                    "service type IS IN LIST: allowed service types",
                    DependencyType.get_and(),
                ),
            ],
        )
        ns.get_sorted_node_list.return_value = [goal, stale_question]
        engine = InferenceEngine(ns)
        ass = Assessment()
        ass._Assessment__goal_node = goal
        ass._Assessment__goal_node_index = 0
        ass.set_node_to_be_asked(stale_question)
        engine.get_assessment_state().set_fact("service type", FactValue("operational service"))

        result = engine.get_next_question(ass)

        assert result is None
        assert ass.get_node_to_be_asked() is None
        assert ass.get_aux_node_to_be_asked() is None

    def test_false_and_child_converges_goal_before_unrelated_questions(self):
        node_set = _parse_node_set(
            """
INPUT someone booked the celebrant AS BOOLEAN
INPUT the celebrant randomly turned up AS BOOLEAN
INPUT unrelated catering confirmed AS BOOLEAN

wedding can proceed
    AND celebrant available
    AND unrelated catering confirmed

celebrant available
    OR someone booked the celebrant
    OR the celebrant randomly turned up
""",
            "synthetic_wedding_false_convergence",
        )
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "wedding can proceed",
            "celebrant available",
            "someone booked the celebrant",
            "the celebrant randomly turned up",
            "unrelated catering confirmed",
        ]
        node_set.set_sorted_node_list([node_dict[name] for name in preferred_order])

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "wedding can proceed")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == [
            "someone booked the celebrant"
        ]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "someone booked the celebrant",
            False,
            FactValueType.BOOLEAN,
            assessment,
        )

        second_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(second_question) == [
            "the celebrant randomly turned up"
        ]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "the celebrant randomly turned up",
            False,
            FactValueType.BOOLEAN,
            assessment,
        )

        final_question = engine.get_next_question(assessment)
        working_memory = engine.get_assessment_state().get_working_memory()

        assert final_question is None
        assert working_memory["celebrant available"].get_value() is False
        assert working_memory["wedding can proceed"].get_value() is False
        assert "unrelated catering confirmed" not in working_memory
        assert assessment.get_node_to_be_asked() is None
        assert assessment.get_aux_node_to_be_asked() is None

    def test_deferred_question_is_skipped_without_asserting_fact(self):
        node_set = _parse_node_set(
            """
INPUT initial evidence AS BOOLEAN
INPUT fallback evidence AS BOOLEAN

goal met
    OR initial evidence
    OR fallback evidence
""",
            "synthetic_deferred_question_flow",
        )
        node_dict = node_set.get_node_dictionary()
        node_set.set_sorted_node_list(
            [
                node_dict["goal met"],
                node_dict["initial evidence"],
                node_dict["fallback evidence"],
            ]
        )

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "goal met")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == ["initial evidence"]

        engine.defer_question("initial evidence")
        second_question = engine.get_next_question(assessment)

        assert engine.get_deferred_questions() == ["initial evidence"]
        assert engine.get_questions_from_node_to_be_asked(second_question) == ["fallback evidence"]
        assert "initial evidence" not in engine.get_assessment_state().get_working_memory()

    def test_true_or_child_prunes_sibling_questions_after_parent_is_determined(self):
        node_set = _parse_node_set(
            """
INPUT someone booked the celebrant AS BOOLEAN
INPUT the celebrant randomly turned up AS BOOLEAN
INPUT unrelated catering confirmed AS BOOLEAN

wedding can proceed
    AND celebrant available
    AND unrelated catering confirmed

celebrant available
    OR someone booked the celebrant
    OR the celebrant randomly turned up
""",
            "synthetic_wedding_true_or_pruning",
        )
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "wedding can proceed",
            "celebrant available",
            "someone booked the celebrant",
            "the celebrant randomly turned up",
            "unrelated catering confirmed",
        ]
        node_set.set_sorted_node_list([node_dict[name] for name in preferred_order])

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "wedding can proceed")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == [
            "someone booked the celebrant"
        ]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "someone booked the celebrant",
            True,
            FactValueType.BOOLEAN,
            assessment,
        )

        next_question = engine.get_next_question(assessment)
        working_memory = engine.get_assessment_state().get_working_memory()

        assert working_memory["celebrant available"].get_value() is True
        assert engine.get_questions_from_node_to_be_asked(next_question) == [
            "unrelated catering confirmed"
        ]
        assert "the celebrant randomly turned up" not in engine.get_assessment_state().get_inclusive_list()
        assert any(
            event["nodeName"] == "the celebrant randomly turned up"
            and event["reason"] == "or_branch_satisfied"
            for event in engine.get_branch_prune_trace()
        )

    def test_false_and_parent_prunes_non_mandatory_subtrees_but_rescues_mandatory_nodes(self):
        node_set = _parse_node_set(
            """
INPUT A AS BOOLEAN
INPUT D AS BOOLEAN
INPUT E AS BOOLEAN
INPUT F AS BOOLEAN
INPUT G AS BOOLEAN
INPUT I AS BOOLEAN
INPUT J AS BOOLEAN

P
    AND A
    AND B
        AND D
        AND E
    AND C
        OR MANDATORY F
        OR G
    AND MANDATORY H
        AND I
        AND J
""",
            "synthetic_and_pruning_mandatory_rescue",
        )
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "P",
            "A",
            "B",
            "D",
            "E",
            "C",
            "F",
            "G",
            "H",
            "I",
            "J",
        ]
        node_set.set_sorted_node_list([node_dict[name] for name in preferred_order])

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "P")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == ["A"]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "A",
            False,
            FactValueType.BOOLEAN,
            assessment,
        )

        second_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(second_question) == ["F"]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "F",
            True,
            FactValueType.BOOLEAN,
            assessment,
        )

        third_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(third_question) == ["I"]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "I",
            False,
            FactValueType.BOOLEAN,
            assessment,
        )

        working_memory = engine.get_assessment_state().get_working_memory()
        final_question = engine.get_next_question(assessment)
        inclusive_list = engine.get_assessment_state().get_inclusive_list()
        mandatory_list = engine.get_assessment_state().get_mandatory_list()
        trace = engine.get_branch_prune_trace()

        assert final_question is None
        assert working_memory["P"].get_value() is False
        assert working_memory["F"].get_value() is True
        assert working_memory["H"].get_value() is False
        assert set(mandatory_list) == {"F", "H"}
        assert engine.get_assessment_state().all_mandatory_node_determined() is True
        assert "B" not in inclusive_list
        assert "C" not in inclusive_list
        assert "D" not in inclusive_list
        assert "E" not in inclusive_list
        assert "G" not in inclusive_list
        assert "J" not in inclusive_list
        assert any(
            event["nodeName"] == "C"
            and event["reason"] == "and_parent_failed"
            for event in trace
        )
        assert any(
            event["nodeName"] == "F"
            and event["reason"] == "mandatory_dependency_survived_pruning"
            for event in trace
        )
        assert any(
            event["nodeName"] == "H"
            and event["reason"] == "mandatory_dependency_survived_pruning"
            for event in trace
        )
        assert any(
            event["nodeName"] == "J"
            and event["reason"] == "and_parent_failed"
            for event in trace
        )

    def test_mandatory_or_child_survives_after_sibling_satisfies_parent(self):
        node_set = _parse_node_set(
            """
INPUT A AS BOOLEAN
INPUT B AS BOOLEAN

P
    OR MANDATORY A
    OR B
""",
            "synthetic_or_mandatory_survives_satisfied_parent",
        )
        node_dict = node_set.get_node_dictionary()
        node_set.set_sorted_node_list([node_dict[name] for name in ["P", "B", "A"]])

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "P")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == ["B"]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "B",
            True,
            FactValueType.BOOLEAN,
            assessment,
        )

        second_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(second_question) == ["A"]
        assert engine.get_assessment_state().get_working_memory()["P"].get_value() is True
        assert any(
            event["nodeName"] == "A"
            and event["reason"] == "mandatory_dependency_survived_pruning"
            for event in engine.get_branch_prune_trace()
        )

    def test_virtual_one_prunes_unselected_branch_after_discriminator(self):
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT incapacity status AS LIST
    ITEM current employee
    ITEM former employee
INPUT current employee evidence AS BOOLEAN
INPUT former employee evidence AS BOOLEAN

benefit met
    AND employment gateway virtual ONE
        OR current employee path
            AND incapacity status = "current employee"
            AND current employee evidence
        OR former employee path
            AND incapacity status = "former employee"
            AND former employee evidence
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("synthetic_drca_branch")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "benefit met",
            "employment gateway virtual ONE",
            "current employee path",
            "former employee path",
            'incapacity status = "current employee"',
            'incapacity status = "former employee"',
            "current employee evidence",
            "former employee evidence",
        ]
        node_set.set_sorted_node_list(
            [node_dict[name] for name in preferred_order]
            + [
                node
                for node in node_set.get_sorted_node_list()
                if node.get_node_name() not in preferred_order
            ]
        )

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == [
            "incapacity status"
        ]

        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "incapacity status",
            "current employee",
            FactValueType.LIST,
            assessment,
        )
        second_question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(second_question) == [
            "current employee evidence"
        ]
        assert "former employee evidence" not in engine.get_assessment_state().get_inclusive_list()
        assert any(
            event["nodeName"] == "former employee evidence"
            and event["reason"] == "parent_branch_false"
            for event in engine.get_branch_prune_trace()
        )

    def test_virtual_one_prunes_later_branch_before_nested_questions(self):
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT incapacity status AS LIST
    ITEM current employee
    ITEM other
INPUT current employee evidence AS BOOLEAN
INPUT normal weekly earnings AS NUMBER
INPUT actual earnings AS NUMBER
INPUT superannuation lump sum received AS BOOLEAN

benefit met
    AND incapacity gateway virtual ONE
        OR current employee path
            AND incapacity preliminary met
            AND incapacity status = "current employee"
            AND current employee evidence
        OR other cases path
            AND incapacity preliminary met
            AND incapacity status = "other"
            AND superannuation pathway virtual ONE
                OR superannuation lump sum path
                    AND superannuation lump sum received
                OR no superannuation path
                    AND NOT superannuation lump sum received

incapacity preliminary met
    AND KNOWN normal weekly earnings
    AND KNOWN actual earnings
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("synthetic_drca_later_branch")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "benefit met",
            "incapacity gateway virtual ONE",
            "current employee path",
            "other cases path",
            "incapacity preliminary met",
            "superannuation pathway virtual ONE",
            "superannuation lump sum path",
            "no superannuation path",
            "superannuation lump sum received",
            'incapacity status = "current employee"',
            'incapacity status = "other"',
            "current employee evidence",
            "normal weekly earnings",
            "actual earnings",
        ]
        node_set.set_sorted_node_list(
            [node_dict[name] for name in preferred_order]
            + [
                node
                for node in node_set.get_sorted_node_list()
                if node.get_node_name() not in preferred_order
            ]
        )

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(question) == [
            "incapacity status"
        ]

        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "incapacity status",
            "current employee",
            FactValueType.LIST,
            assessment,
        )
        question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(question) == [
            "current employee evidence"
        ]

        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "current employee evidence",
            True,
            FactValueType.BOOLEAN,
            assessment,
        )
        for question_name, answer in (
            ("normal weekly earnings", 1000),
            ("actual earnings", 500),
        ):
            question = engine.get_next_question(assessment)
            assert engine.get_questions_from_node_to_be_asked(question) == [
                question_name
            ]
            engine.feed_answer_to_node(
                assessment.get_node_to_be_asked(),
                question_name,
                answer,
                FactValueType.INTEGER,
                assessment,
            )

        next_question = engine.get_next_question(assessment)

        assert next_question is None
        assert "superannuation lump sum received" not in engine.get_assessment_state().get_inclusive_list()
        assert any(
            event["nodeName"] == "superannuation lump sum received"
            for event in engine.get_branch_prune_trace()
        )

    def test_mrca_target_scoped_virtual_one_questions_do_not_leak_chapter_flow(self):
        rule_path = Path("docs/reference/examples/mrca_chapter_1.txt")
        node_set = _parse_node_set(
            rule_path.read_text(),
            "mrca_chapter_1_target_scope",
        )
        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "reservist and cadet determinations met")
        engine.add_assessment_into_assessment_list(assessment)
        target_flow_nodes = {
            "reservist and cadet determinations met",
            "reservist pathway virtual ONE",
            "part time reservist path",
            "cadet path",
            "the person is a part time Reservist",
            "the person is a cadet",
            "unlikely to return to defence service",
            "commission determination required",
        }
        allowed_questions = {
            "the person is a part time Reservist",
            "the person is a cadet",
            "unlikely to return to defence service",
            "commission determination required",
        }
        rejected_questions = {
            "death resulted from service",
            "dependency status",
            "the person is a partner",
            "the person is an eligible young person",
        }
        answers = {
            "the person is a cadet": False,
            "the person is a part time Reservist": True,
            "unlikely to return to defence service": True,
            "commission determination required": True,
        }

        asked_questions = []
        for _ in range(len(answers) + 2):
            question = engine.get_next_question(assessment)
            if question is None:
                break
            question_name = engine.get_questions_from_node_to_be_asked(question)[0]
            asked_questions.append(question_name)
            assert question_name in allowed_questions
            assert question_name not in rejected_questions
            engine.feed_answer_to_node(
                question,
                question_name,
                answers[question_name],
                FactValueType.BOOLEAN,
                assessment,
            )

        state = engine.get_assessment_state()
        assert asked_questions == [
            "the person is a cadet",
            "the person is a part time Reservist",
            "unlikely to return to defence service",
            "commission determination required",
        ]
        assert rejected_questions.isdisjoint(asked_questions)
        assert set(state.get_inclusive_list()) <= target_flow_nodes
        assert state.get_mandatory_list() == ["commission determination required"]
        assert state.get_working_memory()["reservist and cadet determinations met"].get_value() is True
        assert engine.get_next_question(assessment) is None

    def test_global_non_leaf_mandatory_collects_only_unresolved_support(self):
        node_set = _parse_node_set(
            """
INPUT target evidence AS BOOLEAN
INPUT cheap mandatory evidence AS BOOLEAN
INPUT expensive mandatory evidence AS BOOLEAN
INPUT unrelated ordinary evidence AS BOOLEAN

target met
    AND target evidence

ordinary chapter prompt
    AND unrelated ordinary evidence

global mandatory root
    AND MANDATORY mandatory review met

mandatory review met
    AND mandatory support virtual ONE
        OR cheap support path
            AND cheap mandatory evidence
        OR expensive support path
            AND expensive mandatory evidence
""",
            "synthetic_global_non_leaf_mandatory",
        )
        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "target met")
        engine.add_assessment_into_assessment_list(assessment)
        answers = {
            "target evidence": True,
            "cheap mandatory evidence": True,
        }

        asked_questions = []
        for _ in range(len(answers) + 3):
            question = engine.get_next_question(assessment)
            if question is None:
                break
            question_name = engine.get_questions_from_node_to_be_asked(question)[0]
            asked_questions.append(question_name)
            engine.feed_answer_to_node(
                question,
                question_name,
                answers[question_name],
                FactValueType.BOOLEAN,
                assessment,
            )

        state = engine.get_assessment_state()
        assert asked_questions == [
            "target evidence",
            "cheap mandatory evidence",
        ]
        assert "mandatory review met" in state.get_mandatory_list()
        assert state.get_working_memory()["mandatory review met"].get_value() is True
        assert state.get_working_memory()["target met"].get_value() is True
        assert "expensive mandatory evidence" not in asked_questions
        assert "unrelated ordinary evidence" not in asked_questions
        assert engine.get_next_question(assessment) is None

    def test_ontology_auto_answer_disabled_preserves_question_flow(self):
        node_set = _parse_node_set(
            """
INPUT incapacity status AS LIST
    ITEM current employee

benefit met
    AND incapacity status = "current employee"
""",
            "synthetic_ontology_auto_answer_disabled",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_auto_answer=False,
            ),
        )
        engine.configure_ontology_auto_answer(
            {
                "incapacity status": [
                    {
                        "factName": "incapacity status",
                        "relationship": "inf:defaultValue",
                        "suggestedValue": "current employee",
                        "confidence": 1.0,
                        "ontologySnapshotHash": "hash-1",
                    }
                ]
            },
            ontology_snapshot_hash="hash-1",
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(question) == [
            "incapacity status"
        ]
        assert "incapacity status" not in engine.get_assessment_state().get_working_memory()

    def test_ontology_auto_answer_applies_confident_default_without_question(self):
        node_set = _parse_node_set(
            """
INPUT incapacity status AS LIST
    ITEM current employee

benefit met
    AND incapacity status = "current employee"
""",
            "synthetic_ontology_auto_answer_enabled",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_auto_answer=True,
                ontology_auto_answer_confidence_threshold=0.85,
            ),
        )
        engine.configure_ontology_auto_answer(
            {
                "incapacity status": [
                    {
                        "factName": "incapacity status",
                        "relationship": "inf:defaultValue",
                        "suggestedValue": "current employee",
                        "confidence": 0.95,
                        "ontologySnapshotRef": "rule:hash-1",
                        "ontologySnapshotHash": "hash-1",
                        "basis": "explicit_default_value",
                    }
                ]
            },
            ontology_snapshot_hash="hash-1",
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)
        working_memory = engine.get_assessment_state().get_working_memory()

        assert question is None
        assert working_memory["incapacity status"].get_value() == ["current employee"]
        assert FactSource.ASSERTED in engine.get_assessment_state().get_fact_sources(
            "incapacity status"
        )
        assert working_memory["benefit met"].get_value() is True
        trace = engine.get_ontology_auto_answer_trace()
        assert trace[0]["status"] == "auto_answered"
        assert trace[0]["factSource"] == "ASSERTED"

    def test_ontology_auto_answer_low_confidence_falls_back_to_question(self):
        node_set = _parse_node_set(
            """
INPUT incapacity status AS LIST
    ITEM current employee

benefit met
    AND incapacity status = "current employee"
""",
            "synthetic_ontology_auto_answer_low_confidence",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_auto_answer=True,
                ontology_auto_answer_confidence_threshold=0.85,
            ),
        )
        engine.configure_ontology_auto_answer(
            {
                "incapacity status": [
                    {
                        "factName": "incapacity status",
                        "relationship": "inf:defaultValue",
                        "suggestedValue": "current employee",
                        "confidence": 0.5,
                        "ontologySnapshotHash": "hash-1",
                    }
                ]
            },
            ontology_snapshot_hash="hash-1",
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(question) == [
            "incapacity status"
        ]
        assert "incapacity status" not in engine.get_assessment_state().get_working_memory()
        assert engine.get_ontology_auto_answer_trace()[0]["reason"] == (
            "below_confidence_threshold"
        )

    def test_ontology_auto_answer_stale_snapshot_falls_back_to_question(self):
        node_set = _parse_node_set(
            """
INPUT incapacity status AS LIST
    ITEM current employee

benefit met
    AND incapacity status = "current employee"
""",
            "synthetic_ontology_auto_answer_stale_snapshot",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_auto_answer=True,
            ),
        )
        engine.configure_ontology_auto_answer(
            {
                "incapacity status": [
                    {
                        "factName": "incapacity status",
                        "relationship": "inf:defaultValue",
                        "suggestedValue": "current employee",
                        "confidence": 1.0,
                        "ontologySnapshotHash": "old-hash",
                    }
                ]
            },
            ontology_snapshot_hash="new-hash",
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(question) == [
            "incapacity status"
        ]
        assert engine.get_ontology_auto_answer_trace()[0]["reason"] == (
            "stale_or_unversioned_ontology_snapshot"
        )

    def test_ontology_auto_answer_never_overwrites_asserted_fact(self):
        node_set = _parse_node_set(
            """
INPUT incapacity status AS LIST
    ITEM current employee
    ITEM former employee

benefit met
    AND incapacity status = "former employee"
""",
            "synthetic_ontology_auto_answer_asserted_guard",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_auto_answer=True,
            ),
        )
        engine.configure_ontology_auto_answer(
            {
                "incapacity status": [
                    {
                        "factName": "incapacity status",
                        "relationship": "inf:defaultValue",
                        "suggestedValue": "current employee",
                        "confidence": 1.0,
                        "ontologySnapshotHash": "hash-1",
                    }
                ]
            },
            ontology_snapshot_hash="hash-1",
        )
        engine.get_assessment_state().set_fact(
            "incapacity status",
            FactValue(["former employee"], FactValueType.LIST),
            source=FactSource.ASSERTED,
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        engine.get_next_question(assessment)

        fact = engine.get_assessment_state().get_working_memory()["incapacity status"]
        assert fact.get_value() == ["former employee"]

    def test_ontology_reasoning_disabled_preserves_question_flow(self):
        node_set = _parse_node_set(
            """
INPUT vehicle classification AS STRING

benefit met
    AND vehicle classification = "forklift"
    AND vehicle is type approved
""",
            "synthetic_ontology_reasoning_disabled",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_reasoning=False,
            ),
        )
        engine.configure_ontology_reasoner(
            _test_ontology_reasoner(),
            _test_vehicle_ontology_index(),
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        assert engine.get_questions_from_node_to_be_asked(first_question) == [
            "vehicle classification"
        ]
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "vehicle classification",
            "forklift",
            FactValueType.STRING,
            assessment,
        )
        second_question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(second_question) == [
            "vehicle is type approved"
        ]
        assert engine.get_ontology_materialization_trace() == []
        assert engine.get_assessment_state().get_fact_store().peek_in_layer(
            "vehicle is type approved",
            FactSource.INFERRED,
        ) is None

    def test_ontology_reasoning_materializes_inferred_fact_and_cascades(self):
        node_set = _parse_node_set(
            """
INPUT vehicle classification AS STRING

benefit met
    AND vehicle classification = "forklift"
    AND vehicle is type approved
""",
            "synthetic_ontology_reasoning_enabled",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_reasoning=True,
                ontology_reasoning_confidence_threshold=0.85,
            ),
        )
        engine.configure_ontology_reasoner(
            _test_ontology_reasoner(),
            _test_vehicle_ontology_index(),
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)
        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "vehicle classification",
            "forklift",
            FactValueType.STRING,
            assessment,
        )
        next_question = engine.get_next_question(assessment)
        working_memory = engine.get_assessment_state().get_working_memory()

        assert engine.get_questions_from_node_to_be_asked(first_question) == [
            "vehicle classification"
        ]
        assert next_question is None
        assert working_memory["vehicle is type approved"].get_value() is True
        assert FactSource.INFERRED in engine.get_assessment_state().get_fact_sources(
            "vehicle is type approved"
        )
        assert working_memory["benefit met"].get_value() is True
        trace = [
            item
            for item in engine.get_ontology_materialization_trace()
            if item["status"] == "materialized"
        ]
        assert trace[0]["factName"] == "vehicle is type approved"
        assert trace[0]["factSource"] == "INFERRED"
        assert trace[0]["materializedInference"] is True
        assert trace[0]["ontologySnapshotHash"] == "hash"
        assert engine.get_ontology_derived_facts() == ["vehicle is type approved"]

    def test_asserted_false_child_short_circuits_without_ontology_overwrite(self):
        node_set = _parse_node_set(
            """
INPUT vehicle classification AS STRING

benefit met
    AND vehicle classification = "forklift"
    AND vehicle is type approved
""",
            "synthetic_ontology_reasoning_asserted_guard",
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(
                ontology_advisory_enabled=True,
                ontology_reasoning=True,
            ),
        )
        engine.configure_ontology_reasoner(
            _test_ontology_reasoner(),
            _test_vehicle_ontology_index(),
        )
        engine.get_assessment_state().set_fact(
            "vehicle is type approved",
            FactValue(False),
            source=FactSource.ASSERTED,
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        next_question = engine.get_next_question(assessment)
        working_memory = engine.get_assessment_state().get_working_memory()

        asserted = engine.get_assessment_state().get_fact_store().peek_in_layer(
            "vehicle is type approved",
            FactSource.ASSERTED,
        )
        assert next_question is None
        assert working_memory["benefit met"].get_value() is False
        assert asserted.get_value() is False
        assert engine.get_assessment_state().get_fact_store().peek_in_layer(
            "vehicle is type approved",
            FactSource.INFERRED,
        ) is None
        assert engine.get_ontology_materialization_trace() == []

    def test_ontology_question_strategy_disabled_preserves_question_order(self):
        node_set = _parse_node_set(
            """
INPUT medical order signed AS BOOLEAN

benefit met
    AND benefit evidence available
    AND medical order signed
""",
            "synthetic_semantic_question_strategy_disabled",
        )
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "benefit met",
            "benefit evidence available",
            "medical order signed",
        ]
        node_set.set_sorted_node_list(
            [node_dict[name] for name in preferred_order]
            + [
                node
                for node in node_set.get_sorted_node_list()
                if node.get_node_name() not in preferred_order
            ]
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(ontology_question_strategy=False),
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(question) == [
            "benefit evidence available"
        ]
        assert engine.get_semantic_question_strategy_trace() == []

    def test_ontology_question_strategy_enabled_reorders_frontier_with_trace(self):
        node_set = _parse_node_set(
            """
INPUT medical order signed AS BOOLEAN

benefit met
    AND benefit evidence available
    AND medical order signed
""",
            "synthetic_semantic_question_strategy_enabled",
        )
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            "benefit met",
            "benefit evidence available",
            "medical order signed",
        ]
        node_set.set_sorted_node_list(
            [node_dict[name] for name in preferred_order]
            + [
                node
                for node in node_set.get_sorted_node_list()
                if node.get_node_name() not in preferred_order
            ]
        )
        engine = InferenceEngine(
            node_set,
            feature_flags=FeatureFlags(ontology_question_strategy=True),
        )
        engine.set_question_strategy(
            SemanticQuestionStrategy(
                reasoner=_test_ontology_reasoner(),
                ontology_index=_test_question_strategy_ontology_index(),
                fact_store=engine.get_assessment_state().get_fact_store(),
            )
        )
        assessment = Assessment(node_set, "benefit met")
        engine.add_assessment_into_assessment_list(assessment)

        question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(question) == [
            "medical order signed"
        ]
        trace = engine.get_semantic_question_strategy_trace()
        assert trace[0]["questionName"] == "benefit evidence available"
        assert trace[0]["action"] == "pruned"
        assert trace[0]["missingPrerequisites"] == ["medical order signed"]
        assert trace[1]["questionName"] == "medical order signed"
        assert trace[1]["action"] == "selected"
        assert trace[1]["expectedInformationGain"] == 1

    def test_ontology_strategy_can_skip_unreachable_branch(self):
        goal = _make_node(node_id=0, node_name="goal", variable_name="goal")
        unreachable = _make_node(
            node_id=1,
            node_name="clinical_note_branch",
            variable_name="clinical_note_available",
        )
        reachable = _make_node(
            node_id=2,
            node_name="face_to_face_branch",
            variable_name="face_to_face_exam_documented",
        )
        ns = _make_node_set(
            nodes={
                "goal": goal,
                "clinical_note_branch": unreachable,
                "face_to_face_branch": reachable,
            },
            id_dict={
                0: "goal",
                1: "clinical_note_branch",
                2: "face_to_face_branch",
            },
            edges=[
                ("goal", "clinical_note_branch", DependencyType.get_and()),
                ("goal", "face_to_face_branch", DependencyType.get_and()),
            ],
        )

        baseline = InferenceEngine(node_set=ns)
        baseline_assessment = Assessment()
        baseline_assessment._Assessment__goal_node = goal
        baseline_assessment._Assessment__goal_node_index = 0
        assert baseline.get_next_question(baseline_assessment) is unreachable

        strategy = OntologyReachabilityQuestionStrategy(
            [
                ReachabilityEvidence(
                    fact_name="clinical_note_available",
                    reachable=False,
                    reason="not connected to the DME request class",
                    ontology_snapshot_ref="synthetic-pa-ontology-v1",
                ),
                ReachabilityEvidence(
                    fact_name="face_to_face_exam_documented",
                    reachable=True,
                    reason="reachable DME documentation evidence",
                    ontology_snapshot_ref="synthetic-pa-ontology-v1",
                ),
            ]
        )
        guided = InferenceEngine(node_set=ns, question_strategy=strategy)
        guided_assessment = Assessment()
        guided_assessment._Assessment__goal_node = goal
        guided_assessment._Assessment__goal_node_index = 0

        assert guided.get_next_question(guided_assessment) is reachable
        trace = list(strategy.get_trace())
        assert trace[0]["questionName"] == "clinical_note_available"
        assert trace[0]["action"] == "skipped"


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
        engine.get_assessment_state().get_inclusive_list().append("parent_node")
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
    def test_no_graph_returns_false(self):
        engine = InferenceEngine()
        node = _make_node()
        assert engine._can_determine(node, LineType.VALUE_CONCLUSION) is False
        assert engine._can_determine(node, LineType.COMPARISON) is False

    def test_value_conclusion_and_children_true_sets_fact(self):
        parent = _make_node(node_name="parent", variable_name="parent", is_plain_statement=True)
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[("parent", "child", DependencyType.get_and())],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("child", FactValue(True))

        assert engine._can_determine(parent, LineType.VALUE_CONCLUSION) is True
        assert engine.get_assessment_state().get_working_memory()["parent"].get_value() is True
        assert engine.get_assessment_state().get_fact_sources("parent") == {FactSource.INFERRED}

    def test_value_conclusion_and_child_false_sets_false_fact(self):
        parent = _make_node(node_name="parent", variable_name="parent", is_plain_statement=True)
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[("parent", "child", DependencyType.get_and())],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("child", FactValue(False))

        assert engine._can_determine(parent, LineType.VALUE_CONCLUSION) is True
        assert engine.get_assessment_state().get_working_memory()["parent"].get_value() is False

    def test_value_conclusion_and_false_child_settles_with_unknown_optional_sibling(self):
        parent = _make_node(node_name="parent", variable_name="parent", is_plain_statement=True)
        mandatory_child = _make_node(node_name="mandatory_child", variable_name="mandatory_child")
        optional_child = _make_node(node_name="optional_child", variable_name="optional_child")
        ns = _make_node_set(
            nodes={
                "parent": parent,
                "mandatory_child": mandatory_child,
                "optional_child": optional_child,
            },
            edges=[
                (
                    "parent",
                    "mandatory_child",
                    DependencyType.get_mandatory() | DependencyType.get_and(),
                ),
                (
                    "parent",
                    "optional_child",
                    DependencyType.get_optional() | DependencyType.get_and(),
                ),
            ],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("mandatory_child", FactValue(False))

        assert engine._can_determine(parent, LineType.VALUE_CONCLUSION) is True
        assert engine.get_assessment_state().get_working_memory()["parent"].get_value() is False

    def test_value_conclusion_false_child_retains_explicit_mandatory_nodes(self):
        gateway = _make_node(node_name="branch gateway", variable_name="branch gateway", is_plain_statement=True)
        parent = _make_node(node_name="former branch", variable_name="former branch", is_plain_statement=True)
        selected_parent = _make_node(node_name="current branch", variable_name="current branch", is_plain_statement=True)
        false_child = _make_node(node_name="incapacity status = former", variable_name="incapacity status")
        branch_only_child = _make_node(node_name="step down percentage", variable_name="step down percentage")
        related_calc = _make_node(
            node_name="step down percentage IS CALC (weeks of incapacity <= 45 ? 100 : 75)",
            variable_name="step down percentage",
        )
        calc_input = _make_node(node_name="weeks of incapacity", variable_name="weeks of incapacity")
        shared_child = _make_node(node_name="normal weekly earnings >= actual earnings", variable_name="normal weekly earnings")
        ns = _make_node_set(
            nodes={
                "branch gateway": gateway,
                "former branch": parent,
                "current branch": selected_parent,
                "incapacity status = former": false_child,
                "step down percentage": branch_only_child,
                "step down percentage IS CALC (weeks of incapacity <= 45 ? 100 : 75)": related_calc,
                "weeks of incapacity": calc_input,
                "normal weekly earnings >= actual earnings": shared_child,
            },
            edges=[
                ("branch gateway", "former branch", DependencyType.get_or()),
                ("former branch", "incapacity status = former", DependencyType.get_and()),
                ("former branch", "step down percentage", DependencyType.get_and()),
                ("former branch", "normal weekly earnings >= actual earnings", DependencyType.get_and()),
                ("current branch", "normal weekly earnings >= actual earnings", DependencyType.get_and()),
                (
                    "step down percentage IS CALC (weeks of incapacity <= 45 ? 100 : 75)",
                    "weeks of incapacity",
                    DependencyType.get_mandatory() | DependencyType.get_and(),
                ),
            ],
        )
        engine = InferenceEngine(ns)
        state = engine.get_assessment_state()
        state.set_fact("incapacity status = former", FactValue(False))
        state.set_inclusive_list([
            "step down percentage",
            "normal weekly earnings >= actual earnings",
        ])
        state.set_mandatory_list([
            "step down percentage",
            "weeks of incapacity",
            "normal weekly earnings >= actual earnings",
        ])

        assert engine._can_determine(parent, LineType.VALUE_CONCLUSION) is True

        assert state.get_working_memory()["former branch"].get_value() is False
        assert "step down percentage" in state.get_inclusive_list()
        assert "step down percentage" in state.get_mandatory_list()
        assert "weeks of incapacity" in state.get_mandatory_list()
        assert "normal weekly earnings >= actual earnings" in state.get_inclusive_list()
        assert "normal weekly earnings >= actual earnings" in state.get_mandatory_list()
        retained_nodes = {
            event["nodeName"]
            for event in engine.get_branch_prune_trace()
            if event["action"] == "retained"
        }
        assert "step down percentage" in retained_nodes
        assert "normal weekly earnings >= actual earnings" in retained_nodes

    def test_value_conclusion_or_children_waits_for_missing_facts(self):
        parent = _make_node(node_name="parent", variable_name="parent", is_plain_statement=True)
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[("parent", "child", DependencyType.get_or())],
        )
        engine = InferenceEngine(ns)

        assert engine._can_determine(parent, LineType.VALUE_CONCLUSION) is False
        assert "parent" not in engine.get_assessment_state().get_working_memory()

    def test_comparison_child_dependencies_do_not_determine_comparison_truth(self):
        parent = _make_node(
            node_name="parent",
            variable_name="parent",
            line_type=LineType.COMPARISON,
        )
        parent.self_evaluate.return_value = None
        child = _make_node(node_name="child", variable_name="child")
        sibling = _make_node(node_name="sibling", variable_name="sibling")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child, "sibling": sibling},
            edges=[
                ("parent", "child", DependencyType.get_or()),
                ("parent", "sibling", DependencyType.get_or()),
            ],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("child", FactValue(False))

        assert engine._compute_parent_truth_from_children("parent") is None
        assert engine._has_children("parent") is False
        assert "parent" not in engine.get_assessment_state().get_working_memory()

    def test_comparison_operand_reference_is_not_logical_child_or_inferred(self):
        rule_text = """
FIXED DRCA commencement date IS 1/12/1988
INPUT date of injury or onset AS DATE

DRCA temporal application met
    AND date of injury or onset >= DRCA commencement date
"""
        node_set = _parse_node_set(rule_text, "drca_temporal_regression")
        comparison_name = "date of injury or onset >= DRCA commencement date"
        graph = node_set.get_graph()

        assert graph.get_children_flat(comparison_name) == ()

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "DRCA temporal application met")
        engine.add_assessment_into_assessment_list(assessment)

        result = engine._compute_parent_truth_from_children("DRCA temporal application met")
        working_memory = engine.get_assessment_state().get_working_memory()

        assert result is None
        assert "date of injury or onset" not in working_memory
        assert working_memory["DRCA commencement date"].get_value() == "01/12/1988"
        assert comparison_name not in working_memory

    def test_comparison_and_child_false_waits_for_unknown_sibling(self):
        parent = _make_node(
            node_name="parent",
            variable_name="parent",
            line_type=LineType.COMPARISON,
        )
        parent.self_evaluate.return_value = FactValue(True)
        child = _make_node(node_name="child", variable_name="child")
        sibling = _make_node(node_name="sibling", variable_name="sibling")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child, "sibling": sibling},
            edges=[
                ("parent", "child", DependencyType.get_and()),
                ("parent", "sibling", DependencyType.get_and()),
            ],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("child", FactValue(False))

        assert engine._can_determine(parent, LineType.COMPARISON) is False
        assert "parent" not in engine.get_assessment_state().get_working_memory()


class TestComputeParentTruthFromChildren:
    def test_known_dependency_uses_fact_presence_not_fact_truth(self):
        parent = _make_node(node_name="parent", variable_name="parent")
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[("parent", "child", DependencyType.get_known() | DependencyType.get_and())],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("child", FactValue(False))

        result = engine._compute_parent_truth_from_children("parent")

        assert result.get_value() is True

    def test_known_declared_input_waits_for_answer_when_missing(self):
        parent = _make_node(node_name="parent", variable_name="parent")
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[("parent", "child", DependencyType.get_known() | DependencyType.get_and())],
        )
        ns.get_input_dictionary.return_value = {
            "child": FactValue(None, FactValueType.STRING)
        }
        engine = InferenceEngine(ns)

        result = engine._compute_parent_truth_from_children("parent")

        assert result is None

    def test_not_known_dependency_is_true_when_fact_absent(self):
        parent = _make_node(node_name="parent", variable_name="parent")
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[
                (
                    "parent",
                    "child",
                    DependencyType.get_not() | DependencyType.get_known() | DependencyType.get_and(),
                )
            ],
        )
        engine = InferenceEngine(ns)

        result = engine._compute_parent_truth_from_children("parent")

        assert result.get_value() is True

    def test_missing_known_inputs_do_not_false_vea_convergence_after_hazard_answer(self):
        rule_text = """
INPUT the person has rendered hazardous service AS BOOLEAN
INPUT ministerial declaration date AS DATE
INPUT operational area name AS TEXT
INPUT service rendered in declared operational area AS BOOLEAN

VEA Part II sections 7 to 7C convergence met
    AND hazardous service gateway met
        AND the person has rendered hazardous service
    AND operational area gateway met
        AND the ministerial declaration is valid
        AND the operational area matches DVA classification

the ministerial declaration is valid
    AND KNOWN ministerial declaration date

the operational area matches DVA classification
    AND KNOWN operational area name
    AND service rendered in declared operational area
"""
        node_set = _parse_node_set(rule_text, "synthetic_vea_7_to_7c_known_inputs")
        engine = InferenceEngine(node_set)
        goal = "VEA Part II sections 7 to 7C convergence met"
        assessment = Assessment(node_set, goal)
        engine.add_assessment_into_assessment_list(assessment)

        answer_node = node_set.get_node_dictionary()["the person has rendered hazardous service"]
        assessment.set_node_to_be_asked(answer_node)
        engine.feed_answer_to_node(
            answer_node,
            "the person has rendered hazardous service",
            True,
            FactValueType.BOOLEAN,
            assessment,
        )

        working_memory = engine.get_assessment_state().get_working_memory()
        assert goal not in working_memory
        assert "operational area gateway met" not in working_memory

        next_question = engine.get_next_question(assessment)

        assert next_question is not None
        assert engine.get_questions_from_node_to_be_asked(next_question)[0] in {
            "ministerial declaration date",
            "operational area name",
            "service rendered in declared operational area",
        }

    def test_not_and_dependency_negates_each_child_before_grouping(self):
        parent = _make_node(node_name="parent", variable_name="parent")
        first = _make_node(node_name="first", variable_name="first")
        second = _make_node(node_name="second", variable_name="second")
        ns = _make_node_set(
            nodes={"parent": parent, "first": first, "second": second},
            edges=[
                (
                    "parent",
                    "first",
                    DependencyType.get_not() | DependencyType.get_and(),
                ),
                (
                    "parent",
                    "second",
                    DependencyType.get_not() | DependencyType.get_and(),
                ),
            ],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("first", FactValue(False))
        engine.get_assessment_state().set_fact("second", FactValue(True))

        result = engine._compute_parent_truth_from_children("parent")

        assert result.get_value() is False

    def test_parent_truth_materializes_determinable_child_parent(self):
        parent = _make_node(node_name="parent", variable_name="parent")
        child_parent = _make_node(node_name="child parent", variable_name="child parent")
        leaf = _make_node(node_name="leaf", variable_name="leaf")
        ns = _make_node_set(
            nodes={
                "parent": parent,
                "child parent": child_parent,
                "leaf": leaf,
            },
            edges=[
                ("parent", "child parent", DependencyType.get_and()),
                ("child parent", "leaf", DependencyType.get_and()),
            ],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact("leaf", FactValue(True))

        result = engine._compute_parent_truth_from_children("parent")

        assert result.get_value() is True
        assert engine.get_assessment_state().get_working_memory()["child parent"].get_value() is True

    def test_parent_truth_recomputes_stale_inferred_child_parent(self):
        goal = _make_node(node_name="goal", variable_name="goal")
        branch_parent = _make_node(node_name="branch parent", variable_name="branch parent")
        first_branch = _make_node(node_name="first branch", variable_name="first branch")
        second_branch = _make_node(node_name="second branch", variable_name="second branch")
        ns = _make_node_set(
            nodes={
                "goal": goal,
                "branch parent": branch_parent,
                "first branch": first_branch,
                "second branch": second_branch,
            },
            edges=[
                ("goal", "branch parent", DependencyType.get_and()),
                ("branch parent", "first branch", DependencyType.get_or()),
                ("branch parent", "second branch", DependencyType.get_or()),
            ],
        )
        engine = InferenceEngine(ns)
        state = engine.get_assessment_state()
        state.set_fact("branch parent", FactValue(False), source=FactSource.INFERRED)
        state.set_fact("first branch", FactValue(False), source=FactSource.INFERRED)
        state.set_fact("second branch", FactValue(True), source=FactSource.INFERRED)

        result = engine._compute_parent_truth_from_children("goal")

        assert result.get_value() is True
        assert state.get_working_memory()["branch parent"].get_value() is True

    def test_semantic_only_fact_does_not_satisfy_mandatory_dependency(self):
        parent = _make_node(node_name="parent", variable_name="parent", is_plain_statement=True)
        child = _make_node(node_name="child", variable_name="child")
        ns = _make_node_set(
            nodes={"parent": parent, "child": child},
            edges=[("parent", "child", DependencyType.get_mandatory() | DependencyType.get_and())],
        )
        engine = InferenceEngine(ns)
        engine.get_assessment_state().set_fact(
            "child",
            FactValue(True),
            source=FactSource.SEMANTIC,
        )

        result = engine._compute_parent_truth_from_children("parent")

        assert result is None
        assert engine._can_determine(parent, LineType.VALUE_CONCLUSION) is False
        assert "parent" not in engine.get_assessment_state().get_working_memory()


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
        assert ass.get_node_to_be_asked() is None
        assert ass.get_aux_node_to_be_asked() is None

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
        engine.get_assessment_state().get_inclusive_list().append("iter_node")
        with patch.object(engine, '_handle_iterate_node', return_value=True, create=True):
            result = engine._should_ask_node(node, ass, 0)
            assert result is True

    def test_handle_iterate_node_sets_active_iterate_and_aux_question(self):
        engine = InferenceEngine()
        iterate_node = _make_node(node_id=0, line_type=LineType.ITERATE, node_name="iter_node")
        sub_question = _make_node(node_id=1, node_name="1st  item  eligible")
        iterate_node.get_iterate_next_question.return_value = sub_question
        ns = _make_node_set(
            nodes={"iter_node": iterate_node, "1st  item  eligible": sub_question},
            id_dict={0: "iter_node", 1: "1st  item  eligible"},
        )
        engine.set_node_set(ns)
        ass = Assessment()

        result = engine._handle_iterate_node(iterate_node, ass, 3)

        assert result is True
        assert ass.get_node_to_be_asked() is iterate_node
        assert ass.get_aux_node_to_be_asked() is sub_question
        iterate_node.get_iterate_next_question.assert_called_once_with(
            ns,
            engine.get_assessment_state(),
        )

    def test_handle_iterate_node_self_evaluates_when_no_sub_question_remains(self):
        engine = InferenceEngine()
        iterate_node = _make_node(node_id=0, line_type=LineType.ITERATE, node_name="iter_node")
        iterate_node.get_iterate_next_question.return_value = None
        iterate_node.can_be_self_evaluated.return_value = True
        iterate_node.self_evaluate.return_value = FactValue(True)
        ns = _make_node_set(nodes={"iter_node": iterate_node}, id_dict={0: "iter_node"})
        engine.set_node_set(ns)

        result = engine._handle_iterate_node(iterate_node, Assessment(), 0)

        assert result is False
        assert engine.get_assessment_state().get_working_memory()["iter_node"].get_value() is True

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

    def test_goal_fact_clears_stale_iterate_question(self):
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
        assert result is None
        assert ass.get_node_to_be_asked() is None
        assert ass.get_aux_node_to_be_asked() is None

    def test_get_next_question_returns_iterate_sub_question(self):
        engine = InferenceEngine()
        goal = _make_node(node_id=0, node_name="goal", variable_name="goal")
        iterate_node = _make_node(
            node_id=1,
            line_type=LineType.ITERATE,
            node_name="iter_rule",
            variable_name="items",
        )
        sub_question = _make_node(node_id=2, node_name="1st  items  eligible")
        iterate_node.get_iterate_next_question.return_value = sub_question
        ns = _make_node_set(
            nodes={
                "goal": goal,
                "iter_rule": iterate_node,
                "1st  items  eligible": sub_question,
            },
            id_dict={0: "goal", 1: "iter_rule", 2: "1st  items  eligible"},
            edges=[("goal", "iter_rule", DependencyType.get_and())],
        )
        ns.find_node_index.return_value = 0
        engine.set_node_set(ns)
        ass = Assessment()
        ass._Assessment__goal_node = goal
        ass._Assessment__goal_node_index = 0

        result = engine.get_next_question(ass)

        assert result is sub_question
        assert ass.get_node_to_be_asked() is iterate_node
        assert ass.get_aux_node_to_be_asked() is sub_question


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
        engine.get_assessment_state().get_inclusive_list().append("parent_node")
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
        engine.get_assessment_state().get_inclusive_list().append("n1")
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


class TestCollectionInIteration:
    def test_in_iteration_asks_size_from_before_item_fields(self):
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
TYPE service period
    FIELD period of service in days AS NUMBER

INPUT number of service periods AS NUMBER
INPUT service history AS COLLECTION OF service period
    SIZE FROM number of service periods

service history ok
    AND ALL period IN service history
        AND period.period of service in days >= 30
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        engine = InferenceEngine(node_set)
        assessment = Assessment(node_set, "service history ok")
        engine.add_assessment_into_assessment_list(assessment)

        first_question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(first_question) == ["number of service periods"]
        assert engine.find_type_of_element_to_be_asked(first_question)["number of service periods"] == FactValueType.DOUBLE

        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "number of service periods",
            2,
            FactValueType.DOUBLE,
            assessment,
        )
        second_question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(second_question) == [
            "1st  period.period of service in days"
        ]
        assert engine.find_type_of_element_to_be_asked(second_question)[
            "1st  period.period of service in days"
        ] == FactValueType.DOUBLE

        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "1st  period.period of service in days",
            45,
            FactValueType.DOUBLE,
            assessment,
        )
        third_question = engine.get_next_question(assessment)

        assert engine.get_questions_from_node_to_be_asked(third_question) == [
            "2nd  period.period of service in days"
        ]
        assert engine.get_questions_from_node_to_be_asked(third_question) != [
            "1st  period.period of service in days"
        ]

        engine.feed_answer_to_node(
            assessment.get_node_to_be_asked(),
            "2nd  period.period of service in days",
            31,
            FactValueType.DOUBLE,
            assessment,
        )

        working_memory = engine.get_assessment_state().get_working_memory()
        assert working_memory["ALL period ITERATE: LIST OF service history"].get_value() is True
        assert working_memory["service history ok"].get_value() is True
        assert engine.get_next_question(assessment) is None
        assert assessment.get_node_to_be_asked() is None
        assert assessment.get_aux_node_to_be_asked() is None


class TestResetWorkingMemoryClear:
    def test_clears_working_memory_directly(self):
        engine = InferenceEngine()
        engine.get_assessment_state().set_fact("key1", FactValue(1))
        engine.get_assessment_state().get_inclusive_list().append("item1")
        assert "key1" in engine.get_assessment_state().get_working_memory()
        engine.reset_working_memory_and_inclusive_list()
        assert len(engine.get_assessment_state().get_inclusive_list()) == 0
