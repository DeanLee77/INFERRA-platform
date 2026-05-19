from src.domain.fact_values import FactValue
from src.domain.inference.assessment_state import AssessmentState
from src.domain.state import FactSource


def test_set_fact_defaults_to_asserted_layer():
    state = AssessmentState()
    state.set_fact("user_age", FactValue(30))

    assert state.get_fact_sources("user_age") == {FactSource.ASSERTED}


def test_set_fact_writes_to_specified_layer():
    state = AssessmentState()
    state.set_fact("rule_conclusion", FactValue(True), source=FactSource.INFERRED)

    assert state.get_fact_sources("rule_conclusion") == {FactSource.INFERRED}


def test_unified_view_merges_all_three_layers():
    state = AssessmentState()
    state.set_fact("a", FactValue(1), source=FactSource.ASSERTED)
    state.set_fact("b", FactValue(2), source=FactSource.INFERRED)
    state.set_fact("c", FactValue(3), source=FactSource.SEMANTIC)

    unified = state.get_working_memory()

    assert set(unified.keys()) == {"a", "b", "c"}


def test_asserted_wins_on_collision_in_unified_view():
    state = AssessmentState()
    state.set_fact("eligibility", FactValue("inferred-value"), source=FactSource.INFERRED)
    state.set_fact("eligibility", FactValue("user-value"), source=FactSource.ASSERTED)

    unified = state.get_working_memory()

    assert unified["eligibility"].get_value() == "user-value"


def test_inferred_wins_over_semantic():
    state = AssessmentState()
    state.set_fact("flag", FactValue("ontology"), source=FactSource.SEMANTIC)
    state.set_fact("flag", FactValue("rule-engine"), source=FactSource.INFERRED)

    unified = state.get_working_memory()

    assert unified["flag"].get_value() == "rule-engine"


def test_unified_view_returns_fresh_dict_each_call():
    state = AssessmentState()
    state.set_fact("x", FactValue(1))

    first_view = state.get_working_memory()
    first_view["mutated"] = FactValue("ghost")
    second_view = state.get_working_memory()

    assert "mutated" not in second_view


def test_get_fact_sources_reports_multi_layer_membership():
    state = AssessmentState()
    state.set_fact("dual", FactValue("A"), source=FactSource.ASSERTED)
    state.set_fact("dual", FactValue("I"), source=FactSource.INFERRED)

    assert state.get_fact_sources("dual") == {FactSource.ASSERTED, FactSource.INFERRED}


def test_remove_fact_without_source_clears_all_layers():
    state = AssessmentState()
    state.set_fact("k", FactValue("A"), source=FactSource.ASSERTED)
    state.set_fact("k", FactValue("I"), source=FactSource.INFERRED)
    state.set_fact("k", FactValue("S"), source=FactSource.SEMANTIC)

    state.remove_fact("k")

    assert state.get_fact_sources("k") == set()


def test_remove_fact_with_source_targets_only_that_layer():
    state = AssessmentState()
    state.set_fact("k", FactValue("A"), source=FactSource.ASSERTED)
    state.set_fact("k", FactValue("I"), source=FactSource.INFERRED)

    state.remove_fact("k", source=FactSource.ASSERTED)

    assert state.get_fact_sources("k") == {FactSource.INFERRED}


def test_lookup_working_memory_walks_layers_in_precedence_order():
    state = AssessmentState()
    state.set_fact("k", FactValue("inferred"), source=FactSource.INFERRED)
    state.set_fact("k", FactValue("semantic"), source=FactSource.SEMANTIC)

    assert state.lookup_working_memory("k").get_value() == "inferred"

    state.set_fact("k", FactValue("asserted"), source=FactSource.ASSERTED)

    assert state.lookup_working_memory("k").get_value() == "asserted"


def test_set_working_memory_clears_other_layers():
    state = AssessmentState()
    state.set_fact("old_inferred", FactValue("I"), source=FactSource.INFERRED)
    state.set_fact("old_semantic", FactValue("S"), source=FactSource.SEMANTIC)

    state.set_working_memory({"new_key": FactValue("new_value")})

    assert state.get_fact_sources("old_inferred") == set()
    assert state.get_fact_sources("old_semantic") == set()
    assert state.get_fact_sources("new_key") == {FactSource.ASSERTED}


def test_all_mandatory_node_determined_walks_all_layers():
    state = AssessmentState()
    state.set_mandatory_list(["needs_user", "needs_rule"])
    state.set_fact("needs_user", FactValue(True), source=FactSource.ASSERTED)

    assert state.all_mandatory_node_determined() is False

    state.set_fact("needs_rule", FactValue(True), source=FactSource.INFERRED)

    assert state.all_mandatory_node_determined() is True
