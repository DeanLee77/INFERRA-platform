"""
Iterate Line Module.
Handles iteration over lists in PALOS rule sets.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Any, Dict, List, Optional, Union
from project.inference import AssessmentState, Assessment, InferenceEngine, TopologicalSort
from project.loggers import Logger
from project.nodes.node import Node
from project.tokens import Token
from project.nodes.node_set import NodeSet
from project.nodes import ValueConclusionLine, ComparisonLine, ExprConclusionLine, Dependency, LineType, DependencyMatrix, MetaData
from project.fact_values import FactValue, FactValueType

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class IterateLine(Node):
    """
    IterateLine handles iteration over list-based rules.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, id: Optional[int] = None, parent_text: Optional[str] = None, 
                 tokens: Optional[Token] = None, meta_data: Optional[MetaData] = None):
        """
        Public Constructor: Initializes IterateLine.
        
        Args:
            id: Node ID
            parent_text: Text content of the node
            tokens: Tokenized representation
            meta_data: Metadata for the node
        """
        super().__init__(id=id, parent_text=parent_text, tokens=tokens, meta_data=meta_data)
        self._line_type = LineType.ITERATE
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__number_of_target: Optional[str] = None
        self.__iterate_node_set: Optional[NodeSet] = None
        self.__given_list_name: Optional[str] = None
        self.__given_list_size: int = 0
        self.__iterate_ie: Optional[InferenceEngine] = None

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_given_list_name(self) -> Optional[str]:
        """
        Public API: Returns the given list name.
        
        Returns:
            Given list name or None
        """
        return self.__given_list_name

    def get_number_of_target(self) -> Optional[str]:
        """
        Public API: Returns the number of target.
        
        Returns:
            Number of target or None
        """
        return self.__number_of_target

    def get_iterate_node_set(self) -> Optional[NodeSet]:
        """
        Public API: Returns the iterate node set.
        
        Returns:
            Iterate NodeSet or None
        """
        return self.__iterate_node_set

    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType.ITERATE
        """
        return LineType.ITERATE

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Node Set Creation)
    # -------------------------------------------------------------------------
    def create_iterate_node_set(self, parent_node_set: NodeSet) -> NodeSet:
        """
        Public API: Creates iterate node set from parent node set.
        
        Args:
            parent_node_set: Parent NodeSet to create from
            
        Returns:
            New NodeSet for iteration
        """
        parent_dependency_matrix: DependencyMatrix = parent_node_set.get_dependency_matrix()
        parent_node_dictionary = parent_node_set.get_node_dictionary()
        parent_node_id_dictionary = parent_node_set.get_node_id_dictionary()

        this_node_dictionary: Dict[str, Node] = dict()
        this_node_id_dictionary: Dict[int, str] = dict()
        temp_dependency_list: List[Dependency] = list()
        new_node_set = NodeSet()

        this_node_dictionary[self._node_name] = self
        this_node_id_dictionary[self._node_id] = self._node_name

        for nth in range(1, self.__given_list_size + 1):
            for item in parent_dependency_matrix.get_to_child_dependency_list(self.get_node_id()):
                if self.get_node_id() + 1 != item:
                    temp_child_node: Node = parent_node_dictionary[parent_node_id_dictionary[item]]
                    line_type = temp_child_node.get_line_type()
                    temp_node: Optional[Node] = None
                    next_nth_in_string = self._ordinal(nth)

                    if line_type == LineType.VALUE_CONCLUSION:
                        temp_node = ValueConclusionLine(
                            id=None,
                            node_text=next_nth_in_string + "  " + self.get_variable_name() + "  " + temp_child_node.get_node_name(),
                            tokens=temp_child_node.get_tokens())
                    elif line_type == LineType.COMPARISON:
                        temp_node = ComparisonLine(
                            id=None,
                            node_text=next_nth_in_string + "  " + self.get_variable_name() + "  " + temp_child_node.get_node_name(),
                            tokens=temp_child_node.get_tokens())
                        temp_node_fact_value = temp_node.get_rhs()
                        if temp_node_fact_value.get_value_type().value == FactValueType.STRING.value:
                            temp_fact_value = FactValue(
                                next_nth_in_string + "  " + self.get_variable_name() + "  " +
                                temp_node_fact_value.get_value(),
                                FactValueType.STRING)
                            temp_node.set_value(temp_fact_value)

                    elif line_type == LineType.EXPR_CONCLUSION:
                        temp_node = ExprConclusionLine(
                            id=None,
                            node_text=next_nth_in_string + "  " + self.get_variable_name() + "  " + temp_child_node.get_node_name(),
                            tokens=temp_child_node.get_tokens())

                    if temp_node:
                        this_node_dictionary[temp_node.get_node_name()] = temp_node
                        this_node_id_dictionary[temp_node.get_node_id()] = temp_node.get_node_name()
                        temp_dependency_list.append(
                            Dependency(self, temp_node, parent_dependency_matrix.get_dependency_type(self._node_id, item)))

                        self._create_iterate_node_set_aux(parent_dependency_matrix, parent_node_dictionary,
                                                          parent_node_id_dictionary, this_node_dictionary,
                                                          this_node_id_dictionary, temp_dependency_list,
                                                          item, temp_node.get_node_id(), next_nth_in_string)

        number_of_rules = Node.get_static_node_id()
        dependency_matrix = [[-1 for x in range(number_of_rules)] for y in range(number_of_rules)]
        for dp in temp_dependency_list:
            parent_id = dp.get_parent_node().get_node_id()
            child_id = dp.get_child_node().get_node_id()
            dependency_type = dp.get_dependency_type()
            dependency_matrix[parent_id][child_id] = dependency_type

        new_node_set.set_node_id_dictionary(this_node_id_dictionary)
        new_node_set.set_node_dictionary(this_node_dictionary)
        new_node_set.set_dependency_matrix(DependencyMatrix(dependency_matrix))
        new_node_set.set_fact_dictionary(parent_node_set.get_fact_dictionary())
        new_node_set.set_sorted_node_list(TopologicalSort.dfs_topological_sort(this_node_dictionary,
                                                                               this_node_id_dictionary,
                                                                               dependency_matrix))

        return new_node_set

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Answer Feeding)
    # -------------------------------------------------------------------------
    def iterate_feed_answers_with_json(self, given_json_string: Union[str, bytes], 
                                       parent_node_set: NodeSet,
                                       parent_assessment_state: AssessmentState, 
                                       assessment: Assessment) -> None:
        """
        Public API: Feeds answers from JSON string for iteration.
        
        Args:
            given_json_string: JSON string containing iteration data
            parent_node_set: Parent NodeSet
            parent_assessment_state: Parent AssessmentState
            assessment: Current Assessment
        """
        json_object = json.loads(given_json_string)
        service_list = json_object[self._variable_name]

        self.__given_list_size = len(service_list)

        if self.__iterate_node_set is None:
            self.__iterate_node_set = self.create_iterate_node_set(parent_node_set)
            self.__iterate_ie = InferenceEngine(self.__iterate_node_set)
            
            if self.__iterate_ie.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterate_ie.add_assessment_into_assessment_list(
                    Assessment(self.__iterate_node_set, self.get_node_name()))

        while self._node_name not in self.__iterate_ie.get_assessment_state().get_working_memory().keys():
            next_question_node: Node = self.get_iterate_next_question(parent_node_set, parent_assessment_state)
            question_fvt_map = self.__iterate_ie.find_type_of_element_to_be_asked(next_question_node)
            
            for question in self.__iterate_ie.get_questions_from_node_to_be_asked(next_question_node):
                answer = str(json_object[self._variable_name]
                             [next_question_node.get_variable_name()[
                              0: next_question_node.get_variable_name().rindex(self._variable_name) + len(
                                  self._variable_name)]]
                             [next_question_node.get_variable_name()]).strip()

                self.__iterate_ie.feed_answer_to_node(next_question_node, question, 
                                                      FactValue(answer, FactValueType.STRING),
                                                      self.__iterate_ie.get_assessment_of_rule(self.get_node_name()))

            iterate_working_memory = self.__iterate_ie.get_assessment_state().get_working_memory()
            parent_working_memory = parent_assessment_state.get_working_memory()

            self._transfer_fact_value(iterate_working_memory, parent_working_memory)

    def iterate_feed_answers(self, target_node: Node, question_name: str, node_value: Any,
                             node_value_type: FactValueType, parent_node_set: NodeSet,
                             parent_ast: AssessmentState, ass: Assessment) -> None:
        """
        Public API: Feeds answers for iteration without JSON.
        
        Args:
            target_node: Target node
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
            parent_node_set: Parent NodeSet
            parent_ast: Parent AssessmentState
            ass: Current Assessment
        """
        if self.__iterate_node_set is None:
            first_iterate_question_node = parent_node_set.get_node_by_node_id(
                min(parent_node_set.get_dependency_matrix().get_to_child_dependency_list(self.get_node_id()))
            )
            if question_name == first_iterate_question_node.get_node_name():
                self.__given_list_size = int(node_value)

            self.__iterate_node_set = self.create_iterate_node_set(parent_node_set)
            self.__iterate_ie = InferenceEngine(self.__iterate_node_set)

            if self.__iterate_ie.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterate_ie.add_assessment_into_assessment_list(
                    Assessment(self.__iterate_node_set, self.get_node_name()))

        self.__iterate_ie.get_assessment_of_rule(self.get_node_name()).set_node_to_be_asked(target_node)
        self.__iterate_ie.feed_answer_to_node(target_node, question_name, node_value,
                                              node_value_type, 
                                              self.__iterate_ie.get_assessment_of_rule(self.get_node_name()))

        iterate_working_memory = self.__iterate_ie.get_assessment_state().get_working_memory()
        parent_working_memory = parent_ast.get_working_memory()

        self._transfer_fact_value(iterate_working_memory, parent_working_memory)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Evaluation)
    # -------------------------------------------------------------------------
    def can_be_self_evaluated(self, working_memory: Dict[str, Any]) -> bool:
        """
        Public API: Checks if node can be self-evaluated.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            True if can be self-evaluated, False otherwise
        """
        if self.__iterate_ie is not None:
            number_of_determined_second_level_node = \
                filter(lambda target_id:
                        working_memory.get(
                           self.__iterate_ie.get_node_set().get_node_id_dictionary().get(target_id)) is not None \
                       and working_memory.get(
                           self.__iterate_ie.get_node_set().get_node_id_dictionary().get(
                               target_id)).get_value() is not None,
                       filter(lambda i: i is not self._node_id + 1,
                              self.__iterate_ie.get_node_set().get_dependency_matrix().get_to_child_dependency_list(
                                  self._node_id)
                             )
                       )

            if self.__given_list_size == len(list(number_of_determined_second_level_node)) \
                    and self.__iterate_ie.has_all_mandatory_child_answered(self._node_id):
                return True

        return False

    def self_evaluate(self, working_memory: Dict[str, Any]) -> FactValue:
        """
        Public API: Self-evaluates the iterate line.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result of evaluation
        """
        number_if_true_children: int = self._number_of_true_children(working_memory)
        size_of_given_list = self.__given_list_size

        fact_boolean_value: FactValue = None

        if self.__number_of_target == "ALL":
            if number_if_true_children == self.__given_list_size:
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)
        elif self.__number_of_target == "NONE":
            if number_if_true_children == 0:
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)
        elif self.__number_of_target == "SOME":
            if number_if_true_children > 0:
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)
        else:
            if number_if_true_children == int(self.__number_of_target):
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)

        return fact_boolean_value

    def get_iterate_next_question(self, parent_node_set: NodeSet, parent_ast: AssessmentState) -> Optional[Node]:
        """
        Public API: Gets next question for iteration.
        
        Args:
            parent_node_set: Parent NodeSet
            parent_ast: Parent AssessmentState
            
        Returns:
            Next question Node or None
        """
        if self.__iterate_node_set is None and self.__given_list_size != 0:
            self.__iterate_node_set = self.create_iterate_node_set(parent_node_set)
            self.__iterate_ie = InferenceEngine(self.__iterate_node_set)
            
            if self.__iterate_ie.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterate_ie.add_assessment_into_assessment_list(
                    Assessment(self.__iterate_node_set, self.get_node_name()))

        first_iterate_question_node = parent_node_set.get_node_by_node_id(
            min(parent_node_set.get_dependency_matrix().get_to_child_dependency_list(self.get_node_id()))
        )
        question_node: Optional[Node] = None

        if str(self._value.get_value()) not in parent_ast.get_working_memory().keys():
            if first_iterate_question_node.get_node_name() not in parent_ast.get_working_memory().keys():
                question_node = first_iterate_question_node
            else:
                if not self.can_be_self_evaluated(parent_ast.get_working_memory()):
                    question_node = self.__iterate_ie.get_next_question(
                        self.__iterate_ie.get_assessment_of_rule(self.get_node_name()))

        return question_node

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _create_iterate_node_set_aux(self, parent_dependency_matrix: DependencyMatrix, 
                                     parent_node_dictionary: Dict[str, Node],
                                     parent_node_id_dictionary: Dict[int, str],
                                     this_node_dictionary: Dict[str, Node], 
                                     this_node_id_dictionary: Dict[int, str],
                                     temp_dependency_list: List[Dependency],
                                     original_parent_id: int, 
                                     modified_parent_id: int, 
                                     next_nth_in_string: str) -> None:
        """
        Protected Helper: Auxiliary method for creating iterate node set.
        
        Args:
            parent_dependency_matrix: Parent dependency matrix
            parent_node_dictionary: Parent node dictionary
            parent_node_id_dictionary: Parent node ID dictionary
            this_node_dictionary: Current node dictionary
            this_node_id_dictionary: Current node ID dictionary
            temp_dependency_list: Temporary dependency list
            original_parent_id: Original parent ID
            modified_parent_id: Modified parent ID
            next_nth_in_string: Next nth string representation
        """
        child_dependency_list = parent_dependency_matrix.get_to_child_dependency_list(original_parent_id)

        if len(child_dependency_list) > 0:
            for item in child_dependency_list:
                temp_child_node = parent_node_dictionary[parent_node_id_dictionary[item]]
                line_type = temp_child_node.get_line_type()
                
                temp_node = this_node_dictionary.get(next_nth_in_string + "  " +
                                                     self.get_variable_name() + "  " +
                                                     temp_child_node.get_node_name())
                
                if temp_node is None:
                    if line_type == LineType.VALUE_CONCLUSION:
                        temp_node = ValueConclusionLine(
                            id=None,
                            node_text=next_nth_in_string + "  " + self.get_variable_name() + "  " + temp_child_node.get_node_name(),
                            tokens=temp_child_node.get_tokens())
                    elif line_type == LineType.COMPARISON:
                        temp_node = ComparisonLine(
                            id=None,
                            node_text=next_nth_in_string + "  " + self.get_variable_name() + "  " + temp_child_node.get_node_name(),
                            tokens=temp_child_node.get_tokens())
                    elif line_type == LineType.EXPR_CONCLUSION:
                        temp_node = ExprConclusionLine(
                            id=None,
                            node_text=next_nth_in_string + "  " + self.get_variable_name() + "  " + temp_child_node.get_node_name(),
                            tokens=temp_child_node.get_tokens())

                if temp_node and temp_node.get_node_name() not in this_node_dictionary:
                    this_node_dictionary[temp_node.get_node_name()] = temp_node
                    this_node_id_dictionary[temp_node.get_node_id()] = temp_node.get_node_name()
                    temp_dependency_list.append(
                        Dependency(this_node_dictionary[this_node_id_dictionary[modified_parent_id]],
                                   temp_node,
                                   parent_dependency_matrix.get_dependency_type(original_parent_id, item)))

                    self._create_iterate_node_set_aux(parent_dependency_matrix, parent_node_dictionary,
                                                      parent_node_id_dictionary, this_node_dictionary,
                                                      this_node_id_dictionary, temp_dependency_list,
                                                      item, temp_node.get_node_id(), next_nth_in_string)

    def _transfer_fact_value(self, working_memory_one: Dict[str, Any], 
                             working_memory_two: Dict[str, Any]) -> None:
        """
        Protected Helper: Transfers fact values between working memories.
        
        Args:
            working_memory_one: Source working memory
            working_memory_two: Destination working memory
        """
        key_sets_one = set(working_memory_one.keys())
        for each_key_one in key_sets_one:
            if each_key_one not in working_memory_two.keys():
                working_memory_two[each_key_one] = working_memory_one[each_key_one]

    def _number_of_true_children(self, working_memory: Dict[str, Any]) -> int:
        """
        Protected Helper: Counts number of true children.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            Count of true children
        """
        return len(list(filter(lambda second_target_id:
                               str(working_memory[self.__iterate_ie.get_node_set().get_node_id_dictionary()[
                                    second_target_id]].get_value()).lower() == "true",
                               filter(lambda target_id:
                                      target_id != self._node_id + 1,
                                      self.__iterate_ie.get_node_set().get_dependency_matrix()
                                      .get_to_child_dependency_list(self._node_id)
                                      )
                               )))

    def _find_nth(self, working_memory: Dict[str, Any]) -> int:
        """
        Protected Helper: Finds nth iteration.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            Nth iteration number
        """
        nth_list: List[int] = []
        for index in range(1, self.__given_list_size):
            if working_memory.get(self._ordinal(index) + "  " + self._variable_name) is not None:
                nth_list.append(index)
        return len(nth_list)

    @staticmethod
    def _ordinal(i: int) -> str:
        """
        Protected Helper: Converts number to ordinal string.
        
        Args:
            i: Number to convert
            
        Returns:
            Ordinal string (1st, 2nd, 3rd, etc.)
        """
        suffixes = ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"]
        nth_case = i % 100

        if nth_case == 11 or nth_case == 12 or nth_case == 13:
            return str(i) + 'th'
        else:
            return str(i) + suffixes[i % 10]

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _initialisation(self, parent_text: str, tokens: Token) -> None:
        """
        Protected Helper: Initializes the iterate line.
        
        Args:
            parent_text: Text content of the node
            tokens: Tokenized representation
        """
        _logger.info("Generating Iterate Line with : " + str(parent_text))

        self._node_name = parent_text
        self.__number_of_target = tokens.get_tokens_list()[0]
        self._variable_name = tokens.get_tokens_list()[1]
        token_string_list_size = len(tokens.get_tokens_string_list())
        last_token: str = tokens.get_tokens_list()[token_string_list_size - 1]
        last_token_string: str = tokens.get_tokens_string_list()[token_string_list_size - 1]
        self.set_value(last_token_string, last_token)
        self.__given_list_name = last_token