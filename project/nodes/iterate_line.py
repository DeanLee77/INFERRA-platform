import json
from typing import Union
from project.inference import AssessmentState, Assessment, InferenceEngine, TopologicalSort
from project.loggers import Logger
from project.nodes.node import Node
from project.tokens import Token
from project.nodes.node_set import NodeSet
from project.nodes import ValueConclusionLine, ComparisonLine, ExprConclusionLine, Dependency, LineType, DependencyMatrix, MetaData
from project.fact_values import FactValue, FactValueType


logging: Logger = Logger.get_logger(__name__)


class IterateLine(Node):
    __numberOfTarget = None
    __iterateNodeSet = None
    __givenListName = None
    __givenListSize = 0
    __iterateIE = None

    def __init__(self, id:int=None, parent_text: str=None, tokens: Token=None, meta_data: MetaData=None):
        super().__init__(id=id, parent_text=parent_text, tokens=tokens, meta_data=meta_data)
        self._lineType = LineType.ITERATE

    def __repr__(self):
        return json.dumps(self.__dict__)

    def get_given_list_name(self) -> str:
        return self.__givenListName

    def get_number_of_target(self) -> str:
        return self.__numberOfTarget

    def create_iterate_node_set(self, parent_node_set: NodeSet) -> NodeSet:
        parent_dependency_matrix: DependencyMatrix = parent_node_set.get_dependency_matrix()
        parent_node_dictionary = parent_node_set.get_node_dictionary()
        parent_node_id_dictionary = parent_node_set.get_node_id_dictionary()

        this_node_dictionary = dict()
        this_node_id_dictionary = dict()
        temp_dependency_list = list()
        new_node_set = NodeSet()

        this_node_dictionary[self._nodeName] = self
        this_node_id_dictionary[self._nodeId] = self._nodeName

        for nth in range(1, self.__givenListSize + 1):
            for item in parent_dependency_matrix.get_to_child_dependency_list(self.get_node_id()):
                # not first question id
                if self.get_node_id() + 1 != item:
                    temp_child_node: Node = parent_node_dictionary[parent_node_id_dictionary[item]]
                    line_type = temp_child_node.get_line_type()
                    temp_node: Node = None
                    next_nth_in_string = self.ordinal(nth)

                    if line_type == LineType.VALUE_CONCLUSION:
                        temp_node = ValueConclusionLine(
                            next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name(),
                            temp_child_node.get_tokens())
                    elif line_type == LineType.COMPARISON:
                        temp_node = ComparisonLine(
                            next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name(),
                            temp_child_node.get_tokens())
                        temp_node_fact_value = temp_node.get_rhs()
                        if temp_node_fact_value.get_value_type().value == FactValueType.STRING.value:
                            temp_fact_value = FactValue(
                                next_nth_in_string + " " + self.get_variable_name() + " " +
                                temp_node_fact_value.get_value(),
                                FactValueType.STRING)
                            temp_node.set_value(temp_fact_value)

                    elif line_type == LineType.EXPR_CONCLUSION:
                        temp_node = ExprConclusionLine(
                            next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name(),
                            temp_child_node.get_tokens())

                    this_node_dictionary[temp_node.get_node_name()] = temp_node
                    this_node_id_dictionary[temp_node.get_node_id()] = temp_node.get_node_name()
                    temp_dependency_list.append(
                        Dependency(self, temp_node, parent_dependency_matrix.get_dependency_type(self._nodeId, item)))

                    self.create_iterate_node_set_aux(parent_dependency_matrix, parent_node_dictionary,
                                                     parent_node_id_dictionary, this_node_dictionary,
                                                     this_node_id_dictionary, temp_dependency_list,
                                                     item, temp_node.get_node_id(), next_nth_in_string)

                else:  # first question id
                    first_iterate_question_node: Node = parent_node_set.get_node_by_node_id(
                        min(parent_node_set.get_dependency_matrix().get_to_child_dependency_list(self.get_node_id())))

                    if first_iterate_question_node.get_node_name() not in this_node_dictionary.keys():
                        this_node_dictionary[first_iterate_question_node.get_node_name()] = first_iterate_question_node
                        this_node_id_dictionary[item] = first_iterate_question_node.get_node_name()
                        temp_dependency_list.append(Dependency(self, first_iterate_question_node,
                                                               parent_dependency_matrix.get_dependency_type(
                                                                   self._nodeId, item)))

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

    def create_iterate_node_set_aux(self, parent_dependency_matrix: DependencyMatrix, parent_node_dictionary: dict,
                                    parent_node_id_dictionary: dict,
                                    this_node_dictionary: dict, this_node_id_dictionary: dict,
                                    temp_dependency_list: list,
                                    original_parent_id, modified_parent_id, next_nth_in_string) -> None:
        child_dependency_list = parent_dependency_matrix.get_to_child_dependency_list(original_parent_id)

        if len(child_dependency_list) > 0:
            for item in child_dependency_list:
                temp_child_node = parent_node_dictionary[parent_node_id_dictionary[item]]
                line_type = temp_child_node.get_line_type()
                # temp_node: Node

                # if next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name() \
                #     in this_node_dictionary.keys():
                temp_node = this_node_dictionary.get(next_nth_in_string + " " +
                                                     self.get_variable_name() + " " +
                                                     temp_child_node.get_node_name())
                if temp_node is None:
                    if line_type == LineType.VALUE_CONCLUSION:
                        temp_node = ValueConclusionLine(
                            next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name(),
                            temp_child_node.get_tokens())
                        if parent_node_dictionary[parent_node_id_dictionary[original_parent_id]] \
                                .get_line_type() == LineType.EXPR_CONCLUSION:
                            expr_temp_node: ExprConclusionLine = this_node_dictionary[
                                this_node_id_dictionary[modified_parent_id]]
                            replaced_string = str(expr_temp_node.get_equation().get_value()).replace(
                                temp_child_node.get_node_name(),
                                next_nth_in_string + " " + self.get_variable_name() + " " +
                                temp_child_node.get_node_name()
                            )
                            expr_temp_node.set_value(FactValue(replaced_string, FactValueType.STRING))
                            expr_temp_node.set_equation(FactValue(replaced_string, FactValueType.STRING))
                    elif line_type == LineType.COMPARISON:
                        temp_node = ComparisonLine(
                            next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name(),
                            temp_child_node.get_tokens())
                        temp_node_fv = temp_node.get_rhs()
                        if temp_node_fv.get_value_type() == FactValueType.STRING:
                            temp_fv = FactValue(
                                next_nth_in_string + " " + self.get_variable_name() + " " + temp_node_fv,
                                FactValueType.STRING)
                            temp_node.set_value(temp_fv)
                    elif line_type == LineType.EXPR_CONCLUSION:
                        temp_node = ExprConclusionLine(
                            next_nth_in_string + " " + self.get_variable_name() + " " + temp_child_node.get_node_name(),
                            temp_child_node.get_tokens())
                else:
                    if (line_type == LineType.VALUE_CONCLUSION) and \
                            (parent_node_dictionary[parent_node_id_dictionary[
                                original_parent_id]].get_line_type() == LineType.EXPR_CONCLUSION):
                        expr_temp_node = this_node_dictionary[this_node_id_dictionary[modified_parent_id]]
                        replaced_string = str(expr_temp_node.get_equation().get_value()) \
                            .replace(temp_child_node.get_node_name(),
                                     next_nth_in_string + " " + self.get_variable_name() + " " +
                                     temp_child_node.get_node_name())
                        expr_temp_node.set_value(FactValue(replaced_string, FactValueType.STRING))
                        expr_temp_node.set_equation(FactValue(replaced_string, FactValueType.STRING))

                if temp_node.get_node_name() not in this_node_dictionary:
                    this_node_dictionary[temp_node.get_node_name()] = temp_node
                    this_node_id_dictionary[temp_node.get_node_id()] = temp_node.get_node_name()
                temp_dependency_list.append(
                    Dependency(this_node_dictionary[this_node_id_dictionary[modified_parent_id]],
                               temp_node,
                               parent_dependency_matrix.get_dependency_type(original_parent_id, item)))

                self.create_iterate_node_set_aux(parent_dependency_matrix, parent_node_dictionary,
                                                 parent_node_id_dictionary, this_node_dictionary,
                                                 this_node_id_dictionary, temp_dependency_list,
                                                 item, temp_node.get_node_id(), next_nth_in_string)

    def get_iterate_node_set(self) -> NodeSet:
        return self.__iterateNodeSet

    # this method is used when a givenList exists as a string
    def iterate_feed_answers_with_json(self, given_json_string: Union[str,bytes], parent_node_set: NodeSet,
                                       parent_assessment_state: AssessmentState, assessment: Assessment) -> None:

        # givenJsonString has to be in same format as Example otherwise the engine would NOT be able to enable
        # --------------------------- "givenJsonString" Format ----------------------------
        #       given_json_string = "{
        #    							\"iterateLineVariableName\":
        #							        [
        #								        {
        #       									\"1st iterateLineVariableName\":
        #       										{
        #       										  \"1st iterateLineVariableName ruleNme1\":\"..value..\",
        #       										  \"1st iterateLineVariableName ruleNme2\":\"..value..\"
        #       										}
        #       								 },
        #       								 {
        #       									\"2nd iterateLineVariableName\":
        #       										{
        #       										  \"2nd iterateLineVariableName ruleNme1\":\"..value..\",
        #       										  \"2nd iterateLineVariableName ruleNme2\":\"..value..\"
        #       										}
        #       								 },
        #										]
        #							}"
        # -----------------------------  "given_json_string" Example ----------------------------
        #          given_json_string = "{
        #									\"service\":
        #									    [
        #										  {
        #											\"1st service\":
        #       										{
        #               								  \"1st service period\":\"..value..\",
        #												  \"1st service type\":\"..value..\"
        #												}
        #										  },
        #										  {
        #											\"2nd service\":
        #												{
        #												  \"2nd service period\":\"..value..\",
        #												  \"2nd service type\":\"..value..\"}
        #										  }
        #										]
        #								 }";

        json_object = json.loads(given_json_string)
        service_list = json_object[self._variableName]

        self.__givenListSize = len(service_list)

        if self.__iterateNodeSet is None:
            self.__iterateNodeSet = self.create_iterate_node_set(parent_node_set)
            self.__iterateIE = InferenceEngine(self.__iterateNodeSet)
            
            if self.__iterateIE.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterateIE.add_assessment_into_assessment_list(Assessment(self.__iterateNodeSet, self.get_node_name()))
                # self.__iterateIE.set_assessment(Assessment(self.__iterateNodeSet, self.get_node_name()))

        while self._nodeName not in self.__iterateIE.get_assessment_state().get_working_memory().keys():
            next_question_node: Node = self.get_iterate_next_question(parent_node_set, parent_assessment_state)
            answer = ""
            question_fvt_map = self.__iterateIE.find_type_of_element_to_be_asked(next_question_node)
            for question in self.__iterateIE.get_questions_from_node_to_be_asked(next_question_node):
                answer = str(json_object[self._variableName]
                             [next_question_node.get_variable_name()[
                              0: next_question_node.get_variable_name().rindex(self._variableName) + len(
                                  self._variableName)]]
                             [next_question_node.get_variable_name()]).strip()

                self.__iterateIE.feed_answer_to_node(next_question_node, question, FactValue(answer),
                                                     self.__iterateIE.get_assessment_of_rule(self.get_node_name()))

            iterate_working_memory = self.__iterateIE.get_assessment_state().get_working_memory()
            parent_working_memory = parent_assessment_state.get_working_memory()

            self.transfer_fact_value(iterate_working_memory, parent_working_memory)

    # this method is used when a givenList does NOT exist
    def iterate_feed_answers(self, target_node: Node, question_name: str, node_value: any,
                             node_value_type: FactValueType, parent_node_set: NodeSet,
                             parent_ast: AssessmentState, ass: Assessment) -> None:
        if self.__iterateNodeSet is None:
            first_iterate_question_node = parent_node_set.get_node_by_node_id(
                min(parent_node_set.get_dependency_matrix().get_to_child_dependency_list(self.get_node_id()))
            )
            if question_name == first_iterate_question_node.get_node_name():
                self.__givenListSize = int(node_value)

            self.__iterateNodeSet = self.create_iterate_node_set(parent_node_set)
            self.__iterateIE = InferenceEngine(self.__iterateNodeSet)

            self.__iterateIE.get_assessment_of_rule(self.get_node_name())

            if self.__iterateIE.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterateIE.add_assessment_into_assessment_list(Assessment(self.__iterateNodeSet, self.get_node_name()))
                # self.__iterateIE.set_assessment(Assessment(self.__iterateNodeSet, self.get_node_name()))

        self.__iterateIE.get_assessment_of_rule(self.get_node_name()).set_node_to_be_asked(target_node)
        self.__iterateIE.feed_answer_to_node(target_node, question_name, node_value,
                                             node_value_type, self.__iterateIE.get_assessment_of_rule(self.get_node_name()))

        iterate_working_memory = self.__iterateIE.get_assessment_state().get_working_memory()
        parent_working_memory = parent_ast.get_working_memory()

        self.transfer_fact_value(iterate_working_memory, parent_working_memory)

    def transfer_fact_value(self, working_memory_one: dict, working_memory_two: dict) -> None:
        key_sets_one = set(working_memory_one.keys())
        for each_key_one in key_sets_one:
            if each_key_one not in working_memory_two.keys():
                working_memory_two[each_key_one] = working_memory_one[each_key_one]

    def get_iterate_next_question(self, parent_node_set: NodeSet, parent_ast: AssessmentState) -> Node:
        if self.__iterateNodeSet is None and self.__givenListSize != 0:
            self.__iterateNodeSet = self.create_iterate_node_set(parent_node_set)
            self.__iterateIE = InferenceEngine(self.__iterateNodeSet)
            
            if self.__iterateIE.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterateIE.add_assessment_into_assessment_list(Assessment(self.__iterateNodeSet, self.get_node_name()))
                # self.__iterateIE.set_assessment(Assessment(self.__iterateNodeSet, self.get_node_name()))

        first_iterate_question_node = parent_node_set.get_node_by_node_id(
            min(parent_node_set.get_dependency_matrix().get_to_child_dependency_list(self.get_node_id()))
        )
        question_node: Node

        if str(self._value.get_value()) not in parent_ast.get_working_memory().keys():
            if first_iterate_question_node.get_node_name() not in parent_ast.get_working_memory().keys():
                question_node = first_iterate_question_node
            else:
                if not self.can_be_self_evaluated(parent_ast.get_working_memory()):
                    question_node = self.__iterateIE.get_next_question(self.__iterateIE.get_assessment_of_rule(self.get_node_name()))

        return question_node

    def find_n_th(self, working_memory: dict) -> int:
        n_th_list: list = []
        for index in range(1, self.__givenListSize):
            if working_memory[self.ordinal(index) + " " + self._variableName] is not None:
                n_th_list.append(index)
        return len(n_th_list)

    def ordinal(self, i: int):
        suffixes = ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"]
        nth_case = i % 100

        if nth_case == 11 or nth_case == 12 or nth_case == 13:
            return str(i) + 'th'
        else:
            return str(i) + suffixes[i % 10]

    def initialisation(self, parent_text: str, tokens: Token) -> None:
        logging.info("Generating Iterate Line with : " + str(parent_text))

        self._nodeName = parent_text
        self.__numberOfTarget = tokens.get_tokens_list()[0]
        self._variableName = tokens.get_tokens_list()[1]
        token_string_list_size = len(tokens.get_tokens_string_list())
        last_token: str = tokens.get_tokens_list()[token_string_list_size - 1]
        last_token_string: str = tokens.get_tokens_string_list()[token_string_list_size - 1]
        self.set_value(last_token_string, last_token)
        self.__givenListName = last_token

    def get_line_type(self) -> LineType:
        return LineType.ITERATE

    def can_be_self_evaluated(self, working_memory: dict) -> bool:
        if self.__iterateIE is not None:
            out_fact_value: FactValue = None
            number_of_determined_second_level_node = \
                filter(lambda target_id:
                       working_memory.get(
                           self.__iterateIE.get_node_set().get_node_id_dictionary().get(target_id)) is not None \
                       and working_memory.get(
                           self.__iterateIE.get_node_set().get_node_id_dictionary().get(
                               target_id)).get_value() is not None,
                       filter(lambda i: i is not self._nodeId + 1,
                              self.__iterateIE.get_node_set().get_dependency_matrix().get_to_child_dependency_list(
                                  self._nodeId)
                              )
                       )

            if self.__givenListSize == len(list(number_of_determined_second_level_node)) \
                    and self.__iterateIE.has_all_mandatory_child_answered(self._nodeId):
                return True

        return False

    def self_evaluate(self, working_memory: dict) -> FactValue:
        number_if_true_children: int = self.number_of_true_children(working_memory)
        size_of_given_list = self.__givenListSize

        fact_boolean_value: FactValue = None

        if self.__numberOfTarget == "ALL":
            if number_if_true_children == self.__givenListSize:
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)
        elif self.__numberOfTarget == "NONE":
            if number_if_true_children == 0:
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)
        elif self.__numberOfTarget == "SOME":
            if number_if_true_children > 0:
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)
        else:
            if number_if_true_children == int(self.__numberOfTarget):
                fact_boolean_value = FactValue(True)
            else:
                fact_boolean_value = FactValue(False)

        return fact_boolean_value

    def number_of_true_children(self, working_memory: dict) -> int:
        return len(list(filter(lambda second_target_id:
                               str(working_memory[self.__iterateIE.get_node_set().get_node_id_dictionary()[
                                   second_target_id]].get_value()).lower() == "true",
                               filter(lambda target_id:
                                      target_id != self._nodeId + 1,
                                      self.__iterateIE.get_node_set().get_dependency_matrix()
                                      .get_to_child_dependency_list(self._nodeId)
                                      ))
                        ))
