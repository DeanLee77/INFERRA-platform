import pytest

from fact_values.fact_value import FactValue
from fact_values.fact_value_type import FactValueType
from inference.assessment_state import AssessmentState
from nodes.node_set import NodeSet


@pytest.fixture(scope="function")
def my_assessment_state():
    instance = []

    first = "person qualifies for the grant"
    second = "person's name = \"troy jones\""
    third = "person's dob > 01/01/1990"
    my_list = [first, second, third]
    instance.append(my_list)

    fact_dict: dict = {}
    for item in my_list:
        fact_dict[item] = True

    instance.append(fact_dict)
    return instance


def test_init(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_inclusive_list(my_assessment_state[0])
    assessment_state.set_exclusive_list(my_assessment_state[0])
    assessment_state.set_summary_list(my_assessment_state[0])
    assessment_state.set_mandatory_list(my_assessment_state[0])

    to_be_true = True

    if not len(assessment_state.get_inclusive_list()) == 3:
        to_be_true = False
    if not len(assessment_state.get_mandatory_list()) == 3:
        to_be_true = False
    if not len(assessment_state.get_summary_list()) == 3:
        to_be_true = False
    if not len(assessment_state.get_working_memory()) == 0:
        to_be_true = False
    if not len(assessment_state.get_exclusive_list()) == 3:
        to_be_true = False
    assert to_be_true is True


def test_transfer_fact_map_to_working_memory(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_inclusive_list(my_assessment_state[0])

    node_set: NodeSet = NodeSet()
    node_set.set_fact_dictionary(my_assessment_state[1])
    assessment_state.transfer_fact_map_to_working_memory(node_set)
    to_be_true = True
    if not len(assessment_state.get_working_memory()) == 3:
        to_be_true = False
    for key in assessment_state.get_working_memory().keys():
        if assessment_state.get_working_memory()[key] is not True:
            to_be_true = False
    assert to_be_true is True


def test_lookup_working_memory(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_inclusive_list(my_assessment_state[0])

    node_set: NodeSet = NodeSet()
    node_set.set_fact_dictionary(my_assessment_state[1])
    assessment_state.transfer_fact_map_to_working_memory(node_set)

    to_be_true = True
    for item in my_assessment_state[0]:
        if assessment_state.lookup_working_memory(item) is not True:
            to_be_true = False

    assert to_be_true is True


def test_add_item_to_summary_list(my_assessment_state):
    assessment_state = AssessmentState()

    for item in my_assessment_state[0]:
        assessment_state.add_item_to_summary_list(item)

    to_be_true = True
    for summary_item in my_assessment_state[0]:
        if summary_item not in assessment_state.get_summary_list():
            to_be_true = False
    assert to_be_true is True


def test_is_in_inclusive_list(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_inclusive_list(my_assessment_state[0])

    to_be_true = True
    for item in my_assessment_state[0]:
        if not assessment_state.is_in_inclusive_list(item):
            to_be_true = False
    assert to_be_true is True


def test_is_in_exclusive_list(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_exclusive_list(my_assessment_state[0])

    to_be_true = True
    for item in my_assessment_state[0]:
        if not assessment_state.is_in_exclusive_list(item):
            to_be_true = False
    assert to_be_true is True


def test_add_item_to_mandatory_list(my_assessment_state):
    assessment_state = AssessmentState()
    for item in my_assessment_state[0]:
        assessment_state.add_item_to_mandatory_list(item)

    to_be_true = True
    for index in range(len(assessment_state.get_mandatory_list())):
        if not assessment_state.get_mandatory_list()[index] == \
               my_assessment_state[0][index]:
            to_be_true = False

    assert to_be_true is True


def test_is_in_mandatory_list(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_mandatory_list(my_assessment_state[0])

    to_be_true = True
    for item in my_assessment_state[0]:
        if item not in assessment_state.get_mandatory_list():
            to_be_true = False

    assert to_be_true is True


def test_all_mandatory_node_determined(my_assessment_state):
    assessment_state = AssessmentState()
    assessment_state.set_mandatory_list(my_assessment_state[0])
    assessment_state.set_working_memory(my_assessment_state[1])

    assert assessment_state.all_mandatory_node_determined() is True


def test_set_fact(my_assessment_state):
    assessment_state = AssessmentState()
    for key in my_assessment_state[1]:
        assessment_state.set_fact(key, FactValue(my_assessment_state[1][key]))

    to_be_true = True
    for item in assessment_state.get_working_memory():
        working_memory = assessment_state.get_working_memory()
        if working_memory[item].get_value_type() is not FactValueType.BOOLEAN:
            to_be_true = False
        if working_memory[item].get_value() is not True:
            to_be_true = False

    assert to_be_true is True


def test_get_fact(my_assessment_state):
    assessment_state = AssessmentState()
    for key in my_assessment_state[1]:
        assessment_state.set_fact(key, FactValue(my_assessment_state[1][key]))

    to_be_true = True
    for item in my_assessment_state[0]:
        if assessment_state.get_fact(item).get_value_type() is not FactValueType.BOOLEAN:
            to_be_true = False
        if assessment_state.get_fact(item).get_value() is not True:
            to_be_true = False

    assert to_be_true is True


def test_remove_fact(my_assessment_state):
    assessment_state = AssessmentState()
    for key in my_assessment_state[1]:
        assessment_state.set_fact(key, FactValue(my_assessment_state[1][key]))

    assessment_state.remove_fact(my_assessment_state[0][0])
    to_be_true = True
    if my_assessment_state[0][0] in assessment_state.get_working_memory().keys():
        to_be_true = False

    assert to_be_true is True
