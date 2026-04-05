"""
Rule Set Scanner Module.
Scans and parses rule sets from various input sources.
Implements access levels and strong typing where appropriate.
"""

import re
from collections import deque
from typing import Dict, Optional
from project.nodes import MetaData
from project.inference import TopologicalSort
from project.nodes.node_set import NodeSet
from project.rule_parser import ILineReader, IScanFeeder
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class RuleSetScanner:
    """
    RuleSetScanner scans rule sets from input sources and builds node structures.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, reader: ILineReader, feeder: IScanFeeder):
        """
        Public Constructor: Initializes RuleSetScanner.
        
        Args:
            reader: ILineReader instance for reading input
            feeder: IScanFeeder instance for feeding parsed data
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__scan_feeder: IScanFeeder = feeder
        self.__line_reader: ILineReader = reader
        self.__use_historical_data: bool = False
        self.__record_dict_of_nodes: Dict = {}
        
        _logger.info("RuleSetScanner initialized")

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Scanning)
    # -------------------------------------------------------------------------
    def scan_rule_set(self) -> None:
        """
        Public API: Scans the rule set from the input source.
        
        Raises:
            RuntimeError: If no file has been loaded
        """
        parent = ""
        line = ""
        line_trimmed = ""
        parent_stack = deque()
        previous_whitespace = 0
        line_number = 0
        still_lines = True
        new_meta_data = MetaData()
        
        while still_lines:
            line = self.__line_reader.get_next_line()
            
            if line == "":
                still_lines = False
                break
            else:
                # Trim whitespace including 'if' at the end of each line
                line = re.sub(r"\s*(if)*\s*$", "", line)
                line_trimmed = line.strip()
                current_whitespace = 0
                line_number = line_number + 1
                
                # Check if line is empty
                if len(line) == 0:
                    parent_stack.clear()
                    new_meta_data = MetaData()
                elif line_trimmed.startswith(('#', '//')) or not line_trimmed:
                    # Handle commenting in new line only
                    _logger.debug(f'Comment Line: {line_trimmed}')
                    if MetaData.is_meta_data(line_trimmed) and len(parent_stack) == 0:
                        new_meta_data.instantiate_attrs(line)
                elif line[0].isspace():
                    # Calculate indentation level
                    current_whitespace = len(line) - len(line_trimmed)
                    if line[0] != '\t' and current_whitespace % 4 == 0:
                        current_whitespace = int(current_whitespace / 4)
                    
                    if len(line_trimmed) == 0:
                        parent = ""
                    else:
                        indentation_difference = previous_whitespace - current_whitespace
                        
                        if indentation_difference == -4:
                            indentation_difference = -1
                        
                        if indentation_difference == 0 or indentation_difference > 0:
                            parent_stack = self._handling_stack_pop(parent_stack, indentation_difference)
                        elif indentation_difference < -1:
                            # Current line is not a direct child of previous line - invalid format
                            self.__scan_feeder.handle_warning(line_trimmed)
                            break
                        
                        parent = parent_stack[-1]
                        temp_line_trimmed = re.sub(
                            r"^(OR\s?|AND\s?)?(MANDATORY|OPTIONALLY|POSSIBLY)?(\s?NOT|\s?KNOWN)*(NEEDS|WANTS)?",
                            "", line_trimmed.strip()).strip()
                        
                        temp_first_keywords_group = line_trimmed.replace(temp_line_trimmed, "").strip()
                        parent_stack.append(temp_line_trimmed.strip())
                        
                        # Handle indented child
                        self.__scan_feeder.handle_child(parent, temp_line_trimmed, 
                                                       temp_first_keywords_group, line_number)
                else:
                    # Does not begin with whitespace - is a parent
                    parent_stack.clear()
                    parent = line_trimmed
                    self.__scan_feeder.handle_parent(parent, line_number, new_meta_data)
                    parent_stack.append(parent)
                
                previous_whitespace = current_whitespace

    def establish_node_set(self, record_node_dictionary: Optional[Dict] = None) -> NodeSet:
        """
        Public API: Establishes the node set from scanned rules.
        
        Args:
            record_node_dictionary: Optional historical record dictionary
            
        Returns:
            NodeSet object with established rules
        """
        node_set: NodeSet = self.__scan_feeder.get_node_set()
        node_set.set_dependency_matrix(self.__scan_feeder.create_dependency_matrix())
        
        if record_node_dictionary is not None:
            sorted_list = TopologicalSort.dfs_topological_sort_with_record(
                node_set.get_node_dictionary(),
                node_set.get_node_id_dictionary(),
                node_set.get_dependency_matrix().get_dependency_two_dimension_list(),
                record_node_dictionary
            )
        else:
            sorted_list = TopologicalSort.bfs_topological_sort(
                node_set.get_node_dictionary(),
                node_set.get_node_id_dictionary(),
                node_set.get_dependency_matrix().get_dependency_two_dimension_list()
            )
        
        if len(sorted_list) != 0:
            node_set.set_sorted_node_list(sorted_list)
        else:
            self.__scan_feeder.handle_warning("RuleSet needs rewriting due to it is cyclic.")
        
        return node_set

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Configuration)
    # -------------------------------------------------------------------------
    def set_historical_data(self) -> None:
        """
        Public API: Toggles historical data usage.
        """
        self.__use_historical_data = not self.__use_historical_data

    def set_record_dictionary_of_nodes(self, record_dict_of_nodes: Dict) -> None:
        """
        Public API: Sets the record dictionary of nodes.
        
        Args:
            record_dict_of_nodes: Dictionary of node records
        """
        self.__record_dict_of_nodes = record_dict_of_nodes

    def get_record_dict_of_nodes(self) -> Dict:
        """
        Public API: Returns the record dictionary of nodes.
        
        Returns:
            Dictionary of node records
        """
        return self.__record_dict_of_nodes

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _handling_stack_pop(self, parent_stack: deque, indentation_diff: int) -> deque:
        """
        Protected Helper: Handles popping from parent stack based on indentation.
        
        Args:
            parent_stack: Current parent stack
            indentation_diff: Indentation difference
            
        Returns:
            Modified parent stack
        """
        for i in range(indentation_diff + 1):
            if len(parent_stack) > 0:
                parent_stack.pop()
        return parent_stack