import json

from project.nodes.dependency_type import DependencyType


class DependencyMatrix:
    # order of dependency type
    # 1. MANDATORY
    # 2. OPTIONAL
    # 3. POSSIBLE
    # 4. AND
    # 5. OR
    # 6. NOT
    # 7. KNOWN
    # int value will be '1' if any one of them is true case otherwise '0'
    # for instance, if a rule is in 'MANDATORY AND NOT' dependency then
    # dependency type value is '1001010'
    #
    # if there is no dependency then value is 0000000

    __dependencyTwoDimensionList: list[list[any]] = None
    __dependencyListSize: int = None

    def __repr__(self):
        return json.dumps(self.__dict__)

    def __init__(self, dependency_two_dimension_list=None):
        self.__dependencyTwoDimensionList = dependency_two_dimension_list
        self.__dependencyListSize = len(dependency_two_dimension_list)

    def get_dependency_two_dimension_list(self) -> list:
        return self.__dependencyTwoDimensionList

    def get_dependency_type(self, parent_rule_id, child_rule_id) -> int:
        return self.__dependencyTwoDimensionList[parent_rule_id][child_rule_id]

    def get_to_child_dependency_list(self, node_id) -> list:

        target_node_dependency_list = self.__dependencyTwoDimensionList[node_id]
        
        return [
            child_index
            for child_index, value in enumerate(target_node_dependency_list)
            if (
                value != -1
                and child_index != node_id
            )
        ]


    def get_or_to_child_dependency_list(self, node_id) -> list:
    
        target_node_dependency_list = self.__dependencyTwoDimensionList[node_id]
        or_dependency = DependencyType.get_or()
        
        return [
            child_index
            for child_index, value in enumerate(target_node_dependency_list)
            if (
                value != -1
                and child_index != node_id
                and (value & or_dependency) == or_dependency
            )
        ]


    def get_and_to_child_dependency_list(self, node_id) -> list:
        
        target_node_dependency_list = self.__dependencyTwoDimensionList[node_id]
        and_dependency = DependencyType.get_and()
        
        return [
            child_index
            for child_index, value in enumerate(target_node_dependency_list)
            if(
                value != -1
                and child_index != node_id
                and (value & and_dependency) == and_dependency
            )
        ]
        

    def get_mandatory_to_child_dependency_list(self, node_id) -> list:

        target_node_dependency_list = self.__dependencyTwoDimensionList[node_id]
        mandatory_dependency = DependencyType.get_mandatory()

        return [
            child_index
            for child_index, value in enumerate(target_node_dependency_list)
            if (
                value != -1 
                and child_index != node_id 
                and (value & mandatory_dependency) == mandatory_dependency
            )
        ]


    def get_from_parent_dependency_list(self, node_id) -> list:
        return [
            parent_index
            for parent_index, row in enumerate(self.__dependencyTwoDimensionList)
            if parent_index != node_id and row[node_id] != -1
        ]


    def has_mandatory_child_node(self, node_id) -> bool:

        return len(self.get_mandatory_to_child_dependency_list(node_id)) > 0
