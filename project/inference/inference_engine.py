import json
from datetime import *
from project.fact_values import FactValue, FactValueType
from project.inference import Assessment, AssessmentState
from project.inference.assesments import Assessments
from project.inference.question_resolver import QuestionResolver
from project.nodes import ComparisonLine, ValueConclusionLine, DependencyType, LineType
from project.nodes.node import Node
from project.nodes.node_set import NodeSet
from project.loggers import Logger


logging: Logger = Logger.get_logger(__name__)


class InferenceEngine:
    __nodeSet: NodeSet
    __targetNode: Node
    __ast: AssessmentState
    __ass: Assessment
    __asses: Assessments
    __nodeFactList: list
    __questionResolver: QuestionResolver

    def __init__(self, node_set: NodeSet = None):
        self.__nodeSet = node_set
        self.__targetNode = None
        self.__ast = self.new_assessment_state()
        self.__ass = Assessment()
        self.__asses = Assessments()
        self.__nodeFactList = list()  # contains all rules set as a fact given by a user from a ruleList
        self.__questionResolver = QuestionResolver(lambda _: None)

        temp_fact_dict = node_set.get_fact_dictionary() if node_set is not None else {}
        temp_working_memory = self.__ast.get_working_memory()

        if len(temp_fact_dict) > 0:
            for key in temp_fact_dict.keys():
                temp_working_memory[key] = temp_fact_dict[key]


    # def __repr__(self):
    #     return json.dumps(self.__dict__)
    
    # def __getstate__(self):
    #     def serialiseList(list):
    #         serialisedList = []
    #         for item in list:
    #             serialisedList.append(item.__getstate__())
            
    #         return serialisedList
        
    #     # Serialize the object's state into a dictionary
    #     state = {
    #         "_InferenceEngine__nodeSet": self.__nodeSet.__getstate__() if self.__nodeSet != None else None,
    #         "_InferenceEngine__targetNode": self.__targetNode.__getstate__() if self.__targetNode != None else None,
    #         "_InferenceEngine__ast": self.__ast.__getstate__(),
    #         "_InferenceEngine__ass": self.__ass.__getstate__() if self.__ass != None else None,
    #         "_InferenceEngine__nodeFactList": serialiseList(self.__nodeFactList)
    #     }
    #     return state

    # def __setstate__(self, state):
    #     def deserialseList(serialisedList):
    #         deserialsedList = []
    #         for item in serialisedList:
    #             deserialsedList.append(LineType.get_appropriate_node_type(item['_lineType']['name']).__setstate__(item))
            
    #         return deserialsedList

    #     # Deserialize the object's state from the provided dictionary
    #     nodeSet = NodeSet()
    #     self.__nodeSet = nodeSet.__setstate__(state["_InferenceEngine__nodeSet"])
        
    #     LineType.get_appropriate_node_type(state["_InferenceEngine__targetNode"]['_linetype']['name'])\
    #             .__setstate__(state["_InferenceEngine__targetNode"])

    #     ass = Assessment()
    #     self.__ass = ass.__setstate__(state["_InferenceEngine__ass"])

    #     self.__ast = jsonpickle.decode(state["_InferenceEngine__ast"])        
    #     self.__nodeFactList = deserialseList(state["_InferenceEngine__nodeFactList"])
        

    def set_node_set(self, node_set: NodeSet):
        self.__nodeSet = node_set
        self.__ast = self.new_assessment_state()
        temp_fact_dict = node_set.get_fact_dictionary()
        temp_working_memory = self.__ast.get_working_memory()

        if len(temp_fact_dict) > 0:
            for key in temp_fact_dict.keys():
                temp_working_memory[key] = temp_fact_dict[key]

    def get_node_set(self) -> NodeSet:
        return self.__nodeSet

    def get_assessment_state(self) -> AssessmentState:
        return self.__ast

    def new_assessment_state(self) -> AssessmentState:
        # initial_size = len(self.__nodeSet.get_sorted_node_list()) * 2
        ast = AssessmentState()
        # inclusive_list = [None] * initial_size
        # summary_list = [None] * initial_size
        # ast.set_inclusive_list(inclusive_list)
        # ast.set_summary_list(summary_list)

        return ast

    def set_assessments(self, asses: Assessments):
        self.__asses = asses

    def get_assessments(self) -> Assessments:
        return self.__asses
    
    def add_assessment_into_assessment_list(self, assessment: Assessment):
        self.__asses.add_assessment(assessment)

    def get_assessment_of_rule(self, goal_rule_name: str):
        return self.__asses.get_assessment(goal_rule_name)
    
    def set_assessment(self, ass: Assessment):
        self.__ass = ass

    def get_assessment(self) -> Assessment:
        return self.__ass

    def get_list_of_variable_name_and_value_of_nodes(self) -> list[str]:
        """
        this method is to extract all variableName of Nodes, and put them into a list[str]
        it may be useful to display and ask a user to select which information they do have
        even before starting Inference process
        """
        variable_name_list: list = []
        for each_node in self.__nodeSet.get_node_dictionary().values():
            if len(self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list()[each_node.get_node_id()]) == 0:
                variable_name_list.append(each_node.get_variable_name())
                node_fact_value_type: FactValueType = each_node.get_fact_value().get_value_type()

                if (node_fact_value_type == FactValueType.STRING) or (node_fact_value_type == FactValueType.TEXT):
                    variable_name_list.append(str(each_node.get_fact_value().get_value()))

        return variable_name_list

    
    def add_node_fact(self, node_variable_name: str, fv: FactValue) -> None:
        """
        this method allows to store all information via GUI even before starting Inference process
        """
        for each_node in self.__nodeSet.get_node_dictionary().values():
            if (each_node.get_variable_name() == node_variable_name) or \
                    (str(each_node.get_fact_value().get_value()) == node_variable_name):
                self.__nodeFactList.append(each_node)
        self.__ast.get_working_memory()[node_variable_name] = fv

    
    def find_relevant_factors(self) -> list:
        """
        this method is to find all relevant Nodes(immediate child nodes of the most parent) with given information
        while finding out all relevant factors, all given information will be stored in AssessmentState.workingMemory
        """
        relevant_factor_list: list = []
        if len(self.__nodeFactList) > 0:
            for each_node in self.__nodeFactList:
                if len(self.__nodeSet.get_dependency_matrix()
                               .get_from_parent_dependency_list(each_node.get_node_id())) != 0:
                    relevant_node = self.aux_find_relevant_factors(each_node)
                    relevant_factor_list.append(relevant_node)
        return relevant_factor_list

    def aux_find_relevant_factors(self, target_node: Node) -> Node:
        relevant_factor_node: Node = None
        incoming_dependency_list = self.__nodeSet.get_dependency_matrix() \
            .get_from_parent_dependency_list()(
            target_node.get_node_id())  # it contains all id of parent node where dependency come from
        if len(incoming_dependency_list) > 0:
            for i in range(len(incoming_dependency_list)):
                parent_node: Node = self.__nodeSet.get_node_dictionary()[
                    self.__nodeSet.get_node_id_dictionary()[
                        incoming_dependency_list[i]
                    ]
                ]

                if (len(self.__nodeSet.get_dependency_matrix().get_from_parent_dependency_list(
                        parent_node.get_node_id())) > 0) and \
                        (parent_node.get_node_name() != self.__nodeSet.get_sorted_node_list()[0].get_node_name()):
                    relevant_factor_node = self.aux_find_relevant_factors(parent_node)
        return relevant_factor_node

    def get_next_question_with_goal_name(self, goal_name:str) -> Node:
        """
        this method uses a function, get_next_question() which uses 'BACKWARD-CHAINING'. 
        In order to support multiple assessments on a multiple root node in rule set group,
        it needs capability of next question retrieval with its goal name from the target assessment.
        """
        assessment = self.__asses.get_assessment(goal_name)
        return self.get_next_question(assessment)
        
    def get_next_question(self, ass: Assessment) -> Node:
        """
        this method uses 'BACKWARD-CHAINING', and it will return node to be asked of a given assessment, which has not
        been determined and does not have any child nodes if the goal node of the given assessment has still
        not been determined.
        """
        if ass.get_goal_node().get_node_name() not in self.get_assessment_state().get_inclusive_list():
            self.__ast.get_inclusive_list().append(ass.get_goal_node().get_node_name())

        #  Default goal rule of a rule set which is a parameter of InferenceEngine will be evaluated by forwardChaining
        #  when any rule is evaluated within the rule set
        if (self.__ast.get_working_memory().get(ass.get_goal_node().get_node_name()) is None) or \
                (not self.__ast.all_mandatory_node_determined()):
            for index in range(ass.get_goal_node_index(), len(self.__nodeSet.get_sorted_node_list())):
                target_node: Node = self.__nodeSet.get_sorted_node_list()[index]

                # Step1. does the rule currently being been checked have child rules && not yet evaluated && is in the
                # inclusiveList?
                #    if no then ask a user to evaluate the rule,
                #       and do back propagating with a result of the evaluation (note that this part will be handled
                #       in feed_answer())
                #    if yes then move on to following step
                # Step2. does the rule currently being been checked have child rules?
                #    if yes then add the child rules into the inclusiveList
                node_id = target_node.get_node_id()
                if index != ass.get_goal_node_index():
                    parent_dependency_list: list = self.__nodeSet.get_dependency_matrix() \
                        .get_from_parent_dependency_list(node_id)
                    if len(parent_dependency_list) > 0:
                        for parent_id in parent_dependency_list:
                            if self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_id, node_id) != -1 \
                                    and self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_id, node_id) \
                                    & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                                    and not self.__ast.is_in_inclusive_list(target_node.get_node_name()) \
                                    and not self.is_iterate_line_child(target_node.get_node_id()):
                                self.__ast.add_item_to_mandatory_list(target_node.get_node_name())
                if node_id != ass.get_goal_node().get_node_id() \
                        and target_node.get_line_type() == LineType.ITERATE \
                        and target_node.get_node_name() not in self.__ast.get_working_memory().keys():
                    given_list_name_fv: FactValue = None
                    if target_node.get_given_list_name() in self.__ast.get_working_memory().keys():
                        given_list_name_fv: FactValue = self.__ast.get_working_memory()[
                            target_node.get_given_list_name()]
                    given_list_name: str = ''
                    if given_list_name_fv is not None:
                        given_list_name = str(given_list_name_fv.get_value()).strip()
                    if len(given_list_name) > 0:
                        target_node.iterate_feed_answers_with_json(given_list_name, self.__nodeSet, self.__ast, ass)
                    else:
                        if target_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                                and target_node.get_node_name() not in self.__ast.get_exclusive_list():
                            ass.set_node_to_be_asked(target_node)
                            index_of_rule_to_be_asked: int = index
                            logging.info("index Of Rule To Be Asked : " + str(index_of_rule_to_be_asked))
                            next_question_from_iterate_node: Node = target_node.get_iterate_next_question(
                                self.__nodeSet,
                                self.__ast)
                            # this is to treat the node as IterateLine node
                            ass.set_aux_node_to_be_asked(next_question_from_iterate_node)

                            return next_question_from_iterate_node

                elif not self.has_children(node_id) \
                        and target_node.get_node_name() in self.__ast.get_inclusive_list() \
                        and self.__questionResolver.find_next_question_node(
                            target_node,
                            self.__ast.get_working_memory(),
                            has_children=False,
                        ) is not None \
                        and not self.can_evaluate(target_node):
                    ass.set_node_to_be_asked(target_node)
                    index_of_rule_to_be_asked: int = index
                    logging.info("index Of Rule To Be Asked : " + str(index_of_rule_to_be_asked))

                    return ass.get_node_to_be_asked()
                elif self.has_children(node_id) \
                        and target_node.get_variable_name() not in self.__ast.get_working_memory().keys() \
                        and target_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                        and target_node.get_node_name() in self.__ast.get_inclusive_list():
                    self.add_child_rule_into_inclusive_list(target_node)

        next_question_node: Node = ass.get_node_to_be_asked()
        if next_question_node is not None and next_question_node.get_line_type() == LineType.ITERATE:
            ass.set_aux_node_to_be_asked(next_question_node)

        return next_question_node

    def get_questions_from_node_to_be_asked(self, node_to_be_asked: Node) -> list:
        question_list: list = []
        line_type_of_node_to_be_asked: LineType = node_to_be_asked.get_line_type()
        # the most child node line types are as follows
        # ValueConclusionLine type
        if line_type_of_node_to_be_asked == LineType.VALUE_CONCLUSION:
            # if the line format is 'A -statement' then node's nodeName and variableName has same value so that either
            # of them can be asked as a question.
            # if the line format is 'A IS IN LIST B' then the value of node's variableName is 'A' and the value of
            # node's value is 'B' so that only 'A' needs to be asked.
            # list 'B' has to be provided in 'FIXED' list
            #
            # In conclusion, if the line type is 'ValueConclusionLine' then node's variableName should be asked
            # regardless its format
            question_list.append(node_to_be_asked.get_variable_name())
        # ComparisonLine type
        elif line_type_of_node_to_be_asked == LineType.COMPARISON:
            if node_to_be_asked.get_lhs() not in self.__ast.get_working_memory().keys():
                question_list.append(node_to_be_asked.get_lhs())

            if not self.__type_already_set(node_to_be_asked.get_fact_value()) \
                    and str(node_to_be_asked.get_rhs().get_value()) not in self.__ast.get_working_memory().keys():
                question_list.append(str(node_to_be_asked.get_fact_value().get_value()))

        for item in question_list:
            self.__ast.get_inclusive_list().append(item)

        return question_list

    def find_type_of_element_to_be_asked(self, target_node: Node) -> dict:
        # FactValueType can be handled as of 16/06/2017 is as follows;
        #  1. TEXT, STRING;
        #  2.INTEGER, NUMBER;
        #  3.DOUBLE, DECIMAL;
        #  4.BOOLEAN;
        #  5.DATE;
        #  6.HASH;
        #  7.UUID; and
        #  8.URL.
        #  rest of them (LIST, RULE, RULE_SET, OBJECT, UNKNOWN, NULL) can't be handled at this stage
        fact_value_type: FactValueType = None
        fact_value_type_dictionary: dict = {}

        # In a case of that if type of toBeAsked node is ComparisonLine type with following conditions;
        #    - the type of the node's variable to compare is already set as
        #      DefiString (eg. 'dean' or "dean"), Integer (eg. 1, or 2), Double (eg. 1.2 or 2.1), Date (eg. 21/3/1299),
        #      Hash, UUID, or URL
        #   then don't need to look into InputMap or FactMap to check the element's type of 'toBeAsked node'
        #   simply because we can check by looking at type of value variable because two different type
        #   CANNOT be compared
        #
        # If neither type of variable is NOT defined in INPUT/FACT list nor the above case, and value of nodeVariable
        # is same as value of nodeValueString then the engine will recognise a nodeVariable or/and nodeVlaue
        # as a boolean type
        # so that the question for a nodeVariable or/and a nodeValue seeks boolean type of answer

        node_variable_name: str = target_node.get_variable_name()
        node_value_string: str = str(target_node.get_fact_value().get_value())
        type_already_set: bool = self.__type_already_set(target_node.get_fact_value())
        temp_fact_dictionary: dict = self.__nodeSet.get_fact_dictionary()
        temp_input_dictionary: dict = self.__nodeSet.get_input_dictionary()
        node_line_type: LineType = target_node.get_line_type()

        # ComparisonLine type node and type of the node's value is clearly defined
        if LineType.COMPARISON == node_line_type:
            comparison: ComparisonLine = target_node
            node_rhs_type: FactValueType = comparison.get_rhs().get_value_type()

            if FactValueType.STRING != node_rhs_type:
                if FactValueType.DEFI_STRING == node_rhs_type:
                    fact_value_type = FactValueType.STRING
                elif type_already_set is True:
                    fact_value_type = node_rhs_type
                fact_value_type_dictionary[comparison.get_lhs()] = fact_value_type
            elif FactValueType.STRING == node_rhs_type:
                if comparison.get_lhs() in temp_input_dictionary.keys():
                    fact_value_type = temp_input_dictionary[comparison.get_lhs()].get_value_type()
                elif str(comparison.get_rhs().get_value()) in temp_input_dictionary.keys():
                    fact_value_type = temp_input_dictionary[str(comparison.get_rhs().get_value())].get_value_type()
                elif comparison.get_lhs() in temp_fact_dictionary.keys():
                    fact_value_type = temp_fact_dictionary[comparison.get_lhs()].get_value_type()
                elif str(comparison.get_rhs().get_value()) in temp_fact_dictionary.keys():
                    fact_value_type = temp_fact_dictionary[str(comparison.get_rhs().get_value())].get_value_type()

                fact_value_type_dictionary[comparison.get_lhs()] = fact_value_type
                fact_value_type_dictionary[str(comparison.get_rhs().get_value())] = fact_value_type

        # ComparisonLine type node and type of the node's value is not clearly defined
        # and not defined in INPUT nor FIXED list
        # ValueConclusionLine type node, and it is 'A-statement' line,
        # and variableName is not defined neither INPUT nor FIXED
        elif LineType.VALUE_CONCLUSION == node_line_type:
            if node_variable_name in temp_input_dictionary.keys():
                fact_value_type = temp_input_dictionary[node_variable_name].get_value_type()
            elif node_value_string in self.__ast.get_working_memory().keys():
                temp_fact_value: FactValue = self.__ast.get_working_memory()[node_value_string]
                if FactValueType.LIST.value == temp_fact_value.get_value_type().value:
                    fact_value_type = temp_fact_value.get_value()[0].get_value_type()
                else:
                    fact_value_type = temp_fact_value.get_value_type()
            else:
                fact_value_type = FactValueType.BOOLEAN

            fact_value_type_dictionary[node_variable_name] = fact_value_type

        return fact_value_type_dictionary

    def __type_already_set(self, input_fact_value: FactValue) -> bool:
        has_already_set_type = False
        fact_value_type: FactValueType = input_fact_value.get_value_type()

        if FactValueType.DEFI_STRING == fact_value_type or FactValueType.INTEGER == fact_value_type \
                or FactValueType.DOUBLE == fact_value_type or FactValueType.DATE == fact_value_type \
                or FactValueType.BOOLEAN == fact_value_type or FactValueType.GUID == fact_value_type \
                or FactValueType.URL == fact_value_type or FactValueType.HASH == fact_value_type:
            has_already_set_type = True

        return has_already_set_type

    def is_iterate_line_child(self, node_id: int) -> bool:
        is_iterate_line_child = False
        temp_list: list = []
        iterate_line_list: list = list(filter(lambda target_node: target_node.get_line_type() == LineType.ITERATE,
                                              self.__nodeSet.get_node_dictionary().values()))
        for i_node in iterate_line_list:
            iterate_child_node_list: list = self.__nodeSet.get_dependency_matrix() \
                .get_to_child_dependency_list(i_node.get_node_id())

            if node_id in iterate_child_node_list:
                temp_list.append(1)
            else:
                self.is_iterate_line_child_aux(temp_list, iterate_child_node_list, node_id)

        if len(temp_list) > 0:
            is_iterate_line_child = True
        else:
            if self.__nodeSet.get_node_id_dictionary()[node_id] in self.get_assessment_state().get_mandatory_list():
                self.get_assessment_state().get_mandatory_list().remove(
                    self.__nodeSet.get_node_id_dictionary()[node_id])

        return is_iterate_line_child

    def is_iterate_line_child_aux(self, temp_list: list, iterate_child_node_list: list, node_id: int):
        for each_id in iterate_child_node_list:
            iterate_child_node_list_aux = self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list(each_id)
            if node_id in iterate_child_node_list:
                temp_list.append(1)
            else:
                self.is_iterate_line_child_aux(temp_list, iterate_child_node_list_aux, node_id)
    
    def can_evaluate(self, target_node: Node) -> bool:
        """
        This is to check whether a node can be evaluated with all information in the workingMemory.
        If there is information for a value of node's value(FactValue) or variableName,
        then the node can be evaluated otherwise not.
        In order to do it, AssessmentState.workingMemory must contain a value for variable of the rule,
        and rule type must be either COMPARISON, ITERATE or VALUE_CONCLUSION
        because they are the ones only can be the most child nodes, and other type of node must be a parent
        of other types of node.
        """
        can_be_evaluate = False
        line_type: LineType = target_node.get_line_type()

        if LineType.VALUE_CONCLUSION == line_type:
            value_conclusion: ValueConclusionLine = target_node

            if value_conclusion.get_is_plain_statement() and value_conclusion.get_variable_name() in self.__ast.get_working_memory():
                # If the node is in plain statement format then variableName has a same value as nodeName,
                # and if a value for either variableName or nodeName of the node is in workingMemory then it means the
                # node has already been evaluated.
                # Hence, 'canEvaluate' needs to be 'true' in this case.
                can_be_evaluate = True
            elif len(
                    list(filter(lambda token_string: token_string == "IS IN LIST:",
                                value_conclusion.get_tokens().get_tokens_list()))) > 0 \
                    and str(value_conclusion.get_fact_value().get_value()) in self.__ast.get_working_memory().keys() \
                    and value_conclusion.get_variable_name() in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                fact_value: FactValue = value_conclusion.self_evaluate(self.__ast.get_working_memory())

                # the reason why self.__ast.set_fact() is used here rather than self.feed_answer_to_node() is
                # that LineType is already known, and target node object is already found.
                # node.self_evaluation() returns a value of the node's self-evaluation hence,
                # node.get_node_name() is used to store a value for the node itself into a workingMemory
                self.__ast.set_fact(value_conclusion.get_node_name(), fact_value, value_conclusion)

        elif LineType.COMPARISON == line_type:
            comparison: ComparisonLine = target_node
            node_rhs_value: FactValue = comparison.get_rhs()
            if FactValueType.STRING != node_rhs_value.get_value_type() \
                    and comparison.get_lhs() in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                if comparison.get_node_name() not in self.__ast.get_working_memory().keys():
                    self.__ast.set_fact(comparison.get_node_name(),
                                        comparison.self_evaluate(self.__ast.get_working_memory()))
            elif FactValueType.STRING == node_rhs_value.get_value_type() \
                    and comparison.get_lhs() in self.__ast.get_working_memory().keys() \
                    and str(comparison.get_rhs().get_value()) in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                if comparison.get_node_name() not in self.__ast.get_working_memory().keys():
                    self.__ast.set_fact(comparison.get_node_name(),
                                        comparison.self_evaluate(self.__ast.get_working_memory()),
                                        comparison)

        return can_be_evaluate

    def feed_answer_to_node(self, target_node: Node, question_name: str, node_value: any,
                            node_value_type: FactValueType, ass: Assessment):
        """
        This method is to add fact or set a node as a fact by using AssessmentState.setFact() method.
        It also is used to feed an answer to a being asked node. Once a fact is added then forward-chain is used
        to update all effected nodes' state, and workingMemory in AssessmentState class will be updated accordingly.
        The reason for taking nodeName instead nodeVariableName is that it will be easier to find an exact node with
        nodeName rather than nodeVariableName because a certain nodeVariableName could be found in several nodes.
        """
        fact_value: FactValue = None
        if FactValueType.BOOLEAN == node_value_type:
            if isinstance(node_value, bool):
                fact_value = FactValue(node_value, FactValueType.BOOLEAN)
            elif isinstance(node_value, str):
                fact_value = FactValue(eval(node_value.title()), FactValueType.BOOLEAN)
        elif FactValueType.DATE == node_value_type:
            # the string of nodeValue date format is dd / MM / YYYY
            fact_value = FactValue(node_value, FactValueType.DATE)
        elif FactValueType.DOUBLE == node_value_type:
            fact_value = FactValue(float(str(node_value)))
        elif FactValueType.INTEGER == node_value_type:
            fact_value = FactValue(int(node_value))
        elif FactValueType.LIST == node_value_type:
            fact_value = FactValue(node_value, FactValueType.LIST)
        elif FactValueType.STRING == node_value_type:
            fact_value = FactValue(str(node_value))
        elif FactValueType.DEFI_STRING == node_value_type:
            fact_value = FactValue(str(node_value), FactValueType.DEFI_STRING)
        elif FactValueType.HASH == node_value_type:
            fact_value = FactValue(str(node_value))
        elif FactValueType.URL == node_value_type:
            fact_value = FactValue(str(node_value))
        elif FactValueType.GUID == node_value_type:
            fact_value = FactValue(str(node_value))

        if fact_value is not None and LineType.ITERATE != ass.get_node_to_be_asked().get_line_type():
            self.__ast.set_fact(question_name, fact_value)
            # add currentRule into SummeryList as the rule determined
            self.__ast.add_item_to_summary_list(question_name)

            if LineType.VALUE_CONCLUSION == target_node.get_line_type() \
                    and not target_node.get_is_plain_statement():
                self_eval_fact_value: FactValue = target_node.self_evaluate(self.__ast.get_working_memory())
                # add the value of target_node itself into the workingMemory
                self.__ast.set_fact(target_node.get_node_name(), self_eval_fact_value)
                # add currentRule into SummeryList as the rule determined
                self.__ast.add_item_to_summary_list(target_node.get_node_name())
            elif LineType.COMPARISON == target_node.get_line_type():
                rhs_value: FactValue = target_node.get_rhs()
                if (FactValueType.STRING == rhs_value.get_value_type()
                    and str(rhs_value.get_value()) in self.__ast.get_working_memory().keys()) \
                        or FactValueType.STRING != rhs_value.get_value_type():
                    self_eval_fact_value: FactValue = target_node.self_evaluate(self.__ast.get_working_memory())
                    # add the value of targetNode itself into the workingMemory
                    self.__ast.set_fact(target_node.get_node_name(), self_eval_fact_value)
                    # add currentRule into SummeryList as the rule determined
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())

            # once any rules are set as fact and stored into the workingMemory,
            # back-propagation(forward-chaining) needs to be done
            self.back_propagating(self.__nodeSet.find_node_index(target_node.get_node_name()))

        elif LineType.ITERATE == ass.get_node_to_be_asked().get_line_type():
            target_node = ass.get_aux_node_to_be_asked()
            ass.get_node_to_be_asked().iterate_feed_answers(target_node,
                                                            question_name,
                                                            node_value,
                                                            node_value_type,
                                                            self.__nodeSet,
                                                            self.__ast,
                                                            ass)

            if ass.get_node_to_be_asked().can_be_self_evaluated(self.__ast.get_working_memory()):
                self.back_propagating(self.__nodeSet.find_node_index(ass.get_node_to_be_asked().get_node_name()))

    def back_propagating(self, node_index: int) -> None:
        node_sorted_list: list = self.__nodeSet.get_sorted_node_list()
        sorted_list_size: int = len(node_sorted_list)
        for i in range(0, sorted_list_size):
            current_index = sorted_list_size - (i + 1)
            temp_node: Node = node_sorted_list[current_index]
            line_type: LineType = temp_node.get_line_type()
            temp_node_id: int = temp_node.get_node_id()
            parent_dependency_list: list = \
                self.__nodeSet.get_dependency_matrix().get_from_parent_dependency_list(temp_node_id)
            if len(parent_dependency_list) > 0:
                for parent_id in parent_dependency_list:
                    dependency_type = \
                        self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_id, temp_node_id)
                    if dependency_type != -1 \
                            and dependency_type & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                            and not self.__ast.is_in_inclusive_list(temp_node.get_node_name()) \
                            and not self.is_iterate_line_child(temp_node.get_node_id()):
                        self.__ast.add_item_to_mandatory_list(temp_node.get_node_name())

            # case of all nodes located after the nodeIndex
            if node_index < (current_index):
                if self.has_children(temp_node.get_node_id()):
                    if temp_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                            and self.can_determine(temp_node, line_type):
                        if LineType.EXPR_CONCLUSION != line_type:
                            # add currentRule into SummeryList as the rule determined
                            self.__ast.add_item_to_summary_list(temp_node.get_node_name())
                else:
                    # ValueConclusionLine in 'A-statement' format does not need to be considered here due to the
                    # reason that the case should be in the workingMemory if it is already asked.
                    if LineType.VALUE_CONCLUSION == line_type \
                            and not temp_node.get_is_plain_statement() \
                            and temp_node.get_variable_name() in self.__ast.get_working_memory().keys():
                        fact_value: FactValue = temp_node.self_evaluate(self.__ast.get_working_memory())
                        self.__ast.set_fact(temp_node.get_node_name(), fact_value)

                        # add currentRule into SummeryList as the rule determined
                        self.__ast.add_item_to_summary_list(temp_node.get_node_name())
                    elif LineType.COMPARISON == line_type \
                            and temp_node.get_lhs() in self.__ast.get_working_memory().keys() \
                            and (
                            (FactValueType.STRING == temp_node.get_rhs().get_value_type() and str(
                                temp_node.get_rhs().get_value()) in self.__ast.get_working_memory().keys()) \
                            or (FactValueType.STRING != temp_node.get_rhs().get_value_type())):
                        fact_value: FactValue = temp_node.self_evaluate(self.__ast.get_working_memory())
                        self.__ast.set_fact(temp_node.get_node_name(), fact_value)
                        # add currentRule into SummeryList as the rule determined
                        self.__ast.add_item_to_summary_list(temp_node.get_node_name())
            # case of all nodes located before the nodeIndex
            else:
                #  The tempNode is located before the nodeIndex then there is need to check whether the tempNode is
                #  in the inclusiveList due to the reason that evaluating only relevant node could speed the
                #  propagation faster. In addition, only relevant nodes can be traced by checking the inclusiveList.
                if temp_node.get_node_name() in self.__ast.get_inclusive_list():
                    #  once a user feeds an answer to the engine, the engine will propagate the entire NodeSet or
                    #  Assessment base on the answer
                    #  during the back-propagation, the engine checks if current node;
                    #  1. has been determined;
                    #  2. has any child nodes;
                    #  3. can be determined with given facts in the workingMemory.
                    #
                    #  once the current checking node meets the condition then add it to the summaryList for
                    #  summary view.
                    if temp_node.get_node_name() not in self.__ast.get_working_memory().keys() \
                            and self.has_children(temp_node.get_node_id()) \
                            and self.can_determine(temp_node, line_type):
                        if LineType.EXPR_CONCLUSION != line_type:
                            # add currentRule into SummeryList as the rule determined
                            self.__ast.add_item_to_summary_list(temp_node.get_node_name())

    def add_parent_into_inclusive_list(self, child_node: Node):
        node_in_dependency_list: list = self.__nodeSet.get_dependency_matrix().get_from_parent_dependency_list(
            child_node.get_node_id)
        # if rule has parents
        if len(node_in_dependency_list) > 0:
            for item in node_in_dependency_list:
                parent_node: Node = self.__nodeSet.get_node_dictionary()[self.__nodeSet.get_node_id_dictionary()[item]]
                if parent_node.get_node_name() not in self.__ast.get_inclusive_list():
                    self.__ast.get_inclusive_list().append(parent_node.get_node_name())

    def has_all_mandatory_child_answered(self, node_id: int) -> bool:
        mandatory_child_dependency_list: list \
            = self.__nodeSet.get_dependency_matrix().get_mandatory_to_child_dependency_list(node_id)
        all_mandatory_child_answered = False
        if len(mandatory_child_dependency_list) > 0:
            all_mandatory_child_answered = \
                all(self.__nodeSet.get_node_id_dictionary()[child_id] in self.__ast.get_working_memory().keys() \
                    and self.has_all_mandatory_child_answered(child_id)
                    for child_id in mandatory_child_dependency_list)
        elif len(mandatory_child_dependency_list) == 0:
            all_mandatory_child_answered = True

        return all_mandatory_child_answered

    def can_determine(self, target_node: Node, line_type: LineType) -> bool:
        can_be_determined = False
        # Any type of node/line can have either 'OR' or 'AND' type of child nodes
        #
        # -----ValueConclusion Type
        #  there will be two cases for this type
        #     V.1 the format of node is 'A -statement' so that 'TRUE' or "FALSE' value outcome case
        #    	   V.1.1 if it has 'OR' child nodes
        #    			 V.1.1.1 TRUE case
        #     					 if there is any of child node is 'true'
        #       			     then trim off 'UNDETERMINED' child nodes, which are not in 'workingMemory', other
        #       					    than 'MANDATORY' child nodes
        #    			 V.1.1.2 FALSE case
        #     					 if its all 'OR' child nodes are determined and all of them are 'false'
        #     	   V.1.2 if it has 'AND' child nodes
        #       		 V.1.2.1 TRUE case
        #      				 if its all 'AND' child nodes are determined and all of them are 'true'
        #       		 V.1.2.2 FALSE case
        #       				 if its all 'AND' child nodes are determined and all of them are 'false'
        #                     	 , and there is no need to trim off 'UNDETERMINED' child nodes other than 'MANDATORY'
        #                     	 child nodes because since 'virtual node' is introduced, any parent nodes won't have
        #                     	 'OR' and 'AND' dependency at the same time
        #
        #          V.1.3 other than above scenario it can't be determined in 'V.1' case
        #
        #     V.2 a case of that the value in the node text can be used as a value of its node's variable
        #           (e.g. A IS B, B can be used as a value for variable, 'A' in this case if all its child nodes or
        #            one of its child node is true)
        #   	   V.2.1 if it has 'OR' child nodes
        #    			 V.2.1.1 the value CAN BE USED case
        #    					 if its any of child node is 'true'
        #    					 then trim off 'UNDETERMINED' child nodes, which are not in 'workingMemory', other
        #    		    			than 'MANDATORY' child nodes
        #     			 V.2.1.2 the value CANNOT BE USED case
        #     					 if its all 'OR' child nodes are determined and all of them are 'false'
        #     	   V.2.2 if it has 'AND' child nodes
        #     			 V.2.2.1 the value CAN BE USED case
        #     					 if its all 'AND' child nodes are determined and all of them are 'true'
        #     			 V.2.2.2 the value CANNOT BE USED case
        #     					 if its all 'AND' child nodes are determined and all of them are 'false'
        #                      	 , and there is no need to trim off 'UNDETERMINED' child nodes other than
        #                      	 'MANDATORY' child nodes because since 'virtual node' is introduced,
        #                      	 any parent nodes won't have 'OR' and 'AND' dependency at the same time
        #
        #          V.2.3 other than above scenario it can't be determined in 'V.2' case
        #
        #
        #  Note: the reason why only ResultType and ExpressionType are evaluated with selfEvaluation() is as follows;
        #        1. ComparisonType is only evaluated by comparing a value of rule's variable in workingMemory with
        #           the value in the node
        #        2. ExpressionType is only evaluated by retrieving a value(s) of needed child node(s)
        #        3. ValueConclusionType is evaluated under same combination of various condition, and trimming
        #           dependency is involved.
        or_to_child_dependencies: list = self.__nodeSet.get_dependency_matrix() \
            .get_or_to_child_dependency_list(target_node.get_node_id())
        and_to_child_dependencies = self.__nodeSet.get_dependency_matrix() \
            .get_and_to_child_dependency_list(target_node.get_node_id())

        if LineType.VALUE_CONCLUSION == line_type:
            if "IS IN LIST" in target_node.get_node_name() \
                    and target_node.get_variable_name() in self.__ast.get_working_memory().keys() \
                    and str(target_node.get_fact_value().get_value()) in self.__ast.get_working_memory().keys():
                self.__ast.set_fact(target_node.get_node_name(),
                                    target_node.self_evaluate(self.__ast.get_working_memory()))
                can_be_determined = True
            else:
                is_plain_statement_format: bool = target_node.get_is_plain_statement()
                node_fact_value_in_string = str(target_node.get_fact_value().get_value())

                # is_any_or_dependency_true() method contains trimming off method to cut off any 'UNDETERMINED' state
                # 'OR' child nodes.

                # rule has only 'OR' child rules
                if len(and_to_child_dependencies) == 0 \
                        and len(or_to_child_dependencies) > 0:

                    # TRUE case
                    if self.is_any_or_dependency_true(target_node, or_to_child_dependencies):
                        node_id = target_node.get_node_id()
                        if self.__nodeSet.get_dependency_matrix().has_mandatory_child_node(node_id) \
                                and not self.has_all_mandatory_child_answered(node_id):
                            return can_be_determined
                        can_be_determined = True
                        self.__handle_value_conclusion_line_true_case(target_node, is_plain_statement_format,
                                                                      node_fact_value_in_string)

                    # FALSE case
                    elif self.is_all_relevant_child_dependency_determined(target_node, or_to_child_dependencies) \
                            and not self.is_any_or_dependency_true(target_node, or_to_child_dependencies):
                        can_be_determined = True
                        self.__handle_value_conclusion_line_false_case(target_node, is_plain_statement_format,
                                                                       node_fact_value_in_string)

                #  node has only 'AND' child nodes
                elif len(and_to_child_dependencies) > 0 \
                        and len(or_to_child_dependencies) == 0:

                    # TRUE case
                    if self.is_all_relevant_child_dependency_determined(target_node, and_to_child_dependencies) \
                            and self.is_all_and_dependency_true(target_node, and_to_child_dependencies):
                        can_be_determined = True
                        self.__handle_value_conclusion_line_true_case(target_node, is_plain_statement_format,
                                                                      node_fact_value_in_string)


                    #  'is_any_and_dependency_false()' contains a trimming off dependency method
                    #  due to the fact that all undetermined 'AND' child nodes need to be trimmed off when any 'AND' node is evaluated as 'NO'
                    # , which does not influence on determining a parent rule's evaluation.

                    # FALSE case
                    elif self.is_any_and_dependency_false(target_node, and_to_child_dependencies):
                        node_id = target_node.get_node_id()
                        if self.__nodeSet.get_dependency_matrix().has_mandatory_child_node(node_id) \
                                and not self.has_all_mandatory_child_answered(node_id):
                            return can_be_determined

                        can_be_determined = True
                        self.__handle_value_conclusion_line_false_case(target_node, is_plain_statement_format,
                                                                       node_fact_value_in_string)
        elif LineType.COMPARISON == line_type:
            # rule has only 'OR' child rules
            if len(and_to_child_dependencies) == 0 \
                    and len(or_to_child_dependencies) > 0:
                # the node might have a 'MANDATORY OR' child nodes so that the mandatory child nodes need being handled
                if self.__has_any_or_child_evaluated(target_node.get_node_id(), or_to_child_dependencies):
                    if not self.has_all_mandatory_child_answered(target_node.get_node_id()):
                        return False

                    can_be_determined = True
                    self.__ast.set_fact(target_node.get_node_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())
            # node has only 'AND' child nodes
            elif len(and_to_child_dependencies) > 0 \
                    and len(or_to_child_dependencies) == 0:
                # in this case they are all 'MANDATORY' child nodes
                if self.__has_all_and_child_evaluated(and_to_child_dependencies):
                    if not self.has_all_mandatory_child_answered(target_node.get_node_id()):
                        return False
                    can_be_determined = True
                    self.__ast.set_fact(target_node.get_node_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())

        elif LineType.EXPR_CONCLUSION == line_type:
            # rule has only 'OR' child rules
            if len(and_to_child_dependencies) == 0 \
                    and not len(or_to_child_dependencies) == 0:
                # the node might have a 'MANDATORY OR' child nodes so that the mandatory child nodes need
                # being handled
                if self.__has_any_or_child_evaluated(target_node.get_node_id(), or_to_child_dependencies):
                    if not self.has_all_mandatory_child_answered(target_node.get_node_id()):
                        return False
                    can_be_determined = True
                    self.__ast.set_fact(target_node.get_variable_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))

                    # inserting same value for node's name is for the purpose of display equation
                    self.__ast.set_fact(target_node.get_node_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))
                    self.__ast.add_item_to_summary_list(target_node.get_variable_name())

                    # inserting node's name is to find its evaluated value from the workingMemory with its name
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())

            # node has only 'AND' child nodes
            elif len(and_to_child_dependencies) != 0 \
                    and len(or_to_child_dependencies) == 0:
                # in this case they are all 'MANDATORY' child nodes
                if self.__has_all_and_child_evaluated(and_to_child_dependencies):
                    if not self.has_all_mandatory_child_answered(target_node.get_node_id()):
                        return False

                    can_be_determined = True
                    self.__ast.set_fact(target_node.get_variable_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))

                    # inserting same value for node's name is for the purpose of display equation
                    self.__ast.set_fact(target_node.get_node_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))

                    self.__ast.add_item_to_summary_list(target_node.get_variable_name())

                    # inserting node's name is to find its evaluated value from the workingMemory with its name
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())

            else:
                if self.__has_any_or_child_evaluated(target_node.get_node_id(), or_to_child_dependencies) \
                        and self.__has_all_and_child_evaluated(and_to_child_dependencies):
                    if not self.has_all_mandatory_child_answered(target_node.get_node_id()):
                        return False
                    can_be_determined = True
                    self.__ast.set_fact(target_node.get_variable_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))

                    # inserting same value for node's name is for the purpose of display equation
                    self.__ast.set_fact(target_node.get_node_name(),
                                        target_node.self_evaluate(self.__ast.get_working_memory()))

                    self.__ast.add_item_to_summary_list(target_node.get_variable_name())

                    #  inserting node's name is to find its evaluated value from the workingMemory with its name
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())
        elif LineType.ITERATE == line_type:
            if target_node.can_be_self_evaluated(self.__ast.get_working_memory()):
                self.__ast.set_fact(target_node.get_node_name(),
                                    target_node.self_evaluate(self.__ast.get_working_memory()))
                self.__ast.add_item_to_summary_list(target_node.get_variable_name())

        return can_be_determined

    def __has_any_or_child_evaluated(self, parent_node_id: int, or_to_child_dependencies: list):
        any_or_child_evaluated: bool = \
            any((self.__nodeSet.get_node_by_node_id(child_id) in self.__ast.get_working_memory().keys()
                 and self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_node_id, child_id) != -1
                 and self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_node_id, child_id)
                 & DependencyType.get_mandatory() == DependencyType.get_mandatory())
                or self.__nodeSet.get_node_by_node_id(
                child_id).get_variable_name() in self.__ast.get_working_memory().keys()
                for child_id in or_to_child_dependencies)

        return any_or_child_evaluated

    def __has_all_and_child_evaluated(self, and_to_child_dependencies: list):
        all_and_child_evaluated: bool = \
            all(self.__nodeSet.get_node_by_node_id(child_id).get_variable_name()
                in self.__ast.get_working_memory().keys()
                for child_id in and_to_child_dependencies)

        return all_and_child_evaluated

    def __handle_value_conclusion_line_true_case(self, value_node: Node, is_plain_statement_format: bool,
                                                 node_fact_value_in_string: str):
        self.__ast.set_fact(value_node.get_node_name(), FactValue(True))
        if not is_plain_statement_format:
            if node_fact_value_in_string in self.__ast.get_working_memory().keys():
                self.__ast.set_fact(value_node.get_variable_name(),
                                    self.__ast.get_working_memory()[node_fact_value_in_string])
            else:
                self.__ast.set_fact(value_node.get_variable_name(), value_node.get_fact_value(), value_node)

            self.__ast.add_item_to_summary_list(value_node.get_variable_name())

    def __handle_value_conclusion_line_false_case(self, value_node: Node, is_plain_statement_format: bool,
                                                  node_fact_value_in_string: str):
        self.__ast.set_fact(value_node.get_node_name(), FactValue(False))
        if not is_plain_statement_format:
            if node_fact_value_in_string in self.__ast.get_working_memory().keys():
                fact_value_from_working_memory: FactValue = self.__ast.get_working_memory()[node_fact_value_in_string]
                fact_key = "NOT " + str(self.__ast.get_working_memory()[node_fact_value_in_string])
                if fact_value_from_working_memory.get_value_type() is FactValueType.LIST:
                    fact_value_from_working_memory.get_value() \
                        .append(FactValue(fact_key))
                    self.__ast.set_fact(value_node.get_variable_name(), fact_value_from_working_memory)
                else:
                    fact_value_list = list()
                    fact_value_list \
                        .append(self.__ast.get_working_memory()[node_fact_value_in_string])
                    fact_value_list \
                        .append(FactValue(fact_key))
                    self.__ast.set_fact(value_node.get_variable_name(), FactValue(fact_value_list, FactValueType.LIST))
            else:
                self.__ast.set_fact(value_node.get_variable_name(),
                                    FactValue("NOT " + node_fact_value_in_string),
                                    value_node)
            self.__ast.add_item_to_summary_list(value_node.get_variable_name())

    def get_default_goal_rule_question(self) -> str:
        return self.__nodeSet.get_default_goal_node().get_node_name()

    def get_assessment_goal_rule_question(self, ass: Assessment) -> str:
        return ass.get_goal_node().get_node_name()

    def get_default_goal_rule_answer(self) -> FactValue:
        return self.__ast.get_working_memory()[self.__nodeSet.get_default_goal_node().get_variable_name()]

    def get_assessment_goal_rule_answer(self, ass: Assessment) -> FactValue:
        return self.__ast.get_working_memory()[ass.get_goal_node().get_variable_name()]

    def has_children(self, node_id: int) -> bool:
        """
        Returns boolean value that can determine whether the given rule has any children
        this method is used within the process of backward chaining.
        """
        it_has_children = False
        if len(self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list(node_id)) != 0:
            it_has_children = True
            matrix = self.__nodeSet.get_dependency_matrix()
            for item in self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list(node_id):
                node_name = self.__nodeSet.get_node_by_node_id(item)
                self.add_child_rule_into_inclusive_list(node_name)

        return it_has_children

    def add_child_rule_into_inclusive_list(self, parent_node: Node):
        """ the method adds all children rules of relevant parent rule into the 'inclusive_list' if they are not in the list. """
        children_list_of_node: list = \
            self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list(parent_node.get_node_id())
        for item in children_list_of_node:
            child_node_name = \
                self.__nodeSet.get_node_dictionary().get(self.__nodeSet.get_node_id_dictionary().get(item)) \
                    .get_node_name()
            if child_node_name not in self.__ast.get_inclusive_list() \
                    and child_node_name not in self.__ast.get_exclusive_list():
                self.__ast.get_inclusive_list().append(child_node_name)

    def is_any_or_dependency_true(self, parent_node: Node, or_child_dependencies: list) -> bool:
        is_any_or_dependency_true = False
        if len(or_child_dependencies) != 0:
            true_or_child_list = list()
            for child_id in or_child_dependencies:
                if self.__ast.is_in_inclusive_list(self.__nodeSet.get_node_id_dictionary()[child_id]) \
                        and self.__nodeSet.get_node_id_dictionary()[child_id] in self.__ast.get_working_memory().keys():
                    dependency_type = self.__nodeSet.get_dependency_matrix().get_dependency_type(
                        parent_node.get_node_id(), child_id)
                    if dependency_type != - 1 \
                            and dependency_type & DependencyType.get_known() == DependencyType.get_known() \
                            and dependency_type & DependencyType.get_not() != DependencyType.get_not():
                        true_or_child_list.append(child_id)
                        if not "KNOWN " + self.__nodeSet.get_node_id_dictionary()[child_id] \
                               in self.__ast.get_working_memory().keys():
                            fact_key: str = "KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[child_id])
                            self.__ast.set_fact(fact_key, FactValue(True))
                            self.__ast.add_item_to_summary_list(fact_key)
                    elif self.__ast.get_working_memory()[
                        self.__nodeSet.get_node_id_dictionary()[child_id]].get_value() is True \
                            and dependency_type != -1 \
                            and dependency_type & DependencyType.get_not() != DependencyType.get_not():
                        true_or_child_list.append(child_id)
                    elif self.__ast.get_working_memory()[
                        self.__nodeSet.get_node_id_dictionary()[child_id]].get_value() is False \
                            and dependency_type != -1 \
                            and dependency_type & DependencyType.get_not() == DependencyType.get_not():
                        true_or_child_list.append(child_id)
                        fact_key: str = "NOT " + str(self.__nodeSet.get_node_id_dictionary()[child_id])

                        if fact_key not in self.__ast.get_working_memory().keys():
                            self.__ast.set_fact(fact_key, FactValue(True))
                            self.__ast.add_item_to_summary_list(fact_key)
            if not len(true_or_child_list) == 0:
                is_any_or_dependency_true = True
                for child_id in or_child_dependencies:
                    for n_value in true_or_child_list:
                        if child_id != n_value:
                            self.trim_dependency(parent_node, child_id)

        return is_any_or_dependency_true

    def trim_dependency(self, parent_node: Node, child_node_id: int):
        parent_node_id: int = parent_node.get_node_id()
        dp_type: int = \
            self.__nodeSet.get_dependency_matrix().get_dependency_two_dimension_list()[parent_node_id][child_node_id]
        mandatory_dependency_type: int = DependencyType.get_mandatory()
        parent_dependency_list: list = \
            self.__nodeSet.get_dependency_matrix().get_from_parent_dependency_list(child_node_id)

        if ( \
                # the child has more than one parent
                len(parent_dependency_list) > 1 \
                # all parents have been determined
                and all(self.__nodeSet.get_node_id_dictionary()[parent] in self.__ast.get_working_memory().keys()
                        for parent in parent_dependency_list) \
                # the child has no Mandatory dependency parents
                and not any(self.__nodeSet.get_dependency_matrix()
                                    .get_dependency_two_dimension_list()[parent][child_node_id] != -1 \
                            and self.__nodeSet.get_dependency_matrix()
                                    .get_dependency_two_dimension_list()[parent][child_node_id]
                            & mandatory_dependency_type == mandatory_dependency_type
                            for parent in parent_dependency_list)) \
                or \
                (
                        # the child has only one parent
                        len(parent_dependency_list) == 1 \
                        # the dependency is not 'MANDATORY'
                        and dp_type & mandatory_dependency_type != mandatory_dependency_type):
            child_node_name = self.__nodeSet.get_node_id_dictionary()[child_node_id]
            if child_node_name in self.__ast.get_inclusive_list():
                self.__ast.get_inclusive_list().remove(child_node_name)

            if child_node_name not in self.__ast.get_exclusive_list():
                self.__ast.get_exclusive_list().append(child_node_name)

            child_dependency_list_of_child_node: list = \
                self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list(child_node_id)

            if len(child_dependency_list_of_child_node) > 0:
                for item in child_dependency_list_of_child_node:
                    self.trim_dependency(self.__nodeSet.get_node_by_node_id(child_node_id), item)

    def is_any_and_dependency_false(self, parent_node: Node, and_child_dependencies: list) -> bool:
        any_and_dependency_false = False

        if len(and_child_dependencies) > 0:
            false_and_list = list()
            for item in and_child_dependencies:
                dependency_type = self.__nodeSet.get_dependency_matrix() \
                    .get_dependency_type(parent_node.get_node_id(), item)
                if self.__nodeSet.get_node_id_dictionary()[item] in self.__ast.get_working_memory().keys():
                    if self.__ast.get_working_memory()[self.__nodeSet.get_node_id_dictionary()[item]] \
                            .get_value() is False \
                            and dependency_type != -1 \
                            and dependency_type & DependencyType.get_not() != DependencyType.get_not() \
                            and dependency_type & DependencyType.get_known() != DependencyType.get_known():
                        false_and_list.append(item)
                    elif self.__ast.get_working_memory()[
                        self.__nodeSet.get_node_id_dictionary()[item]].get_value() is True \
                            and dependency_type != -1 \
                            and dependency_type & DependencyType.get_not() == DependencyType.get_not() \
                            and dependency_type & DependencyType.get_known() != DependencyType.get_known():
                        fact_key: str = "NOT " + str(self.__nodeSet.get_node_id_dictionary()[item])
                        if fact_key not in self.__ast.get_working_memory().keys():
                            self.__ast.set_fact(fact_key, FactValue(False))
                            self.__ast.add_item_to_summary_list(fact_key)
                        false_and_list.append(item)
                    elif dependency_type != -1 \
                            and dependency_type & (DependencyType.get_not() | DependencyType.get_known()) \
                            == (DependencyType.get_not() | DependencyType.get_known()):

                        fact_key: str = "NOT KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[item])

                        if fact_key not in self.__ast.get_working_memory().keys():
                            self.__ast.set_fact(fact_key, FactValue(False))
                            self.__ast.add_item_to_summary_list(fact_key)
                        false_and_list.append(item)

            if len(false_and_list) > 0:
                any_and_dependency_false = True
                for index in and_child_dependencies:
                    for and_index in false_and_list:
                        if index != and_index:
                            self.trim_dependency(parent_node, index)
            elif len(and_child_dependencies) == 0:
                any_and_dependency_false = True

        return any_and_dependency_false

    def is_all_and_dependency_true(self, parent_node: Node, and_child_dependencies: list) -> bool:
        determined_true_and_child_dependencies = list()
        for item in and_child_dependencies:
            if self.__ast.is_in_inclusive_list(self.__nodeSet.get_node_id_dictionary()[item]) \
                    and self.__nodeSet.get_node_id_dictionary()[item] in self.__ast.get_working_memory().keys():
                dependency_type = \
                    self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_node.get_node_id(), item)
                if self.__ast.get_working_memory()[
                    self.__nodeSet.get_node_id_dictionary()[item]].get_value() is True \
                        and dependency_type!= -1 \
                        and dependency_type & DependencyType.get_not() != DependencyType.get_not():
                    determined_true_and_child_dependencies.append(item)
                elif dependency_type != -1 \
                        and dependency_type & DependencyType.get_known() == DependencyType.get_known() \
                        and dependency_type & DependencyType.get_not() != DependencyType.get_not():

                    fact_key = "KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[item])

                    if fact_key not in self.__ast.get_working_memory():
                        self.__ast.set_fact(fact_key, FactValue(False))
                        self.__ast.add_item_to_summary_list(fact_key)

                    determined_true_and_child_dependencies.append(item)

                elif self.__ast.get_working_memory()[
                    self.__nodeSet.get_node_id_dictionary()[item]].get_value() is False \
                        and dependency_type != -1 \
                        and (dependency_type & DependencyType.get_not() == DependencyType.get_not()) \
                        and (dependency_type & DependencyType.get_known() != DependencyType.get_known()):
                    fact_key = "NOT " + str(self.__nodeSet.get_node_id_dictionary()[item])
                    if fact_key not in self.__ast.get_working_memory():
                        self.__ast.set_fact(fact_key, FactValue(False))
                        self.__ast.add_item_to_summary_list(fact_key)
                    determined_true_and_child_dependencies.append(item)

        if 0 < len(and_child_dependencies) == len(determined_true_and_child_dependencies):
            return True

        return False

    def is_all_relevant_child_dependency_determined(self, parent_node: Node, all_child_dependencies: list) -> bool:
        determined_and_out_dependencies = list()

        for child_dependency in all_child_dependencies:
            dependency_type = \
                self.__nodeSet.get_dependency_matrix().get_dependency_type(parent_node.get_node_id(),
                                                                           child_dependency)
            node_name = self.__nodeSet.get_node_id_dictionary()[child_dependency]
            if node_name not in self.__ast.get_working_memory().keys() \
                    and dependency_type & DependencyType.get_mandatory() == DependencyType.get_mandatory():
                self.__ast.add_item_to_mandatory_list(node_name)
            if node_name in self.__ast.get_working_memory().keys():
                fact_key = ""

                if dependency_type != -1 \
                        and dependency_type & (DependencyType.get_not() | DependencyType.get_known()) == (
                        DependencyType.get_not() | DependencyType.get_known()) \
                        and "NOT KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[
                                                   child_dependency]) not in self.__ast.get_working_memory().keys():
                    fact_key = "NOT KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[child_dependency])
                    self.__ast.set_fact(fact_key, FactValue(False))
                elif self.__ast.get_working_memory()[
                    self.__nodeSet.get_node_id_dictionary()[child_dependency]].get_value() is False \
                        and dependency_type != -1 \
                        and dependency_type & DependencyType.get_not() == DependencyType.get_not() \
                        and "NOT " + str(self.__nodeSet.get_node_id_dictionary()[
                                             child_dependency]) not in self.__ast.get_working_memory().keys():
                    fact_key = "NOT " + str(self.__nodeSet.get_node_id_dictionary()[child_dependency])
                    self.__ast.set_fact(fact_key, FactValue(True))
                elif dependency_type != -1 \
                        and dependency_type & DependencyType.get_known() == DependencyType.get_known() \
                        and "KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[
                                               child_dependency]) not in self.__ast.get_working_memory().keys():
                    fact_key = "KNOWN " + str(self.__nodeSet.get_node_id_dictionary()[child_dependency])
                    self.__ast.set_fact(fact_key, FactValue(True))
                elif self.__ast.get_working_memory()[
                    self.__nodeSet.get_node_id_dictionary()[child_dependency]].get_value() is True \
                        and dependency_type != -1 \
                        and dependency_type & DependencyType.get_not() == DependencyType.get_not() \
                        and "NOT " + str(self.__nodeSet.get_node_id_dictionary()[
                                             child_dependency]) not in self.__ast.get_working_memory().keys():
                    fact_key = "NOT " + str(self.__nodeSet.get_node_id_dictionary()[child_dependency])
                    self.__ast.set_fact(fact_key, FactValue(False))

                if len(fact_key) > 0:
                    self.__ast.add_item_to_summary_list(fact_key)

                if self.__ast.is_in_inclusive_list(self.__nodeSet.get_node_id_dictionary()[child_dependency]) \
                        and self.__nodeSet.get_node_id_dictionary()[child_dependency] \
                        in self.__ast.get_working_memory().keys():
                    determined_and_out_dependencies.append(child_dependency)

        if len(all_child_dependencies) > 0 and len(determined_and_out_dependencies) == len(all_child_dependencies):
            return True

        return False

    def generate_sorted_summary_list(self) -> list:
        sorted_summary_list: list = []
        for sorted_node in self.__nodeSet.get_sorted_node_list():
            if sorted_node.get_node_name() in self.__ast.get_summary_list():
                sorted_summary_list.append(sorted_node.get_node_name())

            if "NOT " + str(sorted_node.get_node_name()) in self.__ast.get_summary_list():
                sorted_summary_list.append("NOT " + str(sorted_node.get_node_name()))

            if "KNOWN " + str(sorted_node.get_node_name()) in self.__ast.get_summary_list():
                sorted_summary_list.append("KNOWN " + str(sorted_node.get_node_name()))

            if "NOT KNOWN " + str(sorted_node.get_node_name()) in self.__ast.get_summary_list():
                sorted_summary_list.append("NOT KNOWN " + str(sorted_node.get_node_name()))

        for node_name in self.__ast.get_summary_list():
            if node_name not in sorted_summary_list:
                sorted_summary_list.insert(1, node_name)

        return sorted_summary_list
    
    def reset_working_memory_and_inclusive_list(self):
        """
        this method is to reset 'workingMemory' list and 'inclusiveList'
        use of this method will depend on a user. if a user wants to continue to assessment on a same case
        with same conditions then don't need to reset 'workingMemory' and 'inclusiveList' otherwise reset them.
        """
        if len(self.__ast.get_inclusive_list()) > 0:
            self.__ast.get_inclusive_list().clear()

        if len(self.__ast.get_working_memory()) > 0:
            self.__ast.get_working_memory().clear()

    def generate_assessment_summary(self) -> list:
        """ this is to generate Assessment Summary """
        temp_summary_list: list = []
        for sum_item in self.get_assessment_state().get_summary_list():
            to_be_json_obj = dict()
            to_be_json_obj["nodeText"] = sum_item
            to_be_json_obj["nodeValue"] = str(self.get_assessment_state().get_working_memory()[sum_item].get_value())
            temp_summary_list.append(json.dump(to_be_json_obj))

        return temp_summary_list

    def edit_answer(self, question: str, target_goal_node_name: str) -> None:
        temp_summary_list = self.get_assessment_state().get_summary_list()
        index_of_question_to_be_edited = temp_summary_list.index(question)
        temp_working_memory = self.get_assessment_state().get_working_memory()

        # following two lines are to reset 'exclusiveList' and 'inclusiveList' which are for tracking all relevant
        # branches by cutting dependencies
        self.get_assessment_state().set_exclusive_list(list())
        self.get_assessment_state().set_inclusive_list(list())

        # need to remove values of 'question' key from workingMemory because it needs editing
        temp_working_memory.pop(question)

        # the reason of doing following lines is to re-establish 'inclusiveList' and 'exclusiveList'
        # which manage cutting all irrelevant branches within the rule tree based on fed answers.
        # all branches up to the point of 'to-be-edited-question' need re-establishment and other branches after the 'question'
        # don't need to be re-established because those may not be irrelevant to effect decision at the end
        # unless they are appeared during the questionnaire after all re-establishment.
        for index in range(0, len(temp_summary_list)):
            if index < index_of_question_to_be_edited:
                node = self.get_next_question(self.get_assessment_of_rule(target_goal_node_name))
                if self.__ass.get_node_to_be_asked().get_line_type() == LineType.ITERATE:
                    self.__ass.set_aux_node_to_be_asked(node)

                questionnaire_from_node = self.get_questions_from_node_to_be_asked(node)
                for question_item in questionnaire_from_node:
                    if question_item in temp_summary_list:
                        fact_value: FactValue = temp_working_memory[question_item]
                        self.feed_answer_to_node(node, question_item,
                                                 str(fact_value.get_value()),
                                                 fact_value.get_value_type(), self.__ass)

    def find_condition(self, keyword: str) -> list:
        """ this is to find a condition in a rule set with a given keyword string, that may contain multiple keywords """

        initial_size = len(self.__nodeSet.get_sorted_node_list())
        condition_list: list = []
        question_list: list = []

        for sorted_node in self.__nodeSet.get_sorted_node_list():
            if len(self.__nodeSet.get_dependency_matrix().get_to_child_dependency_list(sorted_node.get_node_id())) > 0:
                question_list.append(sorted_node.get_node_name())

        keyword_array = keyword.split("\\W+")  # split the keyword by none word character including whitespace.
        keyword_array_length = len(keyword_array)

        for rule_name in question_list:
            number_of_match = 0

            for index in range(0, keyword_array_length):
                if keyword_array[index] in rule_name:
                    number_of_match = number_of_match + 1

                if number_of_match == keyword_array_length:
                    condition_list.append(rule_name)

        return condition_list

        
        
