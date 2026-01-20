import json
from project.loggers import Logger
from project.nodes.node import Node
from . import MetaData, DependencyMatrix
import utils
import inspect


logging: Logger = Logger.get_logger(__name__)


class NodeSet:
    __nodeSetName: str
    __inputDictionary: dict
    __factDictionary: dict
    __nodeDictionary: dict
    __nodeIdDictionary: dict
    __sortedNodeList: []
    __defaultGoalNode: Node
    __dependencyMatrix: DependencyMatrix

    def __init__(self):
        self.__nodeSetName = ''
        self.__inputDictionary = dict()
        self.__factDictionary = dict()
        self.__nodeDictionary = dict()
        self.__nodeIdDictionary = dict()
        self.__sortedNodeList = []
        self.__defaultGoalNode = None
        self.__dependencyMatrix: DependencyMatrix = DependencyMatrix([[]])
        logging.info("NodeSet is generated")

    def __repr__(self):
        return json.dumps(self.__dict__)

    def get_dependency_matrix(self) -> DependencyMatrix:
        return self.__dependencyMatrix

    def set_dependency_matrix(self, dependency_matrix):
        if isinstance(dependency_matrix, list):
            self.__dependencyMatrix = DependencyMatrix(dependency_matrix)
        elif isinstance(dependency_matrix, DependencyMatrix):
            self.__dependencyMatrix = dependency_matrix

    def get_node_set_name(self) -> str:
        return self.__nodeSetName

    def set_node_set_name(self, node_set_name):
        if len(node_set_name) == 0:
            logging.error("node_set_name is None")
        self.__nodeSetName = node_set_name

    def set_node_id_dictionary(self, node_id_dictionary):
        if len(node_id_dictionary) == 0:
            logging.debug("node_id_dictionary has no items")
        self.__nodeIdDictionary = node_id_dictionary

    def get_node_id_dictionary(self) -> dict:
        return self.__nodeIdDictionary

    def set_node_dictionary(self, node_dictionary):
        if len(node_dictionary) == 0:
            logging.debug("node_dictionary has no items")
        self.__nodeDictionary = node_dictionary

    def get_node_dictionary(self) -> dict:
        return self.__nodeDictionary

    def set_sorted_node_list(self, sorted_node_list):
        if len(sorted_node_list) == 0:
            logging.error("sorted_node_list has no items")
        self.__sortedNodeList = sorted_node_list

    def get_sorted_node_list(self) -> list:
        return self.__sortedNodeList

    def get_input_dictionary(self) -> dict:
        return self.__inputDictionary

    def set_fact_dictionary(self, fact_dictionary):
        if len(fact_dictionary) == 0:
            logging.info("fact_dictionary has no items")
        self.__factDictionary = fact_dictionary

    def get_fact_dictionary(self) -> dict:
        return self.__factDictionary

    def get_node(self, node_index) -> Node:
        return self.get_sorted_node_list()[node_index]

    def get_node(self, node_name) -> Node:
        return self.get_node_dictionary()[node_name]

    def get_node_by_node_id(self, node_id) -> Node:
        return self.get_node(self.get_node_id_dictionary()[node_id])

    def find_node_index(self, node_name) -> int:
        for node_index in range(len(self.get_sorted_node_list())):
            if self.get_sorted_node_list()[node_index].get_node_name() == node_name:
                return node_index

    def set_default_goal_node(self, name):
        self.__defaultGoalNode = self.get_node_dictionary().get(name)

    def get_default_goal_node(self) -> Node:
        return self.__defaultGoalNode

    def transfer_fact_dictionary_to_working_memory(self, working_memory) -> dict:
        if len(working_memory) == 0:
            logging.info("working_memory has no items")
        for key in self.get_fact_dictionary().keys():
            working_memory[key] = self.get_fact_dictionary()[key]

        return working_memory
    
    def build_rule_tree(self):
        from typing import Optional
        from dataclasses import dataclass, field
        @dataclass
        class TreeNode:
            meta_data: Optional["MetaData"]
            type: str
            node_id: int
            node_name: str
            variable_name: str
            value: any
            children: list["TreeNode"] = field(default_factory=list)

            @classmethod
            def get_init_args_name(cls) -> list[str]:
                sig = inspect.signature(cls.__init__)
                return [param for param in sig.parameters if param != 'self']
            
            def __init__(self, meta_data: MetaData=None, type: str=None, node_id: int=None, node_name: str=None, variable_name: str=None, value: any=None):
                self.meta_data = meta_data
                self.type = type
                args = TreeNode.inspect.signature()
                param_not_be_none_list = ['node_id', 'node_name', 'variable_name', 'value']
                for arg in args:
                    if arg in param_not_be_none_list and arg == None:
                        raise ValueError(f'{arg} cannot be None')
                
                self.node_id = node_id
                self.node_name = node_name
                self.variable_name = variable_name
                self.value = value
            


            def add_child(self, child: "TreeNode") -> None:
                """Add a child node to this tree node."""
                self.children.append(child)

            def has_children(self) -> bool:
                """Return True if this node has one or more children."""
                return bool(self.children)

            def __repr__(self):
                data = vars(self)
                return json.dumps(data, cls=utils.CustomJSONEncoder, indent=2, sort_keys=True)



        rule_tree_data: list = []
        rele_tree_temp_dict: dict = {}

        
        for node in reversed(self.__sortedNodeList):
            has_children, children_index_list = self._has_children(node.get_node_id())
            
            if has_children:
                children_temp_list = [ self.__nodeDictionary[self.__nodeIdDictionary[child_index]] for child_index in children_index_list]
                children_list = [TreeN]
                treeNode = TreeNode(MetaData = node.get_meta_data(), 
                                type='decision' if len(children_list)>0 else 'outcome',  
                                node_id= node.get_node_id(),
                                node_name=node.get_node_name(),
                                variable_name=node.get_variable_name(),
                                value=node.get_fact_value().get_value(),
                                children=children_list)


        for key, children_list in rule_tree_dict.items():
            node = self.__nodeDictionary[self.__nodeIdDictionary[key]]
            [TreeNode()]
            treeNode = TreeNode(MetaData = node.get_meta_data(), 
                                type='decision' if len(children_list)>0 else 'outcome',  
                                node_id= node.get_node_id(),
                                node_name=node.get_node_name(),
                                variable_name=node.get_variable_name(),
                                value=node.get_fact_value().get_value(),
                                children=children_list)

    def _has_children(self, node_id:int) -> tuple[bool, list]:
        return len(self.__dependencyMatrix.get_to_child_dependency_list(node_id)) > 0, self.__dependencyMatrix.get_to_child_dependency_list(node_id)
        
    def _has_parents(self, node_id: int) -> tuple[bool, list]:
        return len(self.__dependencyMatrix.get_from_parent_dependency_list(node_id)) > 0, self.__dependencyMatrix.get_from_parent_dependency_list(node_id)
    
        
        