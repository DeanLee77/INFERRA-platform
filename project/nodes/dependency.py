"""
Dependency Module.
Represents a single dependency relationship between two nodes.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Optional
from project.loggers import Logger
from project.nodes.node import Node

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class Dependency:
    """
    Dependency represents a relationship between parent and child nodes.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, parent: Node, child: Node, dependency_type: int):
        """
        Public Constructor: Initializes Dependency.
        
        Args:
            parent: Parent node
            child: Child node
            dependency_type: Dependency type integer
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__dependency_type: int = dependency_type
        self.__parent: Optional[Node] = parent
        self.__child: Optional[Node] = child
        
        _logger.info(
            "Generating Dependency with : " + str(dependency_type) +
            ", Parent Text: " + str(parent.get_node_line()) +
            ", Child Text: " + str(child.get_node_line())
        )

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_parent_node(self) -> Optional[Node]:
        """
        Public API: Returns the parent node.
        
        Returns:
            Parent Node or None
        """
        return self.__parent

    def get_child_node(self) -> Optional[Node]:
        """
        Public API: Returns the child node.
        
        Returns:
            Child Node or None
        """
        return self.__child

    def get_dependency_type(self) -> int:
        """
        Public API: Returns the dependency type.
        
        Returns:
            Dependency type integer
        """
        return self.__dependency_type

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_parent_node(self, parent: Node) -> None:
        """
        Public API: Sets the parent node.
        
        Args:
            parent: Parent Node to set
        """
        self.__parent = parent

    def set_child_node(self, child: Node) -> None:
        """
        Public API: Sets the child node.
        
        Args:
            child: Child Node to set
        """
        self.__child = child

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