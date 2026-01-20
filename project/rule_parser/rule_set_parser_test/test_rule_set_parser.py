import pytest

from fact_values.fact_value import FactValue
from fact_values.fact_value_type import FactValueType
from nodes.dependency import Dependency
from nodes.dependency_type import DependencyType
from nodes.line_type import LineType
from nodes.meta_type import MetaType
from nodes.metadata_line import MetadataLine
from nodes.node import Node
from nodes.node_set import NodeSet
from rule_parser.rule_set_parser import RuleSetParser


class RuleSetParserTest:
    meta_parent_1 = "INPUT the groom's name AS TEXT"
    meta_parent_2 = "FIXED the groom's homepage IS https://www.theGroomHomepage.com.au"
    meta_parent_3 = "FIXED the wedding booking schedule for the venue AS LIST"
    first_key_group = "ITEM"
    meta_child_1 = "ITEM someone"
    meta_child_2 = "ITEM somebody"
    meta_child_3 = "ITEM nobody"

    first_key_group_2 = "AND"
    first_key_group_3 = "OR"
    value_con = "person must meet military service criteria"
    comparison = "enlistment date >= 01/07/1951"
    exp_con = "yearly period of service by 6/04/1994 IS CALC (6/04/1994 - enlistment date)"

    rule_set_parser = RuleSetParser()

    def __init__(self):pass

    def handle_parent_value_con(self):
        self.rule_set_parser.handle_parent(self.value_con, 6)

    def handle_child_com(self):
        self.rule_set_parser.handle_child(self.value_con, self.comparison, self.first_key_group_2, 7)

    def handle_parent_exp_con(self):
        self.rule_set_parser.handle_parent(self.exp_con, 8)

    def handle_parent_meta_input(self):
        self.rule_set_parser.handle_parent(self.meta_parent_1, 1)

    def handle_parent_meta_fixed(self):
        self.rule_set_parser.handle_parent(self.meta_parent_2, 2)

    def handle_parent_meta_with_child(self):
        self.rule_set_parser.handle_parent(self.meta_parent_3, 3)

    def handle_child_meta_item(self):
        self.rule_set_parser.handle_child(self.meta_parent_3, self.meta_child_1, "", 4)

    def handle_child_meta_item_2(self):
        self.rule_set_parser.handle_child(self.meta_parent_3, self.meta_child_2, "", 5)

    def create_dependency_matrix(self):
        self.rule_set_parser.get_node_set().set_dependency_matrix(
            self.rule_set_parser.create_dependency_matrix())

@pytest.fixture(scope="function")
def rule_set_parser_test():
    instance = RuleSetParserTest()
    yield instance

    return instance


def test_handle_parent(rule_set_parser_test):
    rule_set_parser_test.handle_parent_value_con()
    rule_set_parser_test.handle_parent_exp_con()
    rule_set_parser_test.handle_parent_meta_input()
    rule_set_parser_test.handle_parent_meta_fixed()
    rule_set_parser_test.handle_parent_meta_with_child()
    rule_set_parser_test.create_dependency_matrix()

    passTest = True

    node_set: NodeSet = rule_set_parser_test.rule_set_parser.get_node_set()

    is_value_con = node_set.get_node_dictionary().get('person must meet military service criteria').get_line_type() \
                   is LineType.VALUE_CONCLUSION

    if is_value_con is not True:
        passTest = False

    is_expr_con = node_set.get_node_dictionary().get('yearly period of service by 6/04/1994 IS CALC (6/04/1994 - enlistment date)').get_line_type()\
                  is LineType.EXPR_CONCLUSION
    if is_expr_con is not True:
        passTest = False

    fact_value: FactValue = node_set.get_input_dictionary()["the groom's name"]
    is_string = fact_value.get_value_type().value is FactValueType.STRING.value
    if is_string is not True:
        passTest = False


    second_fact_value: FactValue = node_set.get_fact_dictionary()["the groom's homepage"]
    is_url = second_fact_value.get_value_type().value is FactValueType.URL.value
    value_is_correct = second_fact_value.get_value() == "https://www.theGroomHomepage.com.au"
    if is_url is not True and value_is_correct is True:
        passTest = False

    third_fact_value: FactValue = node_set.get_fact_dictionary().get("the wedding booking schedule for the venue")
    is_list = third_fact_value.get_value_type().value == FactValueType.LIST.value
    if is_list is not True:
        passTest = False

    assert passTest is True


def test_handle_child(rule_set_parser_test):
    # rule_set_parser_test.handle_parent_value_con()
    rule_set_parser_test.handle_child_com()
    # rule_set_parser_test.handle_parent_exp_con()

    # rule_set_parser_test.handle_parent_meta_input()
    # rule_set_parser_test.handle_parent_meta_fixed()
    # rule_set_parser_test.handle_parent_meta_with_child()
    rule_set_parser_test.handle_child_meta_item()
    rule_set_parser_test.handle_child_meta_item_2()

    rule_set_parser_test.create_dependency_matrix()

    passTest = True

    node_set: NodeSet = rule_set_parser_test.rule_set_parser.get_node_set()

    node: Node = node_set.get_node_dictionary()["enlistment date >= 01/07/1951"]
    is_comparison = node.get_line_type() is LineType.COMPARISON

    parent_node: Node = node_set.get_node_dictionary()['person must meet military service criteria']

    dependency: DependencyType = node_set.get_dependency_matrix()\
        .get_dependency_type(parent_node.get_node_id(), node.get_node_id())

    is_and_dependency = dependency == DependencyType.get_and()
    child_node_list: list = node_set.get_dependency_matrix().get_to_child_dependency_list(parent_node.get_node_id())
    has_one_item = len(child_node_list) == 1
    correct_child = child_node_list[0] == node.get_node_id()

    if is_comparison is not True \
            and is_and_dependency is not True \
            and has_one_item is not True \
            and correct_child is not True:
        passTest = False

    fixed_item: FactValue = node_set.get_fact_dictionary()["the wedding booking schedule for the venue"]
    child_item_list = list(fixed_item.get_value())
    has_two_items = len(child_item_list) == 2
    has_all_items = True

    if FactValue(child_item_list[0]).get_value() != "someone" and \
        FactValue(child_item_list[1]).get_value() != "somebody":
        has_all_items = False

    if has_two_items is not True and has_all_items is not True:
        passTest = False


    assert passTest is True



