"""
Assessment State Class.
Manages the state during rule assessment in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

from typing import Any, Dict, List, Optional
from project.fact_values import FactValue, FactValueType
from project.loggers import Logger
from project.nodes import LineType
from project.nodes.node import Node
from project.nodes.node_set import NodeSet

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class AssessmentState:
    """
    AssessmentState manages working memory and rule lists during assessment.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self):
        """
        Public Constructor: Initializes AssessmentState.
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__working_memory: Dict[str, FactValue] = {}
        self.__inclusive_list: List[str] = []
        self.__exclusive_list: List[str] = []
        self.__summary_list: List[str] = []
        self.__mandatory_list: List[str] = []
        
        _logger.info("AssessmentState is generated")

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Working Memory)
    # -------------------------------------------------------------------------
    def get_working_memory(self) -> Dict[str, FactValue]:
        """
        Public API: Returns the working memory dictionary.
        
        Returns:
            Working memory dictionary
        """
        return self.__working_memory

    def set_working_memory(self, working_memory: Dict[str, FactValue]) -> None:
        """
        Public API: Sets the working memory dictionary.
        
        Args:
            working_memory: Working memory dictionary to set
        """
        self.__working_memory = working_memory

    def lookup_working_memory(self, key_name: str) -> Optional[FactValue]:
        """
        Public API: Looks up a value in working memory by key.
        
        Args:
            key_name: Key to look up
            
        Returns:
            FactValue or None
        """
        if len(key_name) == 0:
            _logger.debug("key_name is None")
            return None
        return self.__working_memory.get(key_name)

    def set_fact(self, node_variable_name: str, value: FactValue, node: Optional[Node] = None) -> None:
        """
        Public API: Sets a fact in the working memory.
        
        Args:
            node_variable_name: Variable name of the node
            value: FactValue to store
            node: Optional node object for context
        """
        if len(node_variable_name) == 0:
            _logger.debug("node_variable_name is None")
            return
        
        if node_variable_name in self.__working_memory.keys():
            self._handle_existing_fact(node_variable_name, value, node)
        else:
            self.__working_memory[node_variable_name] = value

    def get_fact(self, name: str) -> Optional[FactValue]:
        """
        Public API: Gets a fact from working memory.
        
        Args:
            name: Name of the fact
            
        Returns:
            FactValue or None
        """
        return self.__working_memory.get(name)

    def remove_fact(self, name: str) -> None:
        """
        Public API: Removes a fact from working memory.
        
        Args:
            name: Name of the fact to remove
        """
        if len(name) == 0:
            _logger.info("name is None")
            return
        self.__working_memory.pop(name, None)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _handle_existing_fact(self, node_variable_name: str, value: FactValue, node: Optional[Node]) -> None:
        """
        Protected Helper: Handles logic when fact already exists in working memory.
        
        Args:
            node_variable_name: Variable name of the node
            value: FactValue to store
            node: Optional node object for context
        """
        temp_fv: FactValue = self.__working_memory[node_variable_name]
        if temp_fv.get_value_type() == FactValueType.LIST:
            temp_fv.get_value().append(value)
        elif node is not None and self._should_create_list(node):
            fact_value_list: List[FactValue] = [temp_fv, value]
            fact_value: FactValue = FactValue(fact_value_list, FactValueType.LIST)
            self.__working_memory[node_variable_name] = fact_value

    def _should_create_list(self, node: Node) -> bool:
        """
        Protected Helper: Determines if a list should be created.
        
        Args:
            node: Node to evaluate
            
        Returns:
            True if list should be created
        """
        has_is_token = len(list(filter(lambda token_string: token_string == 'IS',
                                        node.get_tokens().get_tokens_list()))) > 0
        is_comparison = (node.get_line_type() == LineType.COMPARISON and node.get_operator() == '==')
        return has_is_token or is_comparison

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

    def is_in_inclusive_list(self, name: str) -> bool:
        """
        Public API: Checks if name is in inclusive list.
        
        Args:
            name: Name to check
            
        Returns:
            True if name is in inclusive list
        """
        if len(name) == 0:
            _logger.debug("name is None")
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
            _logger.debug("summary_list is None")
        self.__summary_list = summary_list

    def add_item_to_summary_list(self, node: str) -> None:
        """
        Public API: Adds an item to the summary list.
        
        Args:
            node: Node name to add
        """
        if len(node) == 0:
            _logger.error("node is None")
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
            _logger.debug("exclusive_list is None")
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
            _logger.debug("name is None")
            return False
        return name in self.__exclusive_list

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
        if len(mandatory_list) == 0:
            _logger.debug("mandatory_list is None")
        self.__mandatory_list = mandatory_list

    def add_item_to_mandatory_list(self, node_name: str) -> None:
        """
        Public API: Adds an item to the mandatory list.
        
        Args:
            node_name: Name of the node to add
        """
        if len(node_name) == 0:
            _logger.debug("node_name is None")
            return
        if node_name not in self.__mandatory_list:
            self.__mandatory_list.append(node_name)

    def is_in_mandatory_list(self, node_name: str) -> bool:
        """
        Public API: Checks if node is in mandatory list.
        
        Args:
            node_name: Name of the node to check
            
        Returns:
            True if node is in mandatory list
        """
        return node_name in self.__mandatory_list

    def all_mandatory_node_determined(self) -> bool:
        """
        Public API: Checks if all mandatory nodes are determined.
        
        Returns:
            True if all mandatory nodes are determined
        """
        filtered_list = [node_name for node_name in self.__mandatory_list 
                        if node_name in self.__working_memory.keys()]
        return len(filtered_list) == len(self.__mandatory_list)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (RuleSet Integration)
    # -------------------------------------------------------------------------
    def transfer_fact_map_to_working_memory(self, node_set: Optional[NodeSet]) -> None:
        """
        Public API: Transfers fact map from RuleSet to working memory.
        
        Args:
            node_set: NodeSet containing facts
        """
        if node_set is None:
            _logger.debug("node_set is None")
            return
        if len(node_set.get_fact_dictionary()) > 0:
            self.__working_memory = node_set.transfer_fact_dictionary_to_working_memory(self.__working_memory)

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        import json
        return json.dumps({
            "working_memory": str(self.__working_memory),
            "inclusive_list": self.__inclusive_list,
            "exclusive_list": self.__exclusive_list,
            "summary_list": self.__summary_list,
            "mandatory_list": self.__mandatory_list
        })