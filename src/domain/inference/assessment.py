"""
Assessment Class.
Manages a single assessment session in INFERRA analysis.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Any, Dict, List, Optional
from src.shared.loggers import Logger
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet

# Protected Module-Level Logger (Access Level: Protected)
_logging: Logger = Logger.get_logger(__name__)


class Assessment:
    """
    Assessment class allows users to perform multiple assessments
    within one or multiple conditions.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, node_set: Optional[NodeSet] = None, goal_node_name: Optional[str] = None):
        """
        Public Constructor: Initializes Assessment.
        
        Args:
            node_set: Optional NodeSet containing rules
            goal_node_name: Optional goal node name for assessment
        """
        self.__assessment_name: Optional[str] = None
        self.__goal_node: Optional[Node] = None
        self.__mandatory_list: List[str] = []
        self.__summary_list: List[str] = []
        self.__inclusive_list: List[str] = []
        self.__exclusive_list: List[str] = []
        self.__goal_node_index: int = -1
        self.__node_to_be_asked: Optional[Node] = None
        self.__aux_node_to_be_asked: Optional[Node] = None

        if node_set is not None and goal_node_name is not None:
            self._initialize_assessment(node_set, goal_node_name)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _initialize_assessment(self, node_set: NodeSet, goal_node_name: str) -> None:
        """
        Protected Helper: Initializes assessment with node set and goal.
        
        Args:
            node_set: NodeSet containing rules
            goal_node_name: Name of the goal node
        """
        self.__goal_node = node_set.get_node_dictionary().get(goal_node_name)
        self.__goal_node_index = node_set.find_node_index(goal_node_name)
        self.__assessment_name = self.__goal_node.get_node_name() if self.__goal_node else goal_node_name

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Assessment Name)
    # -------------------------------------------------------------------------
    def get_assessment_name(self) -> Optional[str]:
        """
        Public API: Returns the assessment name.
        
        Returns:
            Assessment name or None
        """
        return self.__assessment_name

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Goal Node)
    # -------------------------------------------------------------------------
    def get_goal_node(self) -> Optional[Node]:
        """
        Public API: Returns the goal node.
        
        Returns:
            Goal node or None
        """
        return self.__goal_node

    def set_goal_node(self, node_set: NodeSet, goal_node_name: str) -> None:
        """
        Public API: Sets the goal node.
        
        Args:
            node_set: NodeSet containing rules
            goal_node_name: Name of the goal node
        """
        self.__goal_node = node_set.get_node_dictionary().get(goal_node_name)
        self.__goal_node_index = node_set.find_node_index(goal_node_name)

    def get_goal_node_index(self) -> int:
        """
        Public API: Returns the goal node index.
        
        Returns:
            Goal node index in sorted list
        """
        return self.__goal_node_index

    def set_assessment(self, node_set: NodeSet, goal_node_name: str) -> None:
        """
        Public API: Sets up the assessment.
        
        Args:
            node_set: NodeSet containing rules
            goal_node_name: Name of the goal node
        """
        self._initialize_assessment(node_set, goal_node_name)
        self.__node_to_be_asked = None

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Mandatory List)
    # -------------------------------------------------------------------------
    def get_mandatory_list(self) -> List[str]:
        """
        Public API: Returns the mandatory list.
        
        Returns:
            List of mandatory node names
        """
        return self.__mandatory_list

    def set_mandatory_list(self, mandatory_list: List[str]) -> None:
        """
        Public API: Sets the mandatory list.
        
        Args:
            mandatory_list: List of mandatory node names
        """
        self.__mandatory_list = mandatory_list

    def is_in_mandatory_list(self, node_name: str) -> bool:
        """
        Public API: Checks if node is in mandatory list.
        
        Args:
            node_name: Name of the node to check
            
        Returns:
            True if node is in mandatory list
        """
        return node_name in self.__mandatory_list

    def add_item_into_mandatory_list(self, node_name: str) -> None:
        """
        Public API: Adds an item to the mandatory list.
        
        Args:
            node_name: Name of the node to add
        """
        self.__mandatory_list.append(node_name)

    def is_all_mandatory_item_determined(self, working_memory: Dict[str, Any]) -> bool:
        """
        Public API: Checks if all mandatory items are determined.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            True if all mandatory items are determined
        """
        determined_count = len(list(filter(lambda x: x in working_memory.keys(), 
                                           self.__mandatory_list)))
        return determined_count == len(self.__mandatory_list)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Inclusive List)
    # -------------------------------------------------------------------------
    def get_inclusive_list(self) -> List[str]:
        """
        Public API: Returns the inclusive list.
        
        Returns:
            List of inclusive node names
        """
        return self.__inclusive_list

    def set_inclusive_list(self, inclusive_list: List[str]) -> None:
        """
        Public API: Sets the inclusive list.
        
        Args:
            inclusive_list: List of inclusive node names
        """
        self.__inclusive_list = inclusive_list

    def add_item_into_inclusive_list(self, node_name: str) -> None:
        """
        Public API: Adds an item to the inclusive list.
        
        Args:
            node_name: Name of the node to add
        """
        self.__inclusive_list.append(node_name)

    def is_in_inclusive_list(self, name: str) -> bool:
        """
        Public API: Checks if name is in inclusive list.
        
        Args:
            name: Name to check
            
        Returns:
            True if name is in inclusive list
        """
        if len(name) == 0:
            _logging.debug("name is None")
            return False
        return name in self.__inclusive_list

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Summary List)
    # -------------------------------------------------------------------------
    def get_summary_list(self) -> List[str]:
        """
        Public API: Returns the summary list.
        
        Returns:
            List of summary node names
        """
        return self.__summary_list

    def set_summary_list(self, summary_list: List[str]) -> None:
        """
        Public API: Sets the summary list.
        
        Args:
            summary_list: List of summary node names
        """
        if len(summary_list) == 0:
            _logging.debug("summary_list is None")
        self.__summary_list = summary_list

    def add_item_to_summary_list(self, node: str) -> None:
        """
        Public API: Adds an item to the summary list.
        
        Args:
            node: Node name to add
        """
        if len(node) == 0:
            _logging.error("node is None")
            return
        if node not in self.__summary_list:
            self.__summary_list.append(node)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Exclusive List)
    # -------------------------------------------------------------------------
    def get_exclusive_list(self) -> List[str]:
        """
        Public API: Returns the exclusive list.
        
        Returns:
            List of exclusive node names
        """
        return self.__exclusive_list

    def set_exclusive_list(self, exclusive_list: List[str]) -> None:
        """
        Public API: Sets the exclusive list.
        
        Args:
            exclusive_list: List of exclusive node names
        """
        if len(exclusive_list) == 0:
            _logging.debug("exclusive_list is None")
        self.__exclusive_list = exclusive_list

    def is_in_exclusive_list(self, name: str) -> bool:
        """
        Public API: Checks if name is in exclusive list.
        
        Args:
            name: Name to check
            
        Returns:
            True if name is in exclusive list
        """
        if len(name) == 0:
            _logging.debug("name is None")
            return False
        return name in self.__exclusive_list

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Node To Be Asked)
    # -------------------------------------------------------------------------
    def set_node_to_be_asked(self, node_to_be_asked: Optional[Node]) -> None:
        """
        Public API: Sets the node to be asked.
        
        Args:
            node_to_be_asked: Node to be asked
        """
        self.__node_to_be_asked = node_to_be_asked

    def get_node_to_be_asked(self) -> Optional[Node]:
        """
        Public API: Returns the node to be asked.
        
        Returns:
            Node to be asked or None
        """
        return self.__node_to_be_asked

    def set_aux_node_to_be_asked(self, aux_node_to_be_asked: Optional[Node]) -> None:
        """
        Public API: Sets the auxiliary node to be asked.
        
        Args:
            aux_node_to_be_asked: Auxiliary node to be asked
        """
        self.__aux_node_to_be_asked = aux_node_to_be_asked

    def get_aux_node_to_be_asked(self) -> Optional[Node]:
        """
        Public API: Returns the auxiliary node to be asked.
        
        Returns:
            Auxiliary node to be asked or None
        """
        return self.__aux_node_to_be_asked

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps({
            "assessment_name": self.__assessment_name,
            "goal_node_index": self.__goal_node_index,
            "mandatory_list": self.__mandatory_list,
            "summary_list": self.__summary_list,
            "inclusive_list": self.__inclusive_list,
            "exclusive_list": self.__exclusive_list
        })
