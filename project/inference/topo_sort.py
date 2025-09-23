from copy import deepcopy

from project.loggers.logger import Logger
from project.nodes.node import Node
from project.nodes import DependencyType

logging: Logger = Logger.get_logger(__name__)


class TopologicalSort:

    # this topological sort method uses "Kahn's algorithm which is based on BFS(Breadth First Search)
    # within this method, the original 'dependencyMatrix' will lose information of dependency
    # due to the reason that the algorithm itself uses the dependency information
    # and delete it while topological sorting. Hence, this method needs to create copy of dependencyMatrix.

    @staticmethod
    def bfs_topological_sort(node_dictionary: dict, node_id_dictionary: dict, dependency_matrix: [[]]) -> list:
        logging.info("bfs_topological_sort ...")

        sorted_list = list()
        size_of_matrix = len(dependency_matrix)
        copy_of_dependency_matrix = TopologicalSort.create_copy_of_dependency_matrix(dependency_matrix, size_of_matrix)

        temp_list = list()
        s_list = TopologicalSort.filling_s_list(node_dictionary,
                                                node_id_dictionary,
                                                temp_list,
                                                copy_of_dependency_matrix)

        while len(s_list) > 0:
            node = s_list.pop(0)
            sorted_list.append(node)
            node_id = node.get_node_id()

            for index in range(size_of_matrix):
                if (node_id is not index) and copy_of_dependency_matrix[node_id][index] != -1:
                    # this is to remove dependency from 'nodes' to child nodes with nodeId == 'i'
                    copy_of_dependency_matrix[node_id][index] = -1
                    # from this line, it is process to check whether or not the child nodes with nodeId == 'i'
                    # has any other incoming dependencies from other nodes, and the reason for
                    # subtracting 1 from matrixSize is to exclude nodes itself count from the matrix size.
                    number_of_incoming_edge = size_of_matrix - 1
                    for second_index in range(size_of_matrix):
                        if (index != second_index) and (copy_of_dependency_matrix[second_index][index] == -1):
                            number_of_incoming_edge = number_of_incoming_edge - 1
                    # there is no incoming dependencies for the nodes with nodeId == 'i'
                    if number_of_incoming_edge == 0:
                        s_list.append(node_dictionary[node_id_dictionary[index]])

        check_dag = False
        for i in range(size_of_matrix):
            for j in range(size_of_matrix):
                if (i != j) and copy_of_dependency_matrix[i][j] != -1:
                    check_dag = True
                    logging.error("Rules are not DAG, if it is not DAG then rules cannot be sorted.")
                    break

        if check_dag:
            sorted_list.clear()
        # if size of sortedNodeList is '0' then the graph is cyclic so that RuleSet needs rewriting
        # due to it is in incorrect format

        return sorted_list

    @staticmethod
    def filling_s_list(node_dictionary: dict, node_id_dictionary: dict,
                       temp_list: list, dependency_matrix: [[]]) -> list:
        size_of_matrix = len(dependency_matrix)
        for child_row in range(size_of_matrix):
            count = 0
            for parent_col in range(size_of_matrix):
                if (dependency_matrix[parent_col][child_row] == -1) and (parent_col != child_row):
                    count = count + 1
                else:
                    continue
            # exclude its own dependency
            if count == size_of_matrix - 1:
                temp_node_name = node_id_dictionary.get(child_row)
                if temp_node_name is not None:
                    temp_list.append(node_dictionary[temp_node_name])

        return temp_list

    @staticmethod
    def create_copy_of_dependency_matrix(dependency_matrix: [[]], size_of_matrix: int) -> [[]]:
        copy_of_dependency_matrix = [[0 for x in range(size_of_matrix)] for y in range(size_of_matrix)]
        for parent_col in range(size_of_matrix):
            for child_row in range(size_of_matrix):
                copy_of_dependency_matrix[parent_col][child_row] = deepcopy(dependency_matrix[parent_col][child_row])
        return copy_of_dependency_matrix

    # this topological sort method uses DFS(Depth First Search)
    # At this point of time (10th Feb 2018), this method is strictly for sorting child nodes of IterateLine
    # The reason for using this method is only for child nodes of IterateLine is that if there is a child nodes of
    # local variable type. then the sorted order will NOT be appropriate to produce a next question.
    #
    # For instance, if IterateLine nodes has a rule as following.
    # ------------------------------------------------------------
    # ALL service ITERATE: LIST OF service history
    # 	AND number of services
    # 	AND iterate rules
    # 		OR one
    # 			AND enlistment date >= 01/07/1951
    # 			AND discharge date <= 6/12/1972
    # 			AND NOT service type IS IN LIST: Special service
    # 		OR two
    # 			AND enlistment date >= 22/05/1986
    # 			AND yearly period of service by 6/04/1994 >= 3
    # 				AND yearly period of service by 6/04/1994 IS CALC (enlistment date - 6/04/1994)
    # 					NEEDS enlistment date
    # 			AND NOT service type IS IN LIST: Special service
    # 			AND discharge date >= 07/04/1994
    # 			AND discharge date <= 30/06/2004
    # ------------------------------------------------------------
    # and number of service is '2', then the sorted order will be as follows.
    #
    # ------------------------------------------------------------
    #  	ALL service ITERATE: LIST OF service history
    # 	number of services
    #	1st service iterate rules
    # 	2nd service iterate rules
    # 	1st service one
    # 	1st service two
    # 	2nd service one
    # 	2nd service two
    # 	1st service enlistment date >= 01/07/1951
    # 	1st service discharge date <= 6/12/1972
    # 	1st service enlistment date >= 22/05/1986
    # 	1st service yearly period of service by 6/04/1994 >= 3
    # 	1st service service type IS IN LIST: Special service
    # 	1st service enlistment date >= 07/04/1994
    # 	1st service discharge date >= 30/06/2004
    # 	2nd service enlistment date >= 01/07/1951
    # 	2nd service discharge date <= 6/12/1972
    # 	2nd service enlistment date >= 22/05/1986
    # 	2nd service yearly period of service by 6/04/1994 >= 3
    # 	2nd service service type IS IN LIST: Special service
    # 	2nd service enlistment date >= 07/04/1994
    # 	2nd service discharge date >= 30/06/2004
    # 	1st service yearly period of service by 6/04/1994 IS CALC (enlistment date - 6/04/1994)
    # 	2nd service yearly period of service by 6/04/1994 IS CALC (enlistment date - 6/04/1994)
    # 	1st service enlistment date
    # 	2nd service enlistment date
    # ------------------------------------------------------------
    # And therefore, there would cause 1st service question and 2nd service question mixed
    #
    #     !!!!!!!!!!!!!!   I M P O R T A N T  !!!!!!!!!!!!!!!!!!!!
    #
    #     This method does NOT have a mechanism to check if it is DAG or not yet.
    #

    @staticmethod
    def dfs_topological_sort(node_dictionary: dict, node_id_dictionary:     dict, dependency_matrix: [[]]) -> list:

        sorted_list = list()
        copy_of_dependency_matrix = TopologicalSort.create_copy_of_dependency_matrix(dependency_matrix,
                                                                                     len(dependency_matrix))
        s_list = TopologicalSort.filling_s_list(node_dictionary,
                                                node_id_dictionary,
                                                list(),
                                                copy_of_dependency_matrix)
        visited_list = list()
        while len(s_list) > 0:
            node = s_list.pop(0)
            sorted_list.append(node)
            visited_list.append(node.get_node_id())
            node_id = node.get_node_id()
            child_id_list = list()
            for index in range(len(copy_of_dependency_matrix)):
                if copy_of_dependency_matrix[node_id][index] != -1:
                    child_id_list.append(index)

            for child_id in child_id_list:
                current_node = node_dictionary[node_id_dictionary[child_id]]
                if child_id not in visited_list:
                    sorted_list.append(current_node)
                    visited_list.append(child_id)
                    TopologicalSort.deepening(node_dictionary, node_id_dictionary,
                                              copy_of_dependency_matrix, sorted_list,
                                              visited_list, child_id)

        return sorted_list

    @staticmethod
    def deepening(node_dictionary: dict, node_id_dictionary: dict,
                  dependency_matrix: [[]], sorted_list: list,
                  visited_list: list, child_id):

        child_id_list = list()
        for i in range(len(dependency_matrix)):
            if dependency_matrix[child_id][i] != -1:
                child_id_list.append(i)

        for child_id in child_id_list:
            current_node = node_dictionary[node_id_dictionary[child_id]]

            if child_id not in visited_list:
                sorted_list.append(current_node)
                visited_list.append(child_id)

            TopologicalSort.deepening(node_dictionary, node_id_dictionary, dependency_matrix,
                                      sorted_list, visited_list, child_id)

    # this class is another version of topological sort.
    # the first version of topological sort used Kahn's algorithm which is based on Breadth First Search(BFS)
    # Topological sorted list is a fundamental part to get an order list of all questions.
    # However, it always provide same order at all times which might not be shortest path for a certain individual case,
    # therefore, this topological sort based on historical record of each nodes/rule is suggested.
    #
    # logic for the sorting is as follows;
    # note: topological sort logic contains a recursive method
    # 1. set 'S' and 'sortedList'
    # 2. get all data for each rules from database as a HashMap<String, Record>
    # 3. find rules don't have any parent rules, and add them into 'S' list
    # 4. if there is an element in the 'S' list
    # 5. visit the element
    #     5.1 if the element has any child rules
    #         5.1.1 get a list of all child rules, and keep visiting until there are no non-visited rules
    #         5.1.2 if there is not any 'OR' rules ( there are only 'AND' rules)
    #               5.1.2.1 find the most negative rule, and add the rule into the 'sortedList'
    #         5.1.3 if there is not any 'AND' rules ( there are only 'OR' rules)
    #         		5.1.3.1 find the most positive rule, and add the rule into the 'sortedList'
    #
    @staticmethod
    def dfs_topological_sort_with_record(node_dictionary: dict, node_id_dictionary: dict,dependency_matrix: [[]], record_dictionary_of_node: dict) -> list:
        sorted_list = list()
        if (record_dictionary_of_node is None) or (len(record_dictionary_of_node) == 0):
            sorted_list = TopologicalSort.bfs_topological_sort(node_dictionary, node_id_dictionary, dependency_matrix)
        else:
            visited_node_list = list()
            copy_of_dependency_matrix = TopologicalSort.create_copy_of_dependency_matrix(dependency_matrix,len(dependency_matrix))
            s_list = TopologicalSort.filling_s_list(node_dictionary, node_id_dictionary,list(), copy_of_dependency_matrix)

            while len(s_list) > 0:
                node = s_list.pop(0)
                visited_node_list.append(node)
                TopologicalSort.visit(node, sorted_list, record_dictionary_of_node, node_dictionary, node_id_dictionary, visited_node_list, dependency_matrix)
        return sorted_list

    # The idea of this method is to visit a rule that could get a result of parent rule of the rule
    # as quick as it can be for instance, if a 'OR' child rule is 'TRUE' then the parent rule is 'TRUE',
    # and if a 'AND' child rule is 'FALSE' then the parent rule is 'FALSE'.
    # AS result, visit more likely true 'OR' rule or more likely false 'AND' rule to determine a parent rule
    # as fast as we can
    @staticmethod
    def visit(node: Node, sorted_list: list, record_dictionary_of_nodes: dict, node_dictionary: dict, node_id_dictionary: dict, visited_node_list: list, dependency_matrix) -> list:
        if node is not None:
            sorted_list.append(node)
            node_id = node.get_node_id()
            or_dependency_type = DependencyType.get_or()
            and_dependency_type = DependencyType.get_and()
            dependency_matrix_as_list = list(dependency_matrix[node_id])
            size_of_dependency_matrix_as_list = len(dependency_matrix_as_list)
            or_out_dependency = list(
                filter(lambda index: 
                       not dependency_matrix_as_list[index] <= 0 and(dependency_matrix_as_list[index] & or_dependency_type) == or_dependency_type,
                       list([x for x in range(size_of_dependency_matrix_as_list)])))
            and_out_dependency = list(
                filter(lambda index: 
                       not dependency_matrix_as_list[index] <= 0 and
                       (dependency_matrix_as_list[index] & and_dependency_type) == and_dependency_type,
                       list([x for x in range(size_of_dependency_matrix_as_list)])))

            if (len(or_out_dependency) != 0) or (len(and_out_dependency) != 0):
                child_rule_list = list()
                for item in list(filter(lambda child_index: not dependency_matrix_as_list[child_index] <= 0,
                                        list([x for x in range(size_of_dependency_matrix_as_list)]))):
                    child_rule_list.append(node_dictionary[node_id_dictionary[item]])

                if (len(or_out_dependency) != 0) and (len(and_out_dependency) == 0):
                    while len(child_rule_list) != 0:
                        # the reason for selecting an option having more number of 'yes' is as follows
                        # if it is 'OR' rule and it is 'TRUE' then it is the shortest path, and ignore other 'OR' rules
                        # if it is 'OR' rule and it is 'TRUE' then it is the shortest path, and ignore other 'OR' rules
                        # Therefore, looking for more likely 'TRUE' rule would be the shortest one rather than
                        # looking for more likely 'FALSE' rule in terms of processing time

                        the_most_positive, child_rule_list = TopologicalSort.find_the_most_positive(child_rule_list,
                                                                                   record_dictionary_of_nodes,
                                                                                   dependency_matrix_as_list)

                        if the_most_positive not in visited_node_list:
                            visited_node_list.append(the_most_positive)
                            sorted_list = TopologicalSort.visit(the_most_positive, sorted_list,
                                                                record_dictionary_of_nodes, node_dictionary,
                                                                node_id_dictionary, visited_node_list,
                                                                dependency_matrix)

                else:
                    if (len(or_out_dependency) == 0) and (len(and_out_dependency) != 0):
                        # the reason for selecting an option having more number of 'yes' is as follows
                        # if it is 'AND' rule and it is 'FALSE' then it is the shortest path, and ignore
                        # other 'AND' rules. Therefore, looking for more likely 'FALSE' rule would be the
                        # shortest one rather than looking for more likely 'TRUE' rule in terms of
                        # processing time

                        while len(child_rule_list) != 0:
                            the_most_negative, child_rule_list = TopologicalSort.find_the_most_negative(child_rule_list,
                                                                                        record_dictionary_of_nodes,
                                                                                        dependency_matrix_as_list)

                            if the_most_negative not in visited_node_list:
                                visited_node_list.append(the_most_negative)
                                sorted_list = TopologicalSort.visit(the_most_negative, sorted_list,
                                                                    record_dictionary_of_nodes, node_dictionary,
                                                                    node_id_dictionary, visited_node_list,
                                                                    dependency_matrix)
        return sorted_list

    @staticmethod
    def find_the_most_positive(child_node_list: list, record_dictionary_of_nodes: dict,
                               dependency_matrix_as_list: list = None) -> Node:

        the_most_possibility = 0
        summation = 0

        the_most_positive = None

        for node in child_node_list:
            if dependency_matrix_as_list is not None:
                prefix = ""
                dependency_type = dependency_matrix_as_list[node.get_node_id()]
                if (dependency_type & DependencyType.get_known()) == DependencyType.get_known():
                    prefix = "known"
                elif (dependency_type & DependencyType.get_not()) == DependencyType.get_not():
                    prefix = "not"
                elif (dependency_type & (DependencyType.get_not() | DependencyType.get_known())) == \
                        (DependencyType.get_not() | DependencyType.get_known()):
                    prefix = "not known"

                record_of_node = record_dictionary_of_nodes.get(prefix + node.get_node_name())
            else:
                record_of_node = record_dictionary_of_nodes.get(node.get_node_name())

            yes_count = int(_get_true_count(record_of_node)) if record_of_node else 0
            no_count = int(_get_false_count(record_of_node)) if record_of_node else 0
        
            yes_plus_no_count = -1 if yes_count + no_count == 0 else yes_count + no_count

            the_result = 0 if yes_count == 0 else yes_count / yes_plus_no_count

            if TopologicalSort.analysis(the_result, the_most_possibility, yes_plus_no_count, summation):
                the_most_possibility = the_result
                summation = yes_count + no_count
                the_most_positive = node
        child_node_list = [node for node in child_node_list if node.get_node_name() != the_most_positive.get_node_name()]
        
        return the_most_positive, child_node_list

    @staticmethod
    def find_the_most_negative(child_node_list: list, record_dictionary_of_nodes: dict,
                               dependency_matrix_as_list: list = None) -> Node:
        the_most_negative = None

        the_most_possibility = 0
        summation = 0

        for node in child_node_list:

            if dependency_matrix_as_list is not None:
                prefix = ""
                dependency_type = dependency_matrix_as_list[node.get_node_id()]
                if (dependency_type & DependencyType.get_known()) == DependencyType.get_known():
                    prefix = "known"
                elif (dependency_type & DependencyType.get_not()) == DependencyType.get_not():
                    prefix = "not"
                elif (dependency_type & (DependencyType.get_not() | DependencyType.get_known())) == \
                        (DependencyType.get_not() | DependencyType.get_known()):
                    prefix = "not known"

                record_of_node = record_dictionary_of_nodes.get(prefix + node.get_node_name())
            else:
                record_of_node = record_dictionary_of_nodes.get(node.get_node_name())

            yes_count = int(_get_true_count(record_of_node)) if record_of_node else 0
            no_count = int(_get_false_count(record_of_node)) if record_of_node else 0

            yes_plus_no_count = -1 if yes_count + no_count == 0 else yes_count + no_count

            the_result = 0 if no_count == 0 else no_count / yes_plus_no_count

            if TopologicalSort.analysis(the_result, the_most_possibility, yes_plus_no_count, summation):
                the_most_possibility = the_result

                if yes_plus_no_count == -1:
                    summation = yes_plus_no_count
                else:
                    summation = yes_count + no_count
                the_most_negative = node
        child_node_list = [node for node in child_node_list if node.get_node_name() != the_most_negative.get_node_name()]

        return the_most_negative, child_node_list

    @staticmethod
    def analysis(the_result: float, the_most_possibility: float, yes_count_no_count: int, summation: int) -> bool:
        highly_possible = False

        # firstly select an option having more cases and high possibility

        if (the_result > the_most_possibility) and (yes_count_no_count >= summation):
            highly_possible = True

        # secondly, even though the number of being used case is fewer, and it has a high possibility
        # then still select the option

        elif (the_result >= the_most_possibility) and (the_result == 0 and the_most_possibility == 0) and (
                yes_count_no_count > summation):
            highly_possible = True
        elif (the_result >= the_most_possibility) and (the_result == 0) and (yes_count_no_count == -1) and (
                summation <= 0) and (summation != -1):
            highly_possible = True
        elif (the_result >= the_most_possibility) and (the_result == 0) and (yes_count_no_count == -1) and (
                summation <= 0) and (summation != -1):
            highly_possible = True

        return highly_possible

def _get_true_count(record:dict):
    return(record.get('true'))

def _get_false_count(record:dict):
    return(record.get('false'))

def _get_record_type(record:dict):
    return(record.get('type'))