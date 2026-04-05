"""
Inference Engine Module.
Core engine for PALOS rule evaluation and backward chaining.
Implements access levels and strong typing where appropriate.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from project.fact_values import FactValue, FactValueType
from project.inference import Assessment, AssessmentState
from project.inference.assesments import Assessments
from project.inference.question_resolver import QuestionResolver
from project.nodes import ComparisonLine, ValueConclusionLine, DependencyType, LineType
from project.nodes.node import Node
from project.nodes.node_set import NodeSet
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


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
    def __init__(self, node_set: Optional[NodeSet] = None):
        """
        Public Constructor: Initializes InferenceEngine.
        
        Args:
            node_set: Optional NodeSet containing rules
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__node_set: Optional[NodeSet] = node_set
        self.__target_node: Optional[Node] = None
        self.__ast: AssessmentState = self._new_assessment_state()
        self.__ass: Assessment = Assessment()
        self.__asses: Assessments = Assessments()
        self.__node_fact_list: List[Node] = list()
        self.__question_resolver: QuestionResolver = QuestionResolver(lambda _: None)

        if node_set is not None:
            self._initialize_from_node_set(node_set)

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
        temp_working_memory = self.__ast.get_working_memory()

        if len(temp_fact_dict) > 0:
            for key in temp_fact_dict.keys():
                temp_working_memory[key] = temp_fact_dict[key]

    def _new_assessment_state(self) -> AssessmentState:
        """
        Protected Helper: Creates new AssessmentState instance.
        
        Returns:
            New AssessmentState object
        """
        return AssessmentState()

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

    def _has_any_or_child_evaluated(self, parent_node_id: int, or_to_child_dependencies: List[int]) -> bool:
        """
        Protected Helper: Checks if any OR child has been evaluated.
        
        Args:
            parent_node_id: Parent node ID
            or_to_child_dependencies: List of OR child dependencies
            
        Returns:
            True if any OR child is evaluated
        """
        if self.__node_set is None:
            return False
            
        any_or_child_evaluated: bool = any(
            (self.__node_set.get_node_by_node_id(child_id) in self.__ast.get_working_memory().keys()
             and self.__node_set.get_dependency_matrix().get_dependency_type(parent_node_id, child_id) != -1
             and self.__node_set.get_dependency_matrix().get_dependency_type(parent_node_id, child_id)
             & DependencyType.get_mandatory() == DependencyType.get_mandatory())
            or self.__node_set.get_node_by_node_id(child_id).get_variable_name() in self.__ast.get_working_memory().keys()
            for child_id in or_to_child_dependencies
        )

        return any_or_child_evaluated

    def _has_all_and_child_evaluated(self, and_to_child_dependencies: List[int]) -> bool:
        """
        Protected Helper: Checks if all AND children have been evaluated.
        
        Args:
            and_to_child_dependencies: List of AND child dependencies
            
        Returns:
            True if all AND children are evaluated
        """
        if self.__node_set is None:
            return False
            
        all_and_child_evaluated: bool = all(
            self.__node_set.get_node_by_node_id(child_id).get_variable_name()
            in self.__ast.get_working_memory().keys()
            for child_id in and_to_child_dependencies
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
                node_id = target_node.get_node_id()
                
                if index != ass.get_goal_node_index():
                    self._process_parent_dependencies(target_node, node_id, ass)
                
                if self._should_ask_node(target_node, node_id, ass, index):
                    return ass.get_node_to_be_asked()
                elif self._has_children_to_process(target_node, node_id, ass):
                    self._add_child_rule_into_inclusive_list(target_node)

        next_question_node: Optional[Node] = ass.get_node_to_be_asked()
        if next_question_node is not None and next_question_node.get_line_type() == LineType.ITERATE:
            ass.set_aux_node_to_be_asked(next_question_node)

        return next_question_node

    def _process_parent_dependencies(self, target_node: Node, node_id: int, ass: Assessment) -> None:
        """
        Protected Helper: Processes parent dependencies for a node.
        
        Args:
            target_node: Target node to process
            node_id: Node ID
            ass: Current assessment
        """
        if self.__node_set is None:
            return
        parent_dependency_list: List[int] = self.__node_set.get_dependency_matrix().get_from_parent_dependency_list(node_id)
        if len(parent_dependency_list) > 0:
            for parent_id in parent_dependency_list:
                if self.__node_set.get_dependency_matrix().get_dependency_type(parent_id, node_id) != -1 \
                        and self.__node_set.get_dependency_matrix().get_dependency_type(parent_id, node_id) \
                        & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                        and not self.__ast.is_in_inclusive_list(target_node.get_node_name()) \
                        and not self._is_iterate_line_child(target_node.get_node_id()):
                    self.__ast.add_item_to_mandatory_list(target_node.get_node_name())

    def _should_ask_node(self, target_node: Node, node_id: int, ass: Assessment, index: int) -> bool:
        """
        Protected Helper: Determines if a node should be asked.
        
        Args:
            target_node: Target node to evaluate
            node_id: Node ID
            ass: Current assessment
            index: Node index in sorted list
            
        Returns:
            True if node should be asked
        """
        if node_id != ass.get_goal_node().get_node_id() \
                and target_node.get_line_type() == LineType.ITERATE \
                and target_node.get_node_name() not in self.__ast.get_working_memory().keys():
            return self._handle_iterate_node(target_node, ass, index)
        elif not self._has_children(node_id) \
                and target_node.get_node_name() in self.__ast.get_inclusive_list() \
                and self.__question_resolver.find_next_question_node(
                    target_node, self.__ast.get_working_memory(), has_children=False
                ) is not None \
                and not self._can_evaluate(target_node):
            ass.set_node_to_be_asked(target_node)
            _logger.info("index Of Rule To Be Asked : " + str(index))
            return True
        return False

    def _has_children_to_process(self, target_node: Node, node_id: int, ass: Assessment) -> bool:
        """
        Protected Helper: Checks if node has children to process.
        
        Args:
            target_node: Target node to evaluate
            node_id: Node ID
            ass: Current assessment
            
        Returns:
            True if children need processing
        """
        return self._has_children(node_id) \
                and target_node.get_variable_name() not in self.__ast.get_working_memory().keys() \
                and target_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                and target_node.get_node_name() in self.__ast.get_inclusive_list()

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
        
        Args:
            target_node: Target node
            ass: Current assessment
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
        """
        target_node = ass.get_aux_node_to_be_asked()
        ass.get_node_to_be_asked().iterate_feed_answers(
            target_node, question_name, node_value, node_value_type,
            self.__node_set, self.__ast, ass
        )
        if ass.get_node_to_be_asked().can_be_self_evaluated(self.__ast.get_working_memory()):
            self._back_propagating(self.__node_set.find_node_index(ass.get_node_to_be_asked().get_node_name()))

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
            temp_node_id: int = temp_node.get_node_id()
            self._process_node_dependencies(temp_node, temp_node_id)
            self._evaluate_node_after_propagation(temp_node, line_type, node_index, current_index)

    def _process_node_dependencies(self, temp_node: Node, temp_node_id: int) -> None:
        """
        Protected Helper: Processes dependencies for a node during propagation.
        
        Args:
            temp_node: Node to process
            temp_node_id: Node ID
        """
        if self.__node_set is None:
            return
        parent_dependency_list: List[int] = \
            self.__node_set.get_dependency_matrix().get_from_parent_dependency_list(temp_node_id)
        if len(parent_dependency_list) > 0:
            for parent_id in parent_dependency_list:
                dependency_type = \
                    self.__node_set.get_dependency_matrix().get_dependency_type(parent_id, temp_node_id)
                if dependency_type != -1 \
                        and dependency_type & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                        and not self.__ast.is_in_inclusive_list(temp_node.get_node_name()) \
                        and not self._is_iterate_line_child(temp_node.get_node_id()):
                    self.__ast.add_item_to_mandatory_list(temp_node.get_node_name())

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
        if node_index < current_index:
            if self._has_children(temp_node.get_node_id()):
                if temp_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                        and self._can_determine(temp_node, line_type):
                    if LineType.EXPR_CONCLUSION != line_type:
                        self.__ast.add_item_to_summary_list(temp_node.get_node_name())
            else:
                self._evaluate_leaf_node(temp_node, line_type)
        else:
            if temp_node.get_node_name() in self.__ast.get_inclusive_list():
                if temp_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                        and self._has_children(temp_node.get_node_id()) \
                        and self._can_determine(temp_node, line_type):
                    if LineType.EXPR_CONCLUSION != line_type:
                        self.__ast.add_item_to_summary_list(temp_node.get_node_name())

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
        if self.__node_set is None:
            return variable_name_list
        for each_node in self.__node_set.get_node_dictionary().values():
            if len(self.__node_set.get_dependency_matrix().get_to_child_dependency_list()[each_node.get_node_id()]) == 0:
                variable_name_list.append(each_node.get_variable_name())
                node_fact_value_type: FactValueType = each_node.get_fact_value().get_value_type()
                if (node_fact_value_type == FactValueType.STRING) or (node_fact_value_type == FactValueType.TEXT):
                    variable_name_list.append(str(each_node.get_fact_value().get_value()))
        return variable_name_list

    def _has_children(self, node_id: int) -> bool:
        """
        Protected Helper: Checks if node has children.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            True if node has children
        """
        if self.__node_set is None:
            return False
        if len(self.__node_set.get_dependency_matrix().get_to_child_dependency_list(node_id)) != 0:
            for item in self.__node_set.get_dependency_matrix().get_to_child_dependency_list(node_id):
                node_name = self.__node_set.get_node_by_node_id(item)
                self._add_child_rule_into_inclusive_list(node_name)
            return True
        return False

    def _add_child_rule_into_inclusive_list(self, parent_node: Node) -> None:
        """
        Protected Helper: Adds child rules to inclusive list.
        
        Args:
            parent_node: Parent node
        """
        if self.__node_set is None:
            return
        children_list_of_node: List[int] = \
            self.__node_set.get_dependency_matrix().get_to_child_dependency_list(parent_node.get_node_id())
        for item in children_list_of_node:
            child_node_name = \
                self.__node_set.get_node_dictionary().get(self.__node_set.get_node_id_dictionary().get(item)).get_node_name()
            if child_node_name not in self.__ast.get_inclusive_list() \
                    and child_node_name not in self.__ast.get_exclusive_list():
                self.__ast.get_inclusive_list().append(child_node_name)

    def _is_iterate_line_child(self, node_id: int) -> bool:
        """
        Protected Helper: Checks if node is child of iterate line.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            True if node is iterate line child
        """
        if self.__node_set is None:
            return False
        is_iterate_line_child = False
        temp_list: List[int] = []
        iterate_line_list: List[Node] = list(filter(
            lambda target_node: target_node.get_line_type() == LineType.ITERATE,
            self.__node_set.get_node_dictionary().values()
        ))
        for i_node in iterate_line_list:
            iterate_child_node_list: List[int] = self.__node_set.get_dependency_matrix().get_to_child_dependency_list(i_node.get_node_id())
            if node_id in iterate_child_node_list:
                temp_list.append(1)
            else:
                self._is_iterate_line_child_aux(temp_list, iterate_child_node_list, node_id)
        if len(temp_list) > 0:
            is_iterate_line_child = True
        else:
            if self.__node_set.get_node_id_dictionary()[node_id] in self.__ast.get_mandatory_list():
                self.__ast.get_mandatory_list().remove(self.__node_set.get_node_id_dictionary()[node_id])
        return is_iterate_line_child

    def _is_iterate_line_child_aux(
        self,
        temp_list: List[int],
        iterate_child_node_list: List[int],
        node_id: int,
    ) -> None:
        """
        Protected Helper: Recursive helper for iterate line child check.
        
        Args:
            temp_list: Temporary list for tracking
            iterate_child_node_list: List of iterate child node IDs
            node_id: Node ID to check
        """
        if self.__node_set is None:
            return
        for each_id in iterate_child_node_list:
            iterate_child_node_list_aux = self.__node_set.get_dependency_matrix().get_to_child_dependency_list(each_id)
            if node_id in iterate_child_node_list:
                temp_list.append(1)
            else:
                self._is_iterate_line_child_aux(temp_list, iterate_child_node_list_aux, node_id)

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