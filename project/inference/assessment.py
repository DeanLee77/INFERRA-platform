import json

from project.loggers import Logger
from project.nodes.node import Node
from project.nodes.node_set import NodeSet

logging: Logger = Logger.get_logger(__name__)

class Assessment:
    """
    the reason of having Assessment class is to allow a user to do multiple assessment within one or multiple conditions.  
    """
    __assessment_name: str
    __goal_node: Node

    # a list of rule statements labelled with 'MANDATORY'
    __mandatory_list: list

    # a list of determined rule statement
    __summary_list: list

    # a list of rule statements must be determined
    __inclusive_list: list

    # a list of rule statement can be skipped
    __exclusive_list: list

    # the goal rule index in sorted rule list of ruleSet
    __goal_node_index: int

    # each instance of this object has a variable of ruleToBeAsked due to the following reasons
    # 1. a user will be allowed to do assessment on multiple investigation points at the same time
    # 2. a user will be allowed to do an assessment within another assessment.
    __node_to_be_asked: Node

    # this variable is to track next node to be asked within 'IterateLine' type node.
    # However, better way needs to be found.
    __aux_node_to_be_asked: Node

    def __init__(self, node_set: NodeSet = None, goal_node_name: str = None):
        self.__goal_node = None
        self.__node_to_be_asked = None
        self.__aux_node_to_be_asked = None
        self.__goal_node_index = -1
        self.__inclusive_list = []
        self.__mandatory_list = []
        self.__summary_list = []
        self.__exclusive_list = []

        if node_set != None and goal_node_name != None:
            self.__goal_node = node_set.get_node_dictionary()[goal_node_name]
            self.__goal_node_index = node_set.find_node_index(goal_node_name)
            self.__assessment_name = self.__goal_node.get_node_name()


    def __repr__(self):
        return json.dumps(self.__dict__)

    def set_assessment(self, node_set: NodeSet, goal_node_name: str):
        self.__goal_node = node_set.get_node_dictionary().get(goal_node_name)
        self.__goal_node_index = node_set.find_node_index(goal_node_name)
        self.__node_to_be_asked = None
        self.__assessment_name = goal_node_name

    def set_goal_node(self, node_set: NodeSet, goal_node_name: str):
        self.__goal_node = node_set.get_node_dictionary().get(goal_node_name)
        self.__goal_node_index = node_set.find_node_index(goal_node_name)

    def get_assessment_name(self) -> str:
        return self.__assessment_name
    
    def get_goal_node(self) -> Node:
        return self.__goal_node
    
    def set_mandatory_list(self, mandatory_list: list):
        self.__mandatory_list = mandatory_list

    def get_mandatory_list(self) -> list:
        return self.__mandatory_list

    def is_in_mandatory_list(self, node_name: str) -> bool:
        return node_name in self.__mandatory_list
    
    def add_item_into_mandatory_list(self, node_name: str):
        self.__mandatory_list.append(node_name)

    def is_all_mandatory_item_determined(self, working_memory: dict) -> bool:
        return len(list(filter(lambda x: x in working_memory.keys(), self.__mandatory_list))) == len(self.__mandatory_list)
    
    def get_inclusive_list(self) -> list:
        return self.__inclusive_list

    def set_inclusive_list(self, inclusive_list: list) -> None:
        self.__inclusive_list = inclusive_list

    def add_item_into_includsive_list(self, node_name: str):
        self.__inclusive_list.append(node_name)

    def is_in_inclusive_list(self, name: str) -> bool:
        if len(name) == 0:
            logging.debug("name is None")
        return name in self.__inclusive_list

    def add_item_to_summary_list(self, node: str) -> None:
        if len(node) == 0:
            logging.error("node is None")
        if node not in self.__summary_list:
            self.__summary_list.append(node)

    def get_summary_list(self) -> list:
        return self.__summary_list

    def set_summary_list(self, summary_list: list):
        if len(summary_list) == 0:
            logging.debug("summary_list is None")
        self.__summary_list = summary_list

    # // exclusiveList
    def get_exclusive_list(self) -> list:
        return self.__exclusive_list

    def set_exclusive_list(self, exclusive_list: list):
        if len(exclusive_list) == 0:
            logging.debug("exclusive_list is None")
        self.__exclusive_list = exclusive_list

    def is_in_exclusive_list(self, name: str) -> bool:
        if len(name) == 0:
            logging.debug("name is None")
        return name in self.__exclusive_list

    def get_goal_node_index(self) -> int:
        return self.__goal_node_index

    def set_node_to_be_asked(self, node_to_be_asked: Node):
        self.__node_to_be_asked = node_to_be_asked

    def get_node_to_be_asked(self) -> Node:
        return self.__node_to_be_asked

    def set_aux_node_to_be_asked(self, aux_node_to_be_asked: Node):
        self.__aux_node_to_be_asked = aux_node_to_be_asked

    def get_aux_node_to_be_asked(self) -> Node:
        return self.__aux_node_to_be_asked
