import re
from abc import ABC
from datetime import *
from project.constants import DependencyTypeStringMatcher
from project.nodes import DependencyMatrix
from project.nodes.iterate_line import IterateLine
from project.nodes.node_set import NodeSet
from project.nodes import LineType
from project.rule_parser import IScanFeeder
from project.tokens import Tokenizer
from project.constants import LineMatcherConstant
from project.nodes import MetadataLine
from project.nodes import ValueConclusionLine
from project.nodes import ExprConclusionLine
from project.nodes import ComparisonLine
from project.fact_values import FactValue
from project.fact_values import FactValueType
from project.nodes import DependencyType
from project.nodes import Dependency
from project.nodes import MetaType
from project.nodes.node import Node
from project.loggers.logger import Logger

logging: Logger = Logger.get_logger(__name__)


class RuleSetParser(IScanFeeder, ABC):
    # patterns are as follows
    # U : upper case
    # L : lower case
    # M : mixed case
    # No: number
    # Da: date
    # Ha: hash
    # Url: url
    # Id: GUID
    # C : CALC (this is a keyword)
    # De: decimal
    # Q : quotation mark
    #
    # meta_pattern_matcher = r"(^U)([MLU]*)([(No)(Da)ML(De)(Ha)(U(rl)?)(Id)]*$)"
    # value_conclusion_matcher = r"(^[LM]+)(U)?([MLQ(No)(Da)(De)(Ha)(Url)(Id)]*$)(?!C)"
    # expression_conclusion_matcher = r"(^[LM(Da)]+)(U)(C)"
    # comparison_matcher = r"(^[MLU(Da)]+)(O)([MLUQ(No)(Da)(De)(Ha)(Url)(Id)]*$)"
    # iterate_matcher = r"(^[MLU(No)(Da)]+)(I)([MLU]+$)"
    # warning_matcher = r"WARNING"

    # __match_types = LineType.get_all_values()
    # __node_set = NodeSet()
    # __dependency_list = []

    def __init__(self):
        self.__node_set = NodeSet()
        self.__dependency_list = []
        self.__match_types = LineType.get_all_values()
        logging.info("RuleSetParser is initiated")

    def create(self):
        self.__match_types = LineType.get_all_values()
        self.__node_set = NodeSet()
        self.__dependency_list = []
    def handle_parent(self, parent_text, line_number) -> None:
        node_data = None

        if parent_text in self.__node_set.get_node_dictionary().keys():
            node_data = self.__node_set.get_node_dictionary()[parent_text]

        if node_data is None:
            tokens = Tokenizer.get_tokens(parent_text)
            line_match_patterns = [LineMatcherConstant.META_PATTERN_MATCHER.value,
                                   LineMatcherConstant.VALUE_CONCLUSION_MATCHER.value,
                                   LineMatcherConstant.EXPRESSION_CONCLUSION_MATCHER.value,
                                   LineMatcherConstant.WARNING_MATCHER.value]

            for i in range(len(line_match_patterns)):
                pattern = re.compile(line_match_patterns[i])
                match = pattern.match(tokens.get_tokens_string())
                if match:
                    if i == 3:  # warning matcher
                        self.handle_warning(parent_text)
                    elif i == 0:  # meta matcher
                        node_data = MetadataLine(parent_text, tokens)
                        if node_data.get_fact_value().get_value() == 'WARNING':
                            self.handle_warning(parent_text)
                    elif i == 1:  # value conclusion matcher
                        node_data = ValueConclusionLine(parent_text, tokens)
                        # if (len(match.groups()) == 2 and match.group(2) is not None) \
                        if match.group(2) is not None \
                                or (
                                tokens.get_tokens_string() == 'L' or tokens.get_tokens_string() == 'LM'
                                or tokens.get_tokens_string() == 'ML' or tokens.get_tokens_string() == 'M'):
                            variable_name = node_data.get_variable_name()
                            temp_node = node_data

                            # following lines are to look for any nodes having a its nodeName with any operators
                            # due to the reason that the nodes could be used to define a nodes previously used
                            # as a child nodes for other nodes

                            possible_parent_node_key_list = \
                                list(
                                    filter(lambda key: \
                                           re.match(r"(.+)(\s[<>=]+\s?)(" + variable_name + ")", key) \
                                           or re.match(r"(" + variable_name + r")(\s*[<>=]+.*)+", key) \
                                           or re.match(r"(" + variable_name + r")(?!\s*IS)+", key) \
                                           or re.match(r"(" + variable_name + ")(.*(IS IN LIST).*)+",
                                       key)
                                   , self.__node_set.get_node_dictionary().keys()))
                            if len(possible_parent_node_key_list) > 0:
                                for item in possible_parent_node_key_list:
                                    # Dependency Type: OR
                                    self.__dependency_list.append(
                                        Dependency(self.__node_set.get_node_dictionary()[item], temp_node,
                                                   DependencyType.get_or()))

                            if node_data.get_fact_value().get_value() == 'WARNING':
                                self.handle_warning(parent_text)

                    elif i == 2:  # expr conclusion matcher
                        node_data = ExprConclusionLine(parent_text, tokens)
                        variable_name = node_data.get_variable_name()
                        temp_node = node_data

                        # following lines are to look for any nodes having a its nodeName with any operators
                        # due to the reason that the exprConclusion nodes could be used to define another nodes
                        # as a child nodes for other nodes if the variableName of exprConclusion nodes is mentioned
                        # somewhere else. However, it is excluding nodes having 'IS' keyword because if it has
                        # the keyword then it should have child nodes to define the nodes otherwise the entire rule set
                        # has NOT been written in correct way

                        possible_parent_node_key_list = \
                            list(
                                filter(lambda key: \
                                       re.match(r"(.+)(\s[<>=]+\s?)(" + variable_name + ")", key) \
                                       or re.match(r"(" + variable_name + r")(\s*[<>=]+.*)+", key) \
                                       or re.match(r"(" + variable_name + r")(?!\s*IS)+", key) \
                                       or re.match(r"(" + variable_name + ")(.*(IS IN LIST).*)+",
                                                   key)
                                   , self.__node_set.get_node_dictionary().keys()))
                        if len(possible_parent_node_key_list) > 0:
                            for item in possible_parent_node_key_list:
                                self.__dependency_list.append(
                                    Dependency(self.__node_set.get_node_dictionary()[item], temp_node,
                                               DependencyType.get_or()))  # Dependency Type: OR

                        if node_data.get_fact_value().get_value() == 'WARNING':
                            self.handle_warning(parent_text)

                    else:
                        self.handle_warning(parent_text)

                    node_data.set_node_line(line_number)

                    if node_data.get_line_type() == LineType.META:
                        if node_data.get_meta_type() == MetaType.INPUT:
                            self.__node_set.get_input_dictionary()[
                                node_data.get_variable_name()] = node_data.get_fact_value()
                        elif node_data.get_meta_type() == MetaType.FIXED:
                            self.__node_set.get_fact_dictionary()[
                                node_data.get_variable_name()] = node_data.get_fact_value()
                    else:
                        self.__node_set.get_node_dictionary()[node_data.get_node_name()] = node_data
                        self.__node_set.get_node_id_dictionary()[node_data.get_node_id()] = node_data.get_node_name()

                    break

    def handle_child(self, parent_text, child_text, first_key_words_group, line_number) -> None:

        # the reason for using '*' at the last group of pattern within comparison is that
        # the last group contains No, Da, De, Ha, Url, Id.
        # In order to track more than one character within the square bracket of last group '*'(Matches 0 or
        # more occurrences of the preceding expression) needs to be used.

        dependency_type = 0

        if re.match(r"(ITEM)(.*)", child_text):  # is 'ITEM' child line
            if not re.match(r"(.*)(AS LIST)", parent_text):
                self.handle_warning(child_text)
                return

            # is an indented item child
            child_text = child_text.replace("ITEM", "", 1).strip()
            meta_type: MetaType = None
            if re.match(r"^(INPUT)(.*)", parent_text):
                meta_type = MetaType.INPUT
            elif re.match(r"^(FIXED)(.*)", parent_text):
                meta_type = MetaType.FIXED
            self.handle_list_item(parent_text, child_text, meta_type)
        else:  # is 'A-statement', 'A IS B', 'A <= B', or 'A IS CALC (B * C)' child line
            if re.match(r"^(AND\s?)(.*)", first_key_words_group):
                # 8 - AND | 1 - KNOWN? 2 - NOT? 64 - MANDATORY? 32 - OPTIONALLY? 16 - POSSIBLY?
                dependency_type = self.handle_not_known_man_opt_pos(first_key_words_group,
                                                                    DependencyType.get_and())
            elif re.match(r"^(OR\s?)(.*)", first_key_words_group):
                # 4 - OR | 1 - KNOWN? 2 - NOT? 64 - MANDATORY? 32 - OPTIONALLY? 16 - POSSIBLY?
                dependency_type = self.handle_not_known_man_opt_pos(first_key_words_group,
                                                                    DependencyType.get_or())
            elif re.match(r"^(WANTS)", first_key_words_group):
                # 4 - OR
                dependency_type = self.handle_not_known_man_opt_pos(first_key_words_group,
                                                                    DependencyType.get_or())
            elif re.match(r"^(NEEDS)", first_key_words_group):
                # 8 - AND | 64 - MANDATORY
                dependency_type = DependencyType.get_mandatory() | DependencyType.get_and()

            # the keyword of 'AND' or 'OR' should be removed individually.
            # it should NOT be removed by using firstToken string in tokens.tokensList.get(0)
            # because firstToken string may have something else.
            # (e.g. string: 'AND NOT ALL Males' name should sound Male', then Token string will be 'UMLM',
            # and 'U' contains 'AND NOT ALL'. So if we used 'firstToken string' to remove 'AND' in this case
            # as 'string.replace(firstTokenString)', then it will remove 'AND NOT ALL' even we only need to remove 'AND'

            node_data = None
            if child_text in self.__node_set.get_node_dictionary().keys():
                node_data = self.__node_set.get_node_dictionary()[child_text]
            tokens = Tokenizer.get_tokens(child_text)

            if node_data is None:
                match_patterns = [LineMatcherConstant.VALUE_CONCLUSION_MATCHER.value,
                                  LineMatcherConstant.COMPARISON_MATCHER.value,
                                  LineMatcherConstant.ITERATE_MATCHER.value,
                                  LineMatcherConstant.EXPRESSION_CONCLUSION_MATCHER.value,
                                  LineMatcherConstant.WARNING_MATCHER.value]
                for pattern_index in range(len(match_patterns)):
                    pattern = match_patterns[pattern_index]
                    match = re.match(pattern, tokens.get_tokens_string())
                    if match:
                        if pattern_index == 4:  # warning matcher
                            self.handle_warning(child_text)
                        elif pattern_index == 0:  # value conclusion matcher
                            node_data = ValueConclusionLine(child_text, tokens)
                            temp_node = node_data
                            possible_child_node_key_list = \
                                list(filter(lambda key: re.match(
                                    r"^(" + temp_node.get_variable_name() + ")(\\s+(IS(?!(\\s+IN\\s+LIST))).*)*$", key),
                                            self.__node_set.get_node_dictionary().keys()))
                            if len(possible_child_node_key_list) > 0:
                                for item in possible_child_node_key_list:
                                    self.__dependency_list.append(
                                        Dependency(temp_node, self.__node_set.get_node_dictionary()[item],
                                                   DependencyType.get_or()))  # Dependency Type: OR
                            if node_data.get_fact_value().get_value() == "WARNING":
                                self.handle_warning(child_text)
                        elif pattern_index == 1:  # comparison matcher
                            node_data = ComparisonLine(child_text, tokens)
                            rhs_type = node_data.get_rhs().get_value_type()
                            rhs_string = node_data.get_rhs().get_value()
                            lhs_string = node_data.get_lhs()
                            temp_node = node_data
                            if rhs_type == FactValueType.STRING:
                                possible_child_node_key_list = list(filter(
                                    lambda key: re.match(r"^(" + lhs_string + r")(\s+(IS(?!(\s+IN\s+LIST))).*)*$", key)
                                                or re.match(r"^(" + rhs_string + r")(\s+(IS(?!(\s+IN\s+LIST))).*)*$",
                                                            key),
                                    self.__node_set.get_node_dictionary().keys()))
                            else:
                                possible_child_node_key_list = list(filter(
                                    lambda key: re.match(r"^(" + lhs_string + r")(\s+(IS(?!(\s+IN\s+LIST))).*)*$", key),
                                    self.__node_set.get_node_dictionary().keys()))

                            if len(possible_child_node_key_list) > 0:
                                for item in possible_child_node_key_list:
                                    self.__dependency_list.append(
                                        Dependency(temp_node, self.__node_set.get_node_dictionary()[item],
                                                   DependencyType.get_or()))  # Dependency Type: OR

                            if node_data.get_fact_value().get_value_type() == FactValueType.WARNING:
                                self.handle_warning(parent_text)

                        elif pattern_index == 2:  # iterate matcher
                            node_data = IterateLine(child_text, tokens)
                            if node_data.get_fact_value().get_value_type() == FactValueType.WARNING:
                                self.handle_warning(parent_text)
                        elif pattern_index == 3:  # expr conclusion matcher
                            node_data = ExprConclusionLine(child_text, tokens)
                            # In this case, there is no mechanism to find possible parent nodes.
                            # I have brought 'local variable' concept for this case due to it may mass up with
                            # structuring a node dependency tree with topological sort
                            # If ExprConclusion node is used as a child, then it means that this node is a local node
                            # which has to be strictly bound to its parent node only.
                            if node_data.get_fact_value().get_value() == "WARNING":
                                self.handle_warning(parent_text)

                        node_data.set_node_line(line_number)
                        self.__node_set.get_node_dictionary()[node_data.get_node_name()] = node_data
                        self.__node_set.get_node_id_dictionary()[node_data.get_node_id()] = node_data.get_node_name()

            self.__dependency_list.append(Dependency(self.__node_set.get_node(parent_text), node_data, dependency_type))

    def handle_list_item(self, parent_text: str, item_text: str, meta_type: MetaType) -> None:
        tokens = Tokenizer.get_tokens(item_text)
        fv = None

        if tokens.get_tokens_string() == "Da":
            fact_value_in_date = datetime.strptime(item_text, '%d/%m/%Y')
            fv = FactValue(fact_value_in_date, FactValueType.DATE)
        elif tokens.get_tokens_string() == "De":
            fv = FactValue(float(item_text), FactValueType.DOUBLE)
        elif tokens.get_tokens_string() == "No":
            fv = FactValue(int(item_text), FactValueType.INTEGER)
        elif tokens.get_tokens_string() == "Ha":
            fv = FactValue(item_text, FactValueType.HASH)
        elif tokens.get_tokens_string() == "Url":
            fv = FactValue(item_text, FactValueType.URL)
        elif tokens.get_tokens_string() == "Id":
            fv = FactValue(item_text, FactValueType.GUID)
        elif re.match(r"(F|f)(A|a)(L|l)(S|s)(E|e)", item_text) or re.match(r"(T|t)(R|r)(U|u)(E|e)", item_text):
            fv = FactValue(item_text, FactValueType.BOOLEAN)
        else:
            fv = FactValue(item_text)

        string_to_get_fact_value = (parent_text[5: parent_text.index("AS")]).strip()
        if meta_type == MetaType.INPUT:
            fact_value: FactValue = self.__node_set.get_input_dictionary().get(string_to_get_fact_value)
            if fact_value.get_value_type() is not FactValueType.LIST:
                fact_value = FactValue(list(), FactValueType.LIST)
            list(fact_value.get_value()).append(fv)
        elif meta_type == MetaType.FIXED:
            fact_value: FactValue = self.__node_set.get_fact_dictionary().get(string_to_get_fact_value)
            if fact_value.get_value_type() is not FactValueType.LIST:
                fact_value = FactValue(list(), FactValueType.LIST)
            fact_value.get_value().append(fv)

    def get_node_set(self) -> NodeSet:
        return self.__node_set

    def handle_warning(self, parent_text) -> str:
        warning_text = parent_text + ": rule format is not matched. Please check the format again"
        logging.warning(warning_text)
        return warning_text

    # this method is to create virtual nodes where a certain node has 'AND' or 'MANDATORY_AND',
    # and 'OR' children at the same time. When a virtual node is created, all 'AND' children should be connected to
    # the virtual node as 'AND' children and the virtual node should be a 'OR' child of the original parent node
    def handling_virtual_node(self, dependency_list: list) -> dict:
        virtual_node_dictionary: dict = {}
        for each_node in self.__node_set.get_node_dictionary().values():
            virtual_node_dictionary[each_node.get_node_name()] = each_node
            temp_dependency_list: list = \
                list(filter(lambda dp: each_node.get_node_name() == dp.get_parent_node().get_node_name()
                            , dependency_list))

            # need to handle Mandatory, optionally, possibly NodeOptions
            and_dependency = 0
            mandatory_and_dependency = 0
            or_dependency = 0
            if len(temp_dependency_list) != 0:
                for dp in temp_dependency_list:
                    if dp.get_dependency_type() & DependencyType.get_and() \
                            == DependencyType.get_and():
                        and_dependency = and_dependency + 1
                        if dp.get_dependency_type() is (DependencyType.get_mandatory() | DependencyType.get_and()):
                            mandatory_and_dependency = mandatory_and_dependency + 1
                    elif dp.get_dependency_type() & DependencyType.get_or() \
                            == DependencyType.get_or():
                        or_dependency = or_dependency + 1

                has_and_or = False
                if and_dependency > 0 and or_dependency > 0:
                    has_and_or = True

                if has_and_or:
                    parent_node_of_virtual_node_name = each_node.get_node_name()
                    node_line_type = each_node.get_line_type()
                    virtual_node: Node
                    virtual_node_name_text = "VirtualNode-" + parent_node_of_virtual_node_name
                    if node_line_type == LineType.EXPR_CONCLUSION:
                        virtual_node = ExprConclusionLine(virtual_node_name_text,
                                                          Tokenizer.get_tokens(virtual_node_name_text))
                    else:
                        virtual_node = ValueConclusionLine(virtual_node_name_text,
                                                           Tokenizer.get_tokens(virtual_node_name_text))

                    self.__node_set.get_node_id_dictionary()[virtual_node.get_node_id()] = virtual_node_name_text
                    virtual_node_dictionary[virtual_node_name_text] = virtual_node

                    if mandatory_and_dependency > 0:
                        dependency_list.append(
                            Dependency(each_node, virtual_node,
                                       (DependencyType.get_mandatory() | DependencyType.get_or())))
                    else:
                        dependency_list.append(Dependency(each_node, virtual_node, DependencyType.get_or()))

                    for dp in list(filter(lambda each_dp: each_dp.get_dependency_type() == DependencyType.get_and() or
                                                          each_dp.get_dependency_type() == (
                                                                  DependencyType.get_mandatory() | DependencyType.get_and()),
                                          temp_dependency_list)):
                        dp.set_parent_node(virtual_node)

        return virtual_node_dictionary

    def create_dependency_matrix(self) -> DependencyMatrix:
        self.__node_set.set_node_dictionary(self.handling_virtual_node(self.__dependency_list))

        # number of rule is not always matched with the last ruleId in Node

        number_of_rules = Node.get_static_node_id()
        dependency_matrix = [[-1] * number_of_rules for i in range(number_of_rules)]

        for dp in self.__dependency_list:
            parent_id = dp.get_parent_node().get_node_id()
            child_id = dp.get_child_node().get_node_id()
            dp_type = dp.get_dependency_type()
            dependency_matrix[parent_id][child_id] = dp_type

        return DependencyMatrix(dependency_matrix)

    def set_node_set(self, ns: NodeSet) -> None:
        self.__node_set = ns

    def handle_not_known_man_opt_pos(self, first_token_string: str, dependency_type: int) -> int:
        DependencyType.populating_dependency()
        if dependency_type != -1:
            dependency_type_matcher = DependencyTypeStringMatcher.get_all_line_matchers()
            for index in range(len(dependency_type_matcher)):
                regex = re.compile(dependency_type_matcher[index])
                match = regex.match(first_token_string)
                if match:
                    dependency_type = dependency_type | DependencyType.get_dependency_array()[index]

        return dependency_type
