import json

from project.loggers import Logger
from project.nodes.node import Node

logging: Logger = Logger.get_logger(__name__)


class Dependency:
    __dependencyType = None # this variable is to store 'AND/OR' DependencyType between Nodes
    __parent = None # this variable is to store a parent Node of this dependency
    __child = None # this variable is to store a child Node of this dependency

    def __init__(self, parent: Node, child: Node, dependency_type: int):
        self.__parent = parent
        self.__child = child
        self.__dependencyType = dependency_type
        logging.info("Generating Dependency with : " + str(dependency_type) +
                     ", Parent Text: " + str(parent.get_node_line()) +
                     ", Child Text: " + str(child.get_node_line()))

    def __repr__(self):
        return json.dumps(self.__dict__)

    def get_parent_node(self):
        return self.__parent

    def set_parent_node(self, parent):
        self.__parent = parent

    def get_child_node(self):
        return self.__child

    def set_child_node(self, child):
        self.__child = child

    def get_dependency_type(self):
        return self.__dependencyType
