import re
from collections import deque
from project.nodes import MetaData
from project.inference import TopologicalSort
from project.nodes.node_set import NodeSet
from project.rule_parser import ILineReader
from project.rule_parser import IScanFeeder
from project.loggers import Logger

logging: Logger = Logger.get_logger(__name__)


class RuleSetScanner:

    def __int__(self):
        self.__scan_feeder: IScanFeeder = None
        self.__line_reader: ILineReader = None
        self.__use_historical_data: bool = False
        self.__record_dict_of_nodes: dict = {}

    def __init__(self, reader: ILineReader, feeder: IScanFeeder):
        self.__scan_feeder = feeder
        self.__line_reader = reader

    def scan_rule_set(self):
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
                # it trims off whitespace including 'if' at the end of each line
                # due to it could affect on calculating indentation
                line = re.sub("\\s*(if)*\\s*$", "", line)
                line_trimmed = line.strip()
                current_whitespace = 0
                line_number = line_number + 1
                # check the line
                # is it empty?
                if len(line) == 0:
                    parent_stack.clear()
                    new_meta_data = MetaData()
                elif line_trimmed.startswith(('#', '//')) or not line_trimmed:

                    # this els if statement is to handle commenting in new line only
                    # handling commenting in rule text file needs enhancement later
                    logging.debug(f'Comment Line: {line_trimmed}')
                    if MetaData.is_meta_data(line_trimmed) and len(parent_stack) == 0:
                        new_meta_data.instantiate_attrs(line)

                # does it begin with a white space?
                elif line[0].isspace():
                    current_whitespace = len(line) - len(line_trimmed)  # calculating indentation level
                    if line[0] != '\t' and current_whitespace % 4 == 0:
                        current_whitespace = int(current_whitespace/4)

                    if len(line_trimmed) == 0:  # is it a blank line?
                        parent = ""
                    else:
                        indentation_difference = previous_whitespace - current_whitespace

                        if indentation_difference == -4:  # this condition is for handling inputs from ACE text editor
                            indentation_difference = -1

                        # current line is at same level as previous line | | current line is in upper level than previous line
                        if indentation_difference == 0 or indentation_difference > 0:
                            parent_stack = self.handling_stack_pop(parent_stack, indentation_difference)
                        elif indentation_difference < -1:  # current line is not a direct child of previous line hence the format is invalid
                            # need to handle error
                            self.__scan_feeder.handle_warning(line_trimmed)
                            break

                        parent = parent_stack[-1]
                        temp_line_trimmed = \
                            re.sub(
                                "^(OR\\s?|AND\\s?)?(MANDATORY|OPTIONALLY|POSSIBLY)?(\\s?NOT|\\s?KNOWN)*(NEEDS|WANTS)?",
                                "", line_trimmed.strip()).strip()

                        temp_first_keywords_group = line_trimmed.replace(temp_line_trimmed, "").strip()
                        parent_stack.append(
                            temp_line_trimmed.strip())  # due to line_trimmed string contains keywords such as "AND", "OR", "AND KNOWN" or "OR KNOWN" so that it needs removing those keywords for the 'parentStack'
                        
                        # is an indented child
                        self.__scan_feeder.handle_child(parent, temp_line_trimmed, temp_first_keywords_group,
                                                        line_number)
                else:  # does not begin with a white space
                    # is a parent
                    parent_stack.clear()
                    parent = line_trimmed
                    self.__scan_feeder.handle_parent(parent, line_number, new_meta_data)
                    parent_stack.append(parent)

                previous_whitespace = current_whitespace

    def establish_node_set(self, record_node_dictionary: dict = None):
        node_set: NodeSet = self.__scan_feeder.get_node_set()
        node_set.set_dependency_matrix(self.__scan_feeder.create_dependency_matrix())
        if record_node_dictionary is not None:
            sorted_list: list = TopologicalSort.dfs_topological_sort_with_record(node_set.get_node_dictionary(),
                                                                     node_set.get_node_id_dictionary(),
                                                                     node_set.get_dependency_matrix().get_dependency_two_dimension_list(),
                                                                     record_node_dictionary)
        else:
            sorted_list: list = TopologicalSort.bfs_topological_sort(node_set.get_node_dictionary(),
                                                                     node_set.get_node_id_dictionary(),
                                                                     node_set.get_dependency_matrix().get_dependency_two_dimension_list())

        if len(sorted_list) != 0:
            node_set.set_sorted_node_list(sorted_list)
        else:
            self.__scan_feeder.handle_warning("RuleSet needs rewriting due to it is cyclic.")

    def handling_stack_pop(self, parent_stack: dict, indentation_diff: int):
        for i in range(indentation_diff + 1):
            parent_stack.pop()
        return parent_stack

    def set_historical_data(self):
        self.__use_historical_data = not self.__use_historical_data

    def set_record_dictionary_of_nodes(self, record_dict_of_nodes: dict):
        self.__record_dict_of_nodes = record_dict_of_nodes

    def get_record_dict_of_nodes(self):
        return self.__record_dict_of_nodes
