# workingMemory : dictionary{string : FactValue}
#     first 'String' Key represents a Node's variableName and/or nodeName,
#       or it could be a NodeSet's name in further development on.
#     second 'FactValue' Value represents the Rule's value or Fact's value.
# inclusiveList : list(string)
#     it stores all relevant rule as assessment goes by,
#     and the parameter String represents rule.getName().
#
# exclusiveList : list(string)
#     it stores all irrelevant rule as assessment goes by,
#     and the parameter String represents rule.getName().
from project.fact_values import FactValue, FactValueType
from project.loggers import Logger
from project.nodes import LineType
from project.nodes.node import Node
from project.nodes.node_set import NodeSet
import json

logging: Logger = Logger.get_logger(__name__)


class AssessmentState:
    __workingMemory: dict
    __inclusiveList: list
    __exclusiveList: list
    __summaryList: list
    __mandatoryList: list

    def __init__(self):
        self.__workingMemory = {}

        # this is to capture all relevant rules
        self.__inclusiveList = []

        # this is to store all determined rules within assessment in order.
        self.__summaryList = []

        # this is to capture all trimmed rules
        self.__exclusiveList = []

        self.__mandatoryList = []
        logging.info("AssessmentState is generated")


    # this method is to get workingMemory
    def get_working_memory(self) -> dict:
        return self.__workingMemory

    # this method is to set workingMemory from RuleSet instance.
    # this method has to be executed after AssessmentState object initialization.
    # all facts instance will be transferred from ruleMap in RuleSet instance
    # to workingMemory in AssessmentState instance

    def transfer_fact_map_to_working_memory(self, node_set: NodeSet) -> None:
        if NodeSet is None:
            logging.debug("node_set is None")
        if len(node_set.get_fact_dictionary()) > 0:
            self.__workingMemory = \
                node_set.transfer_fact_dictionary_to_working_memory(self.__workingMemory)

    # this is simply for setting workingMemory with a given workingMemory
    def set_working_memory(self, working_memory: dict):
        self.__workingMemory = working_memory

    # it allows a user to look up the workingMemory
    def lookup_working_memory(self, key_name: str) -> FactValue:
        if len(key_name) == 0:
            logging.debug("key_name is None")
        return self.__workingMemory[key_name]

    # it is to get inclusiveList: list()
    def get_inclusive_list(self) -> list:
        return self.__inclusiveList

    def set_inclusive_list(self, inclusive_list: list) -> None:
        self.__inclusiveList = inclusive_list

    def is_in_inclusive_list(self, name: str) -> bool:
        if len(name) == 0:
            logging.debug("name is None")
        return name in self.__inclusiveList

    def add_item_to_summary_list(self, node: str) -> None:
        if len(node) == 0:
            logging.error("node is None")
        if node not in self.__summaryList:
            self.__summaryList.append(node)

    def get_summary_list(self) -> list:
        return self.__summaryList

    def set_summary_list(self, summary_list: list):
        if len(summary_list) == 0:
            logging.debug("summary_list is None")
        self.__summaryList = summary_list

    # // exclusiveList
    def get_exclusive_list(self) -> list:
        return self.__exclusiveList

    def set_exclusive_list(self, exclusive_list: list):
        if len(exclusive_list) == 0:
            logging.debug("exclusive_list is None")
        self.__exclusiveList = exclusive_list

    def is_in_exclusive_list(self, name: str) -> bool:
        if len(name) == 0:
            logging.debug("name is None")
        return name in self.__exclusiveList

    # mandatory_list
    def get_mandatory_list(self) -> list:
        return self.__mandatoryList

    def set_mandatory_list(self, mandatory_list: list) -> None:
        if len(mandatory_list) == 0:
            logging.debug("mandatory_list is None")
        self.__mandatoryList = mandatory_list

    def add_item_to_mandatory_list(self, node_name: str) -> None:
        if len(node_name) == 0:
            logging.debug("node_name is None")
        if node_name not in self.__mandatoryList:
            self.__mandatoryList.append(node_name)

    def is_in_mandatory_list(self, node_name: str) -> bool:
        return node_name in self.__mandatoryList

    def all_mandatory_node_determined(self) -> bool:
        filtered_list = []
        for node_name in self.__mandatoryList:
            if node_name in self.__workingMemory.keys():
                filtered_list.append(node_name)
        return len(filtered_list) == len(self.__mandatoryList)

    # this method is to set a rule as a fact in the workingMemory
    # before this method is called, nodeName should be given and
    # look up nodeMap in NodeSet to find variableName of the node
    # then the variableName of the node should be passed to this method.
    def set_fact(self, node_variable_name: str, value: FactValue, node: Node = None):
        if len(node_variable_name) == 0:
            logging.debug("node_variable_name is None")
        if node_variable_name in self.__workingMemory.keys():
            temp_fv: FactValue = self.__workingMemory[node_variable_name]
            if temp_fv.get_value_type() == FactValueType.LIST:
                temp_fv.get_value().append(value)
            elif node is not None \
                    and (len(list(filter(lambda token_string: token_string == 'IS',
                                         node.get_tokens().get_tokens_list()))) > 0 \
                         or (node.get_line_type() == LineType.COMPARISON and node.get_operator() == '==')):
                fact_value_list: list = [temp_fv, value]
                fact_value: FactValue = FactValue(fact_value_list, FactValueType.LIST)
                self.__workingMemory[node_variable_name] = fact_value
        else:
            self.__workingMemory[node_variable_name] = value

    def get_fact(self, name: str) -> FactValue:
        return self.__workingMemory[name]

    def remove_fact(self, name: str) -> None:
        if len(name) == 0:
            logging.info("name is None")
        self.__workingMemory.pop(name)

    def __repr__(self):
        return json.dumps(self.__dict__)

