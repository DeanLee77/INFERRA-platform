import logging
import os
import pdb
import re

import pytest
from nodes.dependency_matrix import DependencyMatrix
from nodes.dependency_type import DependencyType


class DependencyString:
    dependency_id: int = 0
    dependency_string: str = ""

    def __init__(self, dependency_string: str):
        string_array = dependency_string.split(":")
        self.dependency_string = string_array[1].strip()
        self.dependency_id = int(string_array[0].strip())


class DependencyMatrixList:
    list_dependency_matrix = [[-1 for j in range(12)] for i in range(12)]
    test_dependency_matrix: DependencyMatrix = DependencyMatrix(list_dependency_matrix)

    def __init__(self):
        pass

    @classmethod
    def create_dependency_matrix(cls):
        cls.test_dependency_matrix = DependencyMatrix(cls.list_dependency_matrix)

    @classmethod
    def add_values(cls, parent: DependencyString, children: []):
        parent_id = parent.dependency_id
        for child in children:
            child_id = child.dependency_id
            dependency_type = cls.handling_and_or(child.dependency_string)
            cls.list_dependency_matrix[parent_id][child_id] = dependency_type

    @classmethod
    def handling_and_or(cls, text: str) -> int:
        dependency_type = 0
        and_pattern = re.compile(r"^AND")
        or_pattern = re.compile(r"^OR")
        if and_pattern.search(text):
            dependency_type = dependency_type | DependencyType.get_and()
        elif or_pattern.search(text):
            dependency_type = dependency_type | DependencyType.get_or()

        return cls.handling_not_known_man_opt_pos(text, dependency_type)

    @classmethod
    def handling_not_known_man_opt_pos(cls, text: str, dependency_type: int) -> int:
        if dependency_type != 0:
            if text.find("NOT") != -1:
                dependency_type |= DependencyType.get_not()
            if text.find("KNOWN") != -1:
                dependency_type |= DependencyType.get_known()
            if text.find("MANDATORY") != -1:
                dependency_type |= DependencyType.get_mandatory()
            if text.find("OPTIONAL") != -1:
                dependency_type |= DependencyType.get_optional()
            if text.find("POSSIBLY") != -1:
                dependency_type |= DependencyType.get_possible()

        return dependency_type


@pytest.fixture(scope="function")
def dependency_matrix_list():
    instance = DependencyMatrixList()
    yield instance

    with open(os.path.dirname(__file__) + '/dependency_matrix_testing.txt') as f:
        lines = f.readlines()
        for line in lines:
            line_array = line.split("&")
            parent = DependencyString(line_array[0].strip())
            second_line_array = line_array[1].strip().split("-")
            children_dependency_array = []
            for child_line in second_line_array:
                child = DependencyString(child_line.strip())
                children_dependency_array.append(child)

            instance.add_values(parent, children_dependency_array)
        instance.create_dependency_matrix()
        return instance


def test_get_dependency_two_dimension_list(dependency_matrix_list):
    correct_size = True
    my_test = dependency_matrix_list.test_dependency_matrix
    matrix_array = my_test.get_dependency_two_dimension_list()
    if len(matrix_array) != 12:
        correct_size = False
    for child_array in matrix_array:
        if len(child_array) != 12:
            correct_size = False
    assert correct_size is True


def test_get_dependency_type(dependency_matrix_list):
    result = True
    my_test = dependency_matrix_list.test_dependency_matrix
    matrix_array = my_test.get_dependency_two_dimension_list()
    for index in range(len(matrix_array)):
        if index == 0:
            for j in range(len(matrix_array[index])):
                if j == 1 or j == 2 or j == 3:
                    if matrix_array[index][j] == -1:
                        result = False
        if index == 4:
            for j in range(len(matrix_array[index])):
                if j == 5 or j == 6 or j == 7:
                    if matrix_array[index][j] == -1:
                        result = False
        if index == 8:
            for j in range(len(matrix_array[index])):
                if j == 9 or j == 10 or j == 11:
                    if matrix_array[index][j] == -1:
                        result = False

    assert result is True


def test_get_to_child_dependency_list(dependency_matrix_list):
    result = True
    my_test = dependency_matrix_list.test_dependency_matrix
    child_list = my_test.get_to_child_dependency_list(0)
    expected_child_array = [1, 2, 3]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    child_list = my_test.get_to_child_dependency_list(4)
    expected_child_array = [5, 6, 7]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    child_list = my_test.get_to_child_dependency_list(8)
    expected_child_array = [9, 10, 11]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    assert result is True


def test_get_or_to_child_dependency_list(dependency_matrix_list):
    result = True
    my_test = dependency_matrix_list.test_dependency_matrix
    child_list = my_test.get_or_to_child_dependency_list(0)
    expected_child_array = [1, 2, 3]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    child_list = my_test.get_or_to_child_dependency_list(4)
    expected_child_array = [7]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    child_list = my_test.get_or_to_child_dependency_list(8)
    expected_child_array = [10]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    assert result is True


def test_get_and_to_child_dependency_list(dependency_matrix_list):
    result = True
    my_test = dependency_matrix_list.test_dependency_matrix
    child_list = my_test.get_and_to_child_dependency_list(0)
    expected_child_array = []
    if len(child_list) is not 0:
        result = False
    child_list = my_test.get_and_to_child_dependency_list(4)
    expected_child_array = [5, 6]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    child_list = my_test.get_and_to_child_dependency_list(8)
    expected_child_array = [9, 11]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    assert result is True


def test_get_mandatory_to_child_dependency_list(dependency_matrix_list):
    result = True
    my_test = dependency_matrix_list.test_dependency_matrix
    child_list = my_test.get_mandatory_to_child_dependency_list(0)
    expected_child_array = [3]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    child_list = my_test.get_mandatory_to_child_dependency_list(4)
    if len(child_list) is not 0:
        result = False
    child_list = my_test.get_mandatory_to_child_dependency_list(8)
    expected_child_array = [11]
    for child_id in child_list:
        if child_id not in expected_child_array:
            result = False
    assert result is True


def test_get_from_parent_dependency_list(dependency_matrix_list):
    result = True
    my_test = dependency_matrix_list.test_dependency_matrix
    expected_parent_list = []
    for index in range(12):
        if index == 1 or index == 2 or index == 3:
            expected_parent_list = [0]
            parent_list = my_test.get_from_parent_dependency_list(index)
            if len(parent_list) is not 1:
                result = False
            for parent in parent_list:
                if parent not in expected_parent_list:
                    result = False
        elif index == 5 or index == 6 or index == 7:
            expected_parent_list = [4]
            parent_list = my_test.get_from_parent_dependency_list(index)
            if len(parent_list) is not 1:
                result = False
            for parent in parent_list:
                if parent not in expected_parent_list:
                    result = False
        elif index == 9 or index == 10 or index == 11:
            expected_parent_list = [8]
            parent_list = my_test.get_from_parent_dependency_list(index)
            if len(parent_list) is not 1:
                result = False
            for parent in parent_list:
                if parent not in expected_parent_list:
                    result = False
    assert result is True


# def test_has_mandatory_child_node(dependency_matrix_list):
#     result = True
#     my_test = dependency_matrix_list.test_dependency_matrix
#     if not my_test.get_mandatory_to_child_dependency_list(0):
#         result = False
#     if my_test.get_mandatory_to_child_dependency_list(4):
#         result = False
#     if not my_test.get_mandatory_to_child_dependency_list(8):
#         result = False
#
#     assert result is True
