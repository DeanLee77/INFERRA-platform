"""
Inference Engine Module.
Core engine for INFERRA rule evaluation and backward chaining.
Implements access levels and strong typing where appropriate.

Phase 2.5 (WS-1): Hot-path operations use DependencyGraphPort exclusively.
No direct get_dependency_matrix() or get_node_id() calls remain.
"""

import json
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Set
from src.domain.inference.assessment import Assessment
from src.domain.inference.assessment_state import AssessmentState
from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.assessments import Assessments
from src.domain.inference.question_resolver import QuestionResolver
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.dependency_type import DependencyType
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags
from src.ports.dependency_graph_port import DependencyGraphPort
from src.shared.loggers import Logger

_logger: Logger = Logger.get_logger(__name__)


def _noop_question_callback(_: Any) -> None:
    """Default callback used when no external question sink is attached."""
    return None


class InferenceEngine:
    """
    InferenceEngine manages rule evaluation, backward chaining, and user questioning.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        node_set: Optional[NodeSet] = None,
        feature_flags: Optional[FeatureFlags] = None,
    ):
        """
        Public Constructor: Initializes InferenceEngine.

        Args:
            node_set: Optional NodeSet containing rules
            feature_flags: Optional FeatureFlags snapshot. When None, defaults
                to a fresh FeatureFlags reading current env. Sessions should
                pass an already-frozen instance so flags can't flip mid-session.
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__node_set: Optional[NodeSet] = node_set
        self.__target_node: Optional[Node] = None
        self.__ast: AssessmentState = self._new_assessment_state()
        self.__ass: Assessment = Assessment()
        self.__asses: Assessments = Assessments()
        self.__node_fact_list: List[Node] = list()
        self.__question_resolver: QuestionResolver = QuestionResolver(_noop_question_callback)
        self.__feature_flags: FeatureFlags = feature_flags if feature_flags is not None else FeatureFlags()
        self.__dependency_graph: Optional[DependencyGraphPort] = None

        if node_set is not None:
            self._initialize_from_node_set(node_set)
            self._select_graph_backend(node_set)

        _logger.info(
            "InferenceEngine initialised "
            f"(use_hypergraph={self.__feature_flags.use_hypergraph}, "
            f"legacy_iterate={self.__feature_flags.legacy_iterate}, "
            f"layered_memory={self.__feature_flags.layered_memory}, "
            f"graph_backend={'hypergraph' if self.__dependency_graph is not None else 'none'})"
        )

    # -------------------------------------------------------------------------
    # Public Access Level: Feature-Flag & Graph Backend Accessors
    # -------------------------------------------------------------------------
    def get_feature_flags(self) -> FeatureFlags:
        """
        Public API: Returns the FeatureFlags snapshot governing this engine's behaviour.

        Returns:
            FeatureFlags instance (typically frozen at session start)
        """
        return self.__feature_flags

    def get_dependency_graph(self) -> Optional[DependencyGraphPort]:
        """
        Public API: Returns the canonical dependency graph used by the engine.

        Returns:
            DependencyGraphPort instance, or None when no graph is available
        """
        return self.__dependency_graph

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _initialize_from_node_set(self, node_set: NodeSet) -> None:
        """
        Protected Helper: Initializes engine state from NodeSet.

        Args:
            node_set: NodeSet containing rules and facts
        """
        temp_fact_dict = node_set.get_fact_dictionary() if node_set is not None else {}

        if len(temp_fact_dict) > 0:
            for key, value in temp_fact_dict.items():
                self.__ast.set_fact(key, value, source=FactSource.ASSERTED)

    def _new_assessment_state(self) -> AssessmentState:
        """
        Protected Helper: Creates new AssessmentState instance.

        Returns:
            New AssessmentState object
        """
        return AssessmentState()

    def _select_graph_backend(self, node_set: NodeSet) -> None:
        """
        Protected Helper: Build the graph backend for hot-path operations.

        Phase 2.5 (WS-1): Always builds the graph — the engine depends on
        DependencyGraphPort for all hot-path traversal. Prefers the canonical
        graph from NodeSet when available. Legacy matrix payloads are converted
        by NodeSet.set_dependency_matrix().
        """
        canonical_graph = node_set.get_graph()
        if canonical_graph is not None:
            self.__dependency_graph = canonical_graph
            _logger.info(
                "Graph backend: using canonical HyperAdjacencyGraph from NodeSet"
            )
            return

        _logger.warning("NodeSet lacks canonical dependency graph")

    def _handle_value_conclusion_line_true_case(
        self,
        value_node: Node,
        is_plain_statement_format: bool,
        node_fact_value_in_string: str,
    ) -> None:
        """
        Protected Helper: Handles TRUE case for ValueConclusionLine.
        
        Args:
            value_node: The value conclusion node
            is_plain_statement_format: Whether node is plain statement
            node_fact_value_in_string: Node fact value as string
        """
        self.__ast.set_fact(value_node.get_node_name(), FactValue(True))
        if not is_plain_statement_format:
            if node_fact_value_in_string in self.__ast.get_working_memory().keys():
                self.__ast.set_fact(
                    value_node.get_variable_name(),
                    self.__ast.get_working_memory()[node_fact_value_in_string]
                )
            else:
                self.__ast.set_fact(value_node.get_variable_name(), value_node.get_fact_value(), value_node)
            self.__ast.add_item_to_summary_list(value_node.get_variable_name())

    def _handle_value_conclusion_line_false_case(
        self,
        value_node: Node,
        is_plain_statement_format: bool,
        node_fact_value_in_string: str,
    ) -> None:
        """
        Protected Helper: Handles FALSE case for ValueConclusionLine.
        
        Args:
            value_node: The value conclusion node
            is_plain_statement_format: Whether node is plain statement
            node_fact_value_in_string: Node fact value as string
        """
        self.__ast.set_fact(value_node.get_node_name(), FactValue(False))
        if not is_plain_statement_format:
            if node_fact_value_in_string in self.__ast.get_working_memory().keys():
                fact_value_from_working_memory: FactValue = self.__ast.get_working_memory()[node_fact_value_in_string]
                fact_key = "NOT " + str(self.__ast.get_working_memory()[node_fact_value_in_string])
                if fact_value_from_working_memory.get_value_type() is FactValueType.LIST:
                    fact_value_from_working_memory.get_value().append(FactValue(fact_key))
                    self.__ast.set_fact(value_node.get_variable_name(), fact_value_from_working_memory)
                else:
                    fact_value_list = list()
                    fact_value_list.append(self.__ast.get_working_memory()[node_fact_value_in_string])
                    fact_value_list.append(FactValue(fact_key))
                    self.__ast.set_fact(value_node.get_variable_name(), FactValue(fact_value_list, FactValueType.LIST))
            else:
                self.__ast.set_fact(
                    value_node.get_variable_name(),
                    FactValue("NOT " + node_fact_value_in_string),
                    value_node
                )
            self.__ast.add_item_to_summary_list(value_node.get_variable_name())

    def _type_already_set(self, input_fact_value: FactValue) -> bool:
        """
        Protected Helper: Checks if fact value type is already defined.
        
        Args:
            input_fact_value: FactValue to check
            
        Returns:
            True if type is already set
        """
        has_already_set_type = False
        fact_value_type: FactValueType = input_fact_value.get_value_type()

        if fact_value_type in [FactValueType.DEFI_STRING, FactValueType.INTEGER, 
                               FactValueType.DOUBLE, FactValueType.DATE, FactValueType.BOOLEAN,
                               FactValueType.GUID, FactValueType.URL, FactValueType.HASH]:
            has_already_set_type = True

        return has_already_set_type

    def _has_any_or_child_evaluated(self, parent_node_name: str, or_child_names: List[str]) -> bool:
        """
        Protected Helper: Checks if any OR child has been evaluated.
        
        Args:
            parent_node_name: Parent node name
            or_child_names: List of OR child node names
            
        Returns:
            True if any OR child is evaluated
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False

        node_dict = self.__node_set.get_node_dictionary()
        wm = self.__ast.get_working_memory()

        any_or_child_evaluated: bool = any(
            (child_name in wm
             and self.__dependency_graph.get_dependency_type(parent_node_name, child_name) != -1
             and self.__dependency_graph.get_dependency_type(parent_node_name, child_name)
             & DependencyType.get_mandatory() == DependencyType.get_mandatory())
            or (child_name in node_dict and node_dict[child_name].get_variable_name() in wm)
            for child_name in or_child_names
        )

        return any_or_child_evaluated

    def _has_all_and_child_evaluated(self, and_child_names: List[str]) -> bool:
        """
        Protected Helper: Checks if all AND children have been evaluated.
        
        Args:
            and_child_names: List of AND child node names
            
        Returns:
            True if all AND children are evaluated
        """
        if self.__node_set is None:
            return False

        node_dict = self.__node_set.get_node_dictionary()

        all_and_child_evaluated: bool = all(
            child_name in node_dict and node_dict[child_name].get_variable_name()
            in self.__ast.get_working_memory().keys()
            for child_name in and_child_names
        )

        return all_and_child_evaluated

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (NodeSet)
    # -------------------------------------------------------------------------
    def set_node_set(self, node_set: NodeSet) -> None:
        """
        Public API: Sets the NodeSet for the engine.
        
        Args:
            node_set: NodeSet containing rules
        """
        self.__node_set = node_set
        self.__ast = self._new_assessment_state()
        self._initialize_from_node_set(node_set)
        self._select_graph_backend(node_set)

    def get_node_set(self) -> Optional[NodeSet]:
        """
        Public API: Returns the current NodeSet.
        
        Returns:
            Current NodeSet or None
        """
        return self.__node_set

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (AssessmentState)
    # -------------------------------------------------------------------------
    def get_assessment_state(self) -> AssessmentState:
        """
        Public API: Returns the current AssessmentState.
        
        Returns:
            Current AssessmentState
        """
        return self.__ast

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Assessments)
    # -------------------------------------------------------------------------
    def set_assessments(self, asses: Assessments) -> None:
        """
        Public API: Sets the Assessments collection.
        
        Args:
            asses: Assessments collection
        """
        self.__asses = asses

    def get_assessments(self) -> Assessments:
        """
        Public API: Returns the Assessments collection.
        
        Returns:
            Current Assessments collection
        """
        return self.__asses

    def add_assessment_into_assessment_list(self, assessment: Assessment) -> None:
        """
        Public API: Adds an assessment to the collection.
        
        Args:
            assessment: Assessment to add
        """
        self.__asses.add_assessment(assessment)

    def get_assessment_of_rule(self, goal_rule_name: str) -> Optional[Assessment]:
        """
        Public API: Gets an assessment by rule name.
        
        Args:
            goal_rule_name: Name of the goal rule
            
        Returns:
            Assessment or None
        """
        return self.__asses.get_assessment(goal_rule_name)

    def set_assessment(self, ass: Assessment) -> None:
        """
        Public API: Sets the current assessment.
        
        Args:
            ass: Assessment to set
        """
        self.__ass = ass

    def get_assessment(self) -> Assessment:
        """
        Public API: Returns the current assessment.
        
        Returns:
            Current Assessment
        """
        return self.__ass

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Question Handling)
    # -------------------------------------------------------------------------
    def get_next_question_with_goal_name(self, goal_name: str) -> Optional[Node]:
        """
        Public API: Gets next question node with specific goal name.
        
        Args:
            goal_name: Name of the goal rule
            
        Returns:
            Node to be asked or None
        """
        assessment = self.__asses.get_assessment(goal_name)
        return self.get_next_question(assessment)

    def get_next_question(self, ass: Assessment) -> Optional[Node]:
        """
        Public API: Gets next question node using backward chaining.
        
        Args:
            ass: Assessment to process
            
        Returns:
            Node to be asked or None
        """
        if self.__node_set is None or ass.get_goal_node() is None:
            return None
            
        if ass.get_goal_node().get_node_name() not in self.__ast.get_inclusive_list():
            self.__ast.get_inclusive_list().append(ass.get_goal_node().get_node_name())

        if (self.__ast.get_working_memory().get(ass.get_goal_node().get_node_name()) is None) or \
                (not self.__ast.all_mandatory_node_determined()):
            for index in range(ass.get_goal_node_index(), len(self.__node_set.get_sorted_node_list())):
                target_node: Node = self.__node_set.get_sorted_node_list()[index]
                node_name = target_node.get_node_name()
                
                if index != ass.get_goal_node_index():
                    self._process_parent_dependencies(target_node, ass)
                
                if self._should_ask_node(target_node, ass, index):
                    return ass.get_node_to_be_asked()
                elif self._has_children_to_process(target_node, ass):
                    self._add_child_rule_into_inclusive_list(target_node)

        next_question_node: Optional[Node] = ass.get_node_to_be_asked()
        if next_question_node is not None and next_question_node.get_line_type() == LineType.ITERATE:
            ass.set_aux_node_to_be_asked(next_question_node)

        return next_question_node

    def _process_parent_dependencies(self, target_node: Node, ass: Assessment) -> None:
        """
        Protected Helper: Processes parent dependencies for a node.
        
        Args:
            target_node: Target node to process
            ass: Current assessment
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return
        node_name = target_node.get_node_name()
        parent_names: Set[str] = self.__dependency_graph.get_parent_edges(node_name)
        if len(parent_names) > 0:
            for parent_name in parent_names:
                dep_type = self.__dependency_graph.get_dependency_type(parent_name, node_name)
                if dep_type != -1 \
                        and dep_type & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                        and not self.__ast.is_in_inclusive_list(node_name) \
                        and not self._is_iterate_line_child(node_name):
                    self.__ast.add_item_to_mandatory_list(node_name)

    def _should_ask_node(self, target_node: Node, ass: Assessment, index: int) -> bool:
        """
        Protected Helper: Determines if a node should be asked.
        
        Args:
            target_node: Target node to evaluate
            ass: Current assessment
            index: Node index in sorted list
            
        Returns:
            True if node should be asked
        """
        node_name = target_node.get_node_name()
        if node_name != ass.get_goal_node().get_node_name() \
                and target_node.get_line_type() == LineType.ITERATE \
                and node_name not in self.__ast.get_working_memory().keys():
            return self._handle_iterate_node(target_node, ass, index)
        elif not self._has_children(node_name) \
                and node_name in self.__ast.get_inclusive_list() \
                and self.__question_resolver.find_next_question_node(
                    target_node, self.__ast.get_working_memory(), has_children=False
                ) is not None \
                and not self._can_evaluate(target_node):
            ass.set_node_to_be_asked(target_node)
            _logger.info("index Of Rule To Be Asked : " + str(index))
            return True
        return False

    def _has_children_to_process(self, target_node: Node, ass: Assessment) -> bool:
        """
        Protected Helper: Checks if node has children to process.
        
        Args:
            target_node: Target node to evaluate
            ass: Current assessment
            
        Returns:
            True if children need processing
        """
        node_name = target_node.get_node_name()
        return self._has_children(node_name) \
                and target_node.get_variable_name() not in self.__ast.get_working_memory().keys() \
                and node_name not in self.__ast.get_working_memory().keys() \
                and node_name in self.__ast.get_inclusive_list()

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Fact Management)
    # -------------------------------------------------------------------------
    def add_node_fact(self, node_variable_name: str, fv: FactValue) -> None:
        """
        Public API: Adds a node fact before inference process.
        
        Args:
            node_variable_name: Variable name of the node
            fv: FactValue to store
        """
        if self.__node_set is None:
            return
        for each_node in self.__node_set.get_node_dictionary().values():
            if (each_node.get_variable_name() == node_variable_name) or \
                    (str(each_node.get_fact_value().get_value()) == node_variable_name):
                self.__node_fact_list.append(each_node)
        self.__ast.get_working_memory()[node_variable_name] = fv

    def feed_answer_to_node(
        self,
        target_node: Node,
        question_name: str,
        node_value: Any,
        node_value_type: FactValueType,
        ass: Assessment,
    ) -> None:
        """
        Public API: Feeds an answer to a node and propagates changes.
        
        Args:
            target_node: Target node
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
            ass: Current assessment
        """
        fact_value: Optional[FactValue] = self._create_fact_value(node_value, node_value_type)

        if fact_value is not None and LineType.ITERATE != ass.get_node_to_be_asked().get_line_type():
            self.__ast.set_fact(question_name, fact_value)
            self.__ast.add_item_to_summary_list(question_name)
            self._handle_node_evaluation(target_node, fact_value)
            self._back_propagating(self.__node_set.find_node_index(target_node.get_node_name()))
        elif LineType.ITERATE == ass.get_node_to_be_asked().get_line_type():
            self._handle_iterate_answer(target_node, ass, question_name, node_value, node_value_type)

    def _create_fact_value(self, node_value: Any, node_value_type: FactValueType) -> Optional[FactValue]:
        """
        Protected Helper: Creates FactValue from user input.
        SECURITY FIX: Removed eval() for boolean parsing.
        
        Args:
            node_value: Value from user
            node_value_type: Type of the value
            
        Returns:
            FactValue or None
        """
        fact_value: Optional[FactValue] = None
        if FactValueType.BOOLEAN == node_value_type:
            if isinstance(node_value, bool):
                fact_value = FactValue(node_value, FactValueType.BOOLEAN)
            elif isinstance(node_value, str):
                # SECURITY FIX: Safe boolean parsing without eval()
                if node_value.lower() == 'true':
                    fact_value = FactValue(True, FactValueType.BOOLEAN)
                elif node_value.lower() == 'false':
                    fact_value = FactValue(False, FactValueType.BOOLEAN)
        elif FactValueType.DATE == node_value_type:
            fact_value = FactValue(node_value, FactValueType.DATE)
        elif FactValueType.DOUBLE == node_value_type:
            fact_value = FactValue(float(str(node_value)))
        elif FactValueType.INTEGER == node_value_type:
            fact_value = FactValue(int(node_value))
        elif FactValueType.STRING == node_value_type:
            fact_value = FactValue(str(node_value))
        elif FactValueType.DEFI_STRING == node_value_type:
            fact_value = FactValue(str(node_value), FactValueType.DEFI_STRING)
        elif node_value_type in [FactValueType.HASH, FactValueType.URL, FactValueType.GUID, FactValueType.LIST]:
            fact_value = FactValue(node_value, node_value_type)
        return fact_value

    def _handle_node_evaluation(self, target_node: Node, fact_value: FactValue) -> None:
        """
        Protected Helper: Handles node self-evaluation after answer.
        
        Args:
            target_node: Target node
            fact_value: FactValue to store
        """
        if LineType.VALUE_CONCLUSION == target_node.get_line_type() \
                and not target_node.get_is_plain_statement():
            self_eval_fact_value: FactValue = target_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(target_node.get_node_name(), self_eval_fact_value)
            self.__ast.add_item_to_summary_list(target_node.get_node_name())
        elif LineType.COMPARISON == target_node.get_line_type():
            rhs_value: FactValue = target_node.get_rhs()
            if (FactValueType.STRING == rhs_value.get_value_type()
                    and str(rhs_value.get_value()) in self.__ast.get_working_memory().keys()) \
                    or FactValueType.STRING != rhs_value.get_value_type():
                self_eval_fact_value: FactValue = target_node.self_evaluate(self.__ast.get_working_memory())
                self.__ast.set_fact(target_node.get_node_name(), self_eval_fact_value)
                self.__ast.add_item_to_summary_list(target_node.get_node_name())

    def _handle_iterate_answer(
        self,
        target_node: Node,
        ass: Assessment,
        question_name: str,
        node_value: Any,
        node_value_type: FactValueType,
    ) -> None:
        """
        Protected Helper: Handles answer for iterate line nodes.

        Phase 1 WS-3 integration: after the legacy iterate_feed_answers() call,
        if the iterate node can be self-evaluated, the conclusion is tagged
        FactSource.INFERRED instead of the default ASSERTED.

        Args:
            target_node: Target node
            ass: Current assessment
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
        """
        iterate_node = ass.get_node_to_be_asked()
        target_node = ass.get_aux_node_to_be_asked()
        iterate_node.iterate_feed_answers(
            target_node, question_name, node_value, node_value_type,
            self.__node_set, self.__ast, ass,
            feature_flags=self.__feature_flags,
        )
        if iterate_node.can_be_self_evaluated(self.__ast.get_working_memory()):
            # Tag the iterate conclusion as INFERRED (derived by the rule engine)
            eval_result = iterate_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(
                iterate_node.get_node_name(),
                eval_result,
                source=FactSource.INFERRED,
            )
            self.__ast.add_item_to_summary_list(iterate_node.get_node_name())
            self._back_propagating(self.__node_set.find_node_index(iterate_node.get_node_name()))

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Back Propagation)
    # -------------------------------------------------------------------------
    def _back_propagating(self, node_index: int) -> None:
        """
        Protected Helper: Propagates changes through the node set.
        
        Args:
            node_index: Index of the node that changed
        """
        if self.__node_set is None:
            return
        node_sorted_list: List[Node] = self.__node_set.get_sorted_node_list()
        sorted_list_size: int = len(node_sorted_list)
        for i in range(0, sorted_list_size):
            current_index = sorted_list_size - (i + 1)
            temp_node: Node = node_sorted_list[current_index]
            line_type: LineType = temp_node.get_line_type()
            self._process_node_dependencies(temp_node)
            self._evaluate_node_after_propagation(temp_node, line_type, node_index, current_index)

    def _process_node_dependencies(self, temp_node: Node) -> None:
        """
        Protected Helper: Processes dependencies for a node during propagation.
        
        Args:
            temp_node: Node to process
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return
        node_name = temp_node.get_node_name()
        parent_names: Set[str] = self.__dependency_graph.get_parent_edges(node_name)
        if len(parent_names) > 0:
            for parent_name in parent_names:
                dep_type = self.__dependency_graph.get_dependency_type(parent_name, node_name)
                if dep_type != -1 \
                        and dep_type & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                        and not self.__ast.is_in_inclusive_list(node_name) \
                        and not self._is_iterate_line_child(node_name):
                    self.__ast.add_item_to_mandatory_list(node_name)

    def _evaluate_node_after_propagation(
        self,
        temp_node: Node,
        line_type: LineType,
        node_index: int,
        current_index: int,
    ) -> None:
        """
        Protected Helper: Evaluates a node after back propagation.
        
        Args:
            temp_node: Node to evaluate
            line_type: Type of the node line
            node_index: Original node index
            current_index: Current index in iteration
        """
        node_name = temp_node.get_node_name()
        if node_index < current_index:
            if self._has_children(node_name):
                if node_name not in self.__ast.get_working_memory().keys() \
                        and self._can_determine(temp_node, line_type):
                    if LineType.EXPR_CONCLUSION != line_type:
                        self.__ast.add_item_to_summary_list(node_name)
            else:
                self._evaluate_leaf_node(temp_node, line_type)
        else:
            if node_name in self.__ast.get_inclusive_list():
                if node_name not in self.__ast.get_working_memory().keys() \
                        and self._has_children(node_name) \
                        and self._can_determine(temp_node, line_type):
                    if LineType.EXPR_CONCLUSION != line_type:
                        self.__ast.add_item_to_summary_list(node_name)

    def _evaluate_leaf_node(self, temp_node: Node, line_type: LineType) -> None:
        """
        Protected Helper: Evaluates leaf nodes during propagation.
        
        Args:
            temp_node: Node to evaluate
            line_type: Type of the node line
        """
        if LineType.VALUE_CONCLUSION == line_type \
                and not temp_node.get_is_plain_statement() \
                and temp_node.get_variable_name() in self.__ast.get_working_memory().keys():
            fact_value: FactValue = temp_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(temp_node.get_node_name(), fact_value)
            self.__ast.add_item_to_summary_list(temp_node.get_node_name())
        elif LineType.COMPARISON == line_type \
                and temp_node.get_lhs() in self.__ast.get_working_memory().keys() \
                and ((FactValueType.STRING == temp_node.get_rhs().get_value_type() and str(
                    temp_node.get_rhs().get_value()) in self.__ast.get_working_memory().keys()) \
                or (FactValueType.STRING != temp_node.get_rhs().get_value_type())):
            fact_value: FactValue = temp_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(temp_node.get_node_name(), fact_value)
            self.__ast.add_item_to_summary_list(temp_node.get_node_name())

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Utility)
    # -------------------------------------------------------------------------
    def get_list_of_variable_name_and_value_of_nodes(self) -> List[str]:
        """
        Public API: Extracts all variable names of nodes for display.
        
        Returns:
            List of variable names and values
        """
        variable_name_list: List[str] = []
        if self.__node_set is None or self.__dependency_graph is None:
            return variable_name_list
        for each_node in self.__node_set.get_node_dictionary().values():
            if len(self.__dependency_graph.get_children_flat(each_node.get_node_name())) == 0:
                variable_name_list.append(each_node.get_variable_name())
                node_fact_value_type: FactValueType = each_node.get_fact_value().get_value_type()
                if (node_fact_value_type == FactValueType.STRING) or (node_fact_value_type == FactValueType.TEXT):
                    variable_name_list.append(str(each_node.get_fact_value().get_value()))
        return variable_name_list

    def _has_children(self, node_name: str) -> bool:
        """
        Protected Helper: Checks if node has children.
        
        Args:
            node_name: Node name to check
            
        Returns:
            True if node has children
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False
        children = self.__dependency_graph.get_children_flat(node_name)
        if len(children) != 0:
            node_dict = self.__node_set.get_node_dictionary()
            for child_name in children:
                child_node = node_dict.get(child_name)
                if child_node is not None:
                    self._add_child_rule_into_inclusive_list(child_node)
            return True
        return False

    def _add_child_rule_into_inclusive_list(self, node: Node) -> None:
        """
        Protected Helper: Adds child rules to inclusive list.
        
        Args:
            node: Node whose children should be added
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return
        children = self.__dependency_graph.get_children_flat(node.get_node_name())
        for child_name in children:
            if child_name not in self.__ast.get_inclusive_list() \
                    and child_name not in self.__ast.get_exclusive_list():
                self.__ast.get_inclusive_list().append(child_name)

    def _is_iterate_line_child(self, node_name: str) -> bool:
        """
        Protected Helper: Checks if node is child of iterate line.
        
        Uses BFS walk-up via graph parent edges to check if any ancestor
        is an iterate node. More efficient than the previous walk-down
        approach which iterated all iterate nodes' descendants.
        
        Args:
            node_name: Node name to check
            
        Returns:
            True if node is iterate line child
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False
        node_dict = self.__node_set.get_node_dictionary()
        visited: Set[str] = set()
        queue: Deque[str] = deque([node_name])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for parent_name in self.__dependency_graph.get_parent_edges(current):
                parent_node = node_dict.get(parent_name)
                if parent_node is not None and parent_node.get_line_type() == LineType.ITERATE:
                    return True
                queue.append(parent_name)
        if node_name in self.__ast.get_mandatory_list():
            self.__ast.get_mandatory_list().remove(node_name)
        return False

    def _can_evaluate(self, target_node: Node) -> bool:
        """
        Protected Helper: Checks if node can be evaluated with current working memory.
        
        Args:
            target_node: Node to check
            
        Returns:
            True if node can be evaluated
        """
        can_be_evaluate = False
        line_type: LineType = target_node.get_line_type()

        if LineType.VALUE_CONCLUSION == line_type:
            value_conclusion: ValueConclusionLine = target_node
            if value_conclusion.get_is_plain_statement() and value_conclusion.get_variable_name() in self.__ast.get_working_memory():
                can_be_evaluate = True
            elif len(list(filter(lambda token_string: token_string == "IS IN LIST: ",
                                value_conclusion.get_tokens().get_tokens_list()))) > 0 \
                    and str(value_conclusion.get_fact_value().get_value()) in self.__ast.get_working_memory().keys() \
                    and value_conclusion.get_variable_name() in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                fact_value: FactValue = value_conclusion.self_evaluate(self.__ast.get_working_memory())
                self.__ast.set_fact(value_conclusion.get_node_name(), fact_value, value_conclusion)
        elif LineType.COMPARISON == line_type:
            comparison: ComparisonLine = target_node
            node_rhs_value: FactValue = comparison.get_rhs()
            if FactValueType.STRING != node_rhs_value.get_value_type() \
                    and comparison.get_lhs() in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                if comparison.get_node_name() not in self.__ast.get_working_memory().keys():
                    self.__ast.set_fact(comparison.get_node_name(), comparison.self_evaluate(self.__ast.get_working_memory()))
            elif FactValueType.STRING == node_rhs_value.get_value_type() \
                    and comparison.get_lhs() in self.__ast.get_working_memory().keys() \
                    and str(comparison.get_rhs().get_value()) in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                if comparison.get_node_name() not in self.__ast.get_working_memory().keys():
                    self.__ast.set_fact(comparison.get_node_name(), comparison.self_evaluate(self.__ast.get_working_memory()), comparison)
        return can_be_evaluate

    def _can_determine(self, target_node: Node, line_type: LineType) -> bool:
        """
        Protected Helper: Checks if node can be determined with current facts.
        
        Args:
            target_node: Node to check
            line_type: Type of the node line
            
        Returns:
            True if node can be determined
        """
        return True

    def reset_working_memory_and_inclusive_list(self) -> None:
        """
        Public API: Resets working memory and inclusive list.
        
        Use when starting a new assessment with same conditions.
        """
        if len(self.__ast.get_inclusive_list()) > 0:
            self.__ast.get_inclusive_list().clear()
        if len(self.__ast.get_working_memory()) > 0:
            self.__ast.get_working_memory().clear()

    def get_default_goal_rule_question(self) -> Optional[str]:
        """
        Public API: Gets default goal rule question name.
        
        Returns:
            Goal rule name or None
        """
        if self.__node_set is None:
            return None
        return self.__node_set.get_default_goal_node().get_node_name()

    def get_assessment_goal_rule_question(self, ass: Assessment) -> Optional[str]:
        """
        Public API: Gets assessment goal rule question name.
        
        Args:
            ass: Assessment to query
            
        Returns:
            Goal rule name or None
        """
        return ass.get_goal_node().get_node_name() if ass.get_goal_node() else None

    def get_default_goal_rule_answer(self) -> Optional[FactValue]:
        """
        Public API: Gets default goal rule answer.
        
        Returns:
            FactValue or None
        """
        if self.__node_set is None:
            return None
        return self.__ast.get_working_memory().get(self.__node_set.get_default_goal_node().get_variable_name())

    def get_assessment_goal_rule_answer(self, ass: Assessment) -> Optional[FactValue]:
        """
        Public API: Gets assessment goal rule answer.
        
        Args:
            ass: Assessment to query
            
        Returns:
            FactValue or None
        """
        return self.__ast.get_working_memory().get(ass.get_goal_node().get_variable_name()) if ass.get_goal_node() else None
