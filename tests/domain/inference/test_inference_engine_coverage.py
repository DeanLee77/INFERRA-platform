from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.dependency_type import DependencyType
from src.domain.inference.assessment import Assessment
from src.domain.inference.inference_engine import (
    InferenceEngine,
    _noop_question_callback,
    _safe_float,
)
from src.domain.nodes.line_type import LineType
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags


def _node(
    name: str,
    *,
    line_type: LineType = LineType.VALUE_CONCLUSION,
    variable: str | None = None,
    fact_value: FactValue | None = None,
    plain: bool = False,
):
    node = MagicMock()
    node.get_node_name.return_value = name
    node.get_variable_name.return_value = name if variable is None else variable
    node.get_line_type.return_value = line_type
    node.get_fact_value.return_value = fact_value or FactValue("value", FactValueType.STRING)
    node.get_is_plain_statement.return_value = plain
    tokens = MagicMock()
    tokens.get_tokens_list.return_value = []
    node.get_tokens.return_value = tokens
    return node


def _graph(*, groups=None, parents=None, children=None, dep_types=None, edges=None):
    graph = MagicMock()
    graph.get_child_groups.side_effect = lambda name: list((groups or {}).get(name, []))
    graph.get_parent_edges.side_effect = lambda name: set((parents or {}).get(name, set()))
    graph.get_children_flat.side_effect = lambda name: list((children or {}).get(name, []))
    graph.get_dependency_type.side_effect = lambda parent, child: (dep_types or {}).get(
        (parent, child), -1
    )
    graph.edges.return_value = list(edges or [])
    return graph


def _node_set(
    nodes=None,
    *,
    graph=None,
    inputs=None,
    facts=None,
    types=None,
    collections=None,
    sorted_nodes=None,
):
    nodes = nodes or {}
    node_set = MagicMock()
    node_set.get_node_dictionary.return_value = nodes
    node_set.get_graph.return_value = graph
    node_set.get_input_dictionary.return_value = inputs or {}
    node_set.get_fact_dictionary.return_value = facts or {}
    node_set.get_type_dictionary.return_value = types or {}
    node_set.get_collection_dictionary.return_value = collections or {}
    node_set.get_sorted_node_list.return_value = list(sorted_nodes or nodes.values())
    node_set.find_node_index.return_value = 0
    node_set.get_default_goal_node.return_value = next(iter(nodes.values()), None)
    return node_set


def _engine_with_graph(nodes, graph, **kwargs) -> InferenceEngine:
    return InferenceEngine(node_set=_node_set(nodes, graph=graph, **kwargs))


def _set_graph(engine: InferenceEngine, graph) -> None:
    engine._InferenceEngine__dependency_graph = graph


def test_small_fallback_helpers_and_deferred_question_state():
    assert _noop_question_callback(object()) is None
    assert _safe_float("1.5", 0.0) == 1.5
    assert _safe_float(object(), 0.25) == 0.25

    engine = InferenceEngine()
    assessment = MagicMock()
    engine.set_assessment(assessment)
    engine.defer_question("  ")
    assert engine.get_deferred_questions() == []
    engine.defer_question("  later question  ")
    assert engine.get_deferred_questions() == ["later question"]
    assessment.set_node_to_be_asked.assert_called_once_with(None)
    assessment.set_aux_node_to_be_asked.assert_called_once_with(None)


def test_deterministic_child_answer_fallbacks_and_answer_keys():
    engine = InferenceEngine()
    assert engine._has_deterministic_child_answer("missing") is False

    child = _node("child", variable="answer")
    engine.set_node_set(_node_set({"child": child}, graph=None))
    assert engine._has_deterministic_child_answer("missing") is False
    assert engine._has_deterministic_child_answer("child") is False
    engine.get_assessment_state().set_fact(
        "answer", FactValue("yes"), source=FactSource.ASSERTED
    )
    assert engine._has_deterministic_child_answer("child") is True


def test_question_name_and_declared_type_fallbacks():
    engine = InferenceEngine()
    assert engine.find_type_of_element_to_be_asked(None) == {}
    assert engine._question_name_for_node(None) is None

    unnamed = _node("node", variable="")
    unnamed.get_node_name.return_value = None
    assert engine._question_name_for_node(unnamed) is None
    unnamed.get_node_name.return_value = "node fallback"
    assert engine._question_name_for_node(unnamed) == "node fallback"
    assert engine._declared_value_type("missing") is None
    assert engine._declared_collection_field_type(7) is None

    comparison = _node("comparison", line_type=LineType.COMPARISON, variable="fallback")
    comparison.get_lhs.return_value = "lhs"
    assert engine._question_name_for_node(comparison) == "lhs"
    comparison.get_lhs.return_value = ""
    assert engine._question_name_for_node(comparison) == "fallback"

    declared = FactValue("value", FactValueType.DATE)
    types = {"record": {"fields": {"date": FactValueType.DATE}}}
    collections = {"items": {"fields": {"amount": FactValueType.DOUBLE}}}
    engine.set_node_set(
        _node_set(
            {},
            graph=None,
            inputs={"declared": declared},
            types=types,
            collections=collections,
        )
    )
    assert engine._declared_value_type("prefix  declared") == FactValueType.DATE
    assert engine._declared_collection_field_type("record.date") == FactValueType.DATE
    assert engine._declared_collection_field_type("row.amount") == FactValueType.DOUBLE
    assert engine._declared_collection_field_type("missing") is None


def test_question_and_node_value_type_inference_branches():
    engine = InferenceEngine()
    comparison = _node(
        "comparison",
        line_type=LineType.COMPARISON,
        variable="lhs",
        fact_value=FactValue("result", FactValueType.UNKNOWN),
    )
    rhs = FactValue(3, FactValueType.INTEGER)
    comparison.get_rhs.return_value = rhs
    assert engine._infer_question_value_type(comparison, "lhs") == FactValueType.INTEGER
    assert engine._infer_node_value_type(comparison) == FactValueType.BOOLEAN

    rhs = FactValue("declared", FactValueType.STRING)
    comparison.get_rhs.return_value = rhs
    engine.set_node_set(
        _node_set({}, graph=None, inputs={"declared": FactValue("", FactValueType.GUID)})
    )
    assert engine._infer_question_value_type(comparison, "lhs") == FactValueType.GUID

    plain = _node("plain", variable="answer", plain=True)
    assert engine._infer_question_value_type(plain, "answer") == FactValueType.BOOLEAN
    assert engine._infer_node_value_type(plain) == FactValueType.BOOLEAN

    typed = _node(
        "typed",
        variable="answer",
        fact_value=FactValue("x", FactValueType.URL),
    )
    assert engine._infer_question_value_type(typed, "answer") == FactValueType.URL
    assert engine._infer_node_value_type(typed) == FactValueType.URL
    typed.get_fact_value.return_value = object()
    assert engine._infer_question_value_type(typed, "answer") == FactValueType.UNKNOWN
    assert engine._infer_node_value_type(typed) == FactValueType.UNKNOWN


def test_goal_satisfaction_and_active_node_cleanup_paths():
    engine = InferenceEngine()
    assert engine._goal_fact_is_satisfied(None) is False
    assert engine._goal_fact_is_satisfied(FactValue(None)) is False
    assert engine._goal_fact_is_satisfied(FactValue(False)) is True

    assessment = MagicMock()
    assessment.get_node_to_be_asked.return_value = None
    assert engine._active_askable_node(assessment) is None
    assessment.set_aux_node_to_be_asked.assert_called_with(None)

    iterate = _node("iterate", line_type=LineType.ITERATE)
    aux = _node("aux")
    assessment.reset_mock()
    assessment.get_node_to_be_asked.return_value = iterate
    assessment.get_aux_node_to_be_asked.return_value = aux
    engine.get_assessment_state().set_fact(
        "iterate", FactValue(True), source=FactSource.ASSERTED
    )
    assert engine._active_askable_node(assessment) is None

    engine.get_assessment_state().remove_fact("iterate")
    engine.defer_question("iterate")
    assert engine._active_askable_node(assessment) is None

    fresh = InferenceEngine()
    assessment.get_node_to_be_asked.return_value = iterate
    assessment.get_aux_node_to_be_asked.return_value = None
    assert fresh._active_askable_node(assessment) is None
    assessment.get_aux_node_to_be_asked.return_value = aux
    fresh.get_assessment_state().set_fact(
        "aux", FactValue(True), source=FactSource.ASSERTED
    )
    assert fresh._active_askable_node(assessment) is None
    fresh.get_assessment_state().remove_fact("aux")
    fresh.defer_question("aux")
    assert fresh._active_askable_node(assessment) is None

    final = InferenceEngine()
    assessment.get_aux_node_to_be_asked.return_value = aux
    assert final._active_askable_node(assessment) is aux
    assessment.get_node_to_be_asked.return_value = aux
    assert final._active_askable_node(assessment) is aux
    assert final._node_answer_is_known(None) is False
    final.defer_question("aux")
    assert final._active_askable_node(assessment) is None
    final = InferenceEngine()
    assessment.get_node_to_be_asked.return_value = aux
    final.get_assessment_state().set_fact(
        "aux", FactValue(True), source=FactSource.ASSERTED
    )
    assert final._active_askable_node(assessment) is None


def test_question_flow_scan_and_reachability_fallbacks():
    engine = InferenceEngine()
    assessment = MagicMock()
    assessment.get_goal_node.return_value = None
    assert engine._question_flow_scan_nodes(assessment) == []
    assert engine._target_reachable_node_names("goal") == {"goal"}

    goal = _node("goal")
    reachable = _node("reachable")
    other = _node("other")
    graph = _graph(
        groups={"goal": [(DependencyType.get_and(), ("reachable",))]},
        children={"goal": ["reachable"]},
    )
    engine = _engine_with_graph(
        {"goal": goal, "reachable": reachable, "other": other},
        graph,
        sorted_nodes=[other, goal, reachable],
    )
    assessment.get_goal_node.return_value = goal
    assessment.get_goal_node_index.return_value = -1
    ordered = engine._question_flow_scan_nodes(assessment)
    assert [node.get_node_name() for _, node in ordered] == ["goal", "reachable", "other"]

    engine.get_node_set().get_sorted_node_list.return_value = [reachable, goal, other]
    assessment.get_goal_node_index.return_value = 1
    ordered = engine._question_flow_scan_nodes(assessment)
    assert [node.get_node_name() for _, node in ordered] == ["goal", "reachable", "other"]


def test_mandatory_retention_reverses_pruning_and_records_event():
    engine = InferenceEngine()
    state = engine.get_assessment_state()
    state.add_item_to_mandatory_list("required")
    engine._InferenceEngine__pruned_question_flow_nodes.add("required")

    engine._retain_mandatory_node_for_question_flow(
        "required",
        parent_name="parent",
        reason="required",
    )

    assert "required" in state.get_inclusive_list()
    assert "required" not in engine._InferenceEngine__pruned_question_flow_nodes
    assert engine.get_branch_prune_trace()[0]["action"] == "retained"


def _auto_answer_engine() -> tuple[InferenceEngine, MagicMock]:
    node = _node(
        "input node",
        variable="input",
        fact_value=FactValue("", FactValueType.BOOLEAN),
    )
    flags = FeatureFlags(
        ontology_advisory_enabled=True,
        ontology_auto_answer=True,
        ontology_auto_answer_confidence_threshold=0.8,
    )
    return InferenceEngine(feature_flags=flags), node


def _suggestion(**overrides):
    value = {
        "status": "available",
        "autoAnswerEligible": True,
        "suggestedValue": True,
        "confidence": 0.95,
        "ontologySnapshotHash": "hash",
        "ontologySnapshotRef": "snapshot",
        "relationship": "default",
        "basis": "test",
    }
    value.update(overrides)
    return value


def test_ontology_auto_answer_abstention_and_success_branches(monkeypatch):
    disabled = InferenceEngine()
    _, node = _auto_answer_engine()
    assert disabled._select_ontology_auto_answer(node, record_abstain=True) is None

    asserted, node = _auto_answer_engine()
    asserted.get_assessment_state().set_fact(
        "input", FactValue(False), source=FactSource.ASSERTED
    )
    assert asserted._select_ontology_auto_answer(node, record_abstain=True) is None
    assert asserted.get_ontology_auto_answer_trace()[-1]["reason"] == "asserted_fact_exists"

    inferred, node = _auto_answer_engine()
    inferred.get_assessment_state().set_fact(
        "input", FactValue(False), source=FactSource.INFERRED
    )
    assert inferred._select_ontology_auto_answer(node, record_abstain=True) is None
    assert inferred.get_ontology_auto_answer_trace()[-1]["reason"] == "deterministic_fact_exists"

    no_suggestion, node = _auto_answer_engine()
    assert no_suggestion._select_ontology_auto_answer(node, record_abstain=True) is None

    ambiguous, node = _auto_answer_engine()
    ambiguous.configure_ontology_auto_answer(
        {"input": [_suggestion(), _suggestion(suggestedValue=False)]},
        ontology_snapshot_hash="hash",
    )
    assert ambiguous._select_ontology_auto_answer(node, record_abstain=True) is None
    assert ambiguous.get_ontology_auto_answer_trace()[-1]["reason"] == (
        "ambiguous_or_contradictory_ontology_default"
    )

    stale, node = _auto_answer_engine()
    stale.configure_ontology_auto_answer(
        {"input": [_suggestion(ontologySnapshotHash="old")]},
        ontology_snapshot_hash="hash",
    )
    assert stale._select_ontology_auto_answer(node, record_abstain=True) is None
    assert stale.get_ontology_auto_answer_trace()[-1]["reason"] == (
        "stale_or_unversioned_ontology_snapshot"
    )

    low, node = _auto_answer_engine()
    low.configure_ontology_auto_answer(
        {"input": [_suggestion(confidence="invalid")]},
        ontology_snapshot_hash="hash",
    )
    assert low._select_ontology_auto_answer(node, record_abstain=True) is None
    assert low.get_ontology_auto_answer_trace()[-1]["reason"] == "below_confidence_threshold"

    invalid, node = _auto_answer_engine()
    invalid.configure_ontology_auto_answer(
        {"input": [_suggestion()]},
        ontology_snapshot_hash="hash",
    )
    monkeypatch.setattr(invalid, "_infer_question_value_type", lambda *_args: FactValueType.UNKNOWN)
    assert invalid._select_ontology_auto_answer(node, record_abstain=True) is None
    assert invalid.get_ontology_auto_answer_trace()[-1]["reason"] == "unparseable_default_value"

    successful, node = _auto_answer_engine()
    successful.configure_ontology_auto_answer(
        {"input": [_suggestion()]},
        ontology_snapshot_hash="hash",
    )
    selected = successful._select_ontology_auto_answer(node, record_abstain=True)
    assert selected[0] == "input"
    assert successful._ontology_default_fact_value_for_node(node).get_value() is True
    successful._record_ontology_auto_answer_event(
        node,
        "input",
        "auto_answered",
        suggestion=selected[2],
        fact_value=selected[1],
    )
    assert successful.get_ontology_auto_answer_trace()[-1]["factSource"] == "ASSERTED"
    assert successful._ontology_snapshot_matches({}) is False


def test_parent_dependency_and_question_strategy_branches(monkeypatch):
    child = _node("child")
    parent = _node("parent")
    dep = DependencyType.get_and() | DependencyType.get_mandatory()
    graph = _graph(
        parents={"child": {"parent"}},
        children={"parent": ["child"]},
        dep_types={("parent", "child"): dep},
    )
    engine = _engine_with_graph({"parent": parent, "child": child}, graph)
    engine.get_assessment_state().get_inclusive_list().append("parent")
    monkeypatch.setattr(engine, "_is_iterate_line_child", lambda _name: False)
    engine._process_parent_dependencies(child, MagicMock())
    assert engine.get_assessment_state().is_in_mandatory_list("child")

    engine = InferenceEngine()
    assessment = MagicMock()
    assessment.get_goal_node.return_value = parent
    assert engine._should_ask_node(child, assessment, 0) is False

    engine.set_node_set(_node_set({"child": child}, graph=None))
    engine.get_assessment_state().get_inclusive_list().append("child")
    engine.defer_question("child")
    assert engine._should_ask_node(child, assessment, 0) is False

    fresh = InferenceEngine(node_set=_node_set({"child": child}, graph=None))
    fresh.get_assessment_state().get_inclusive_list().append("child")
    fresh._InferenceEngine__pruned_question_flow_nodes.add("child")
    assert fresh._should_ask_node(child, assessment, 0) is False

    prune_blocked = InferenceEngine()
    prune_blocked.get_assessment_state().get_inclusive_list().append("child")
    monkeypatch.setattr(
        prune_blocked, "_prune_resolved_false_parent_branch", lambda _name: True
    )
    assert prune_blocked._should_ask_node(child, assessment, 0) is False

    strategy = MagicMock()
    strategy.select_next.return_value = child
    strategy_engine = InferenceEngine(question_strategy=strategy)
    monkeypatch.setattr(strategy_engine, "_askable_frontier_candidates", lambda: [])
    assert strategy_engine._select_question_strategy_frontier_candidate(child) is child
    strategy.select_next.assert_called_once()

    no_strategy = InferenceEngine()
    assert no_strategy._askable_frontier_candidates() == []
    monkeypatch.setattr(no_strategy, "_question_strategy_allows_ask", lambda *_a, **_k: False)
    assert no_strategy._select_question_strategy_frontier_candidate(child) is None


def test_frontier_candidate_filters_and_question_strategy(monkeypatch):
    valid = _node("valid")
    iterate = _node("iterate", line_type=LineType.ITERATE)
    outside = _node("outside")
    deferred = _node("deferred")
    pruned = _node("pruned")
    children = _node("children")
    pending = _node("pending")
    evaluable = _node("evaluable")
    rejected = _node("rejected")
    nodes = [valid, iterate, outside, deferred, pruned, children, pending, evaluable, rejected]
    engine = InferenceEngine(node_set=_node_set({n.get_node_name(): n for n in nodes}, graph=None))
    engine.get_assessment_state().set_inclusive_list(
        [n.get_node_name() for n in nodes if n is not outside]
    )
    engine.defer_question("deferred")
    engine._InferenceEngine__pruned_question_flow_nodes.add("pruned")
    monkeypatch.setattr(engine, "_has_children", lambda name: name == "children")
    monkeypatch.setattr(
        engine, "_has_pending_branch_discriminator", lambda name: name == "pending"
    )
    monkeypatch.setattr(
        engine, "_can_evaluate_without_mutation", lambda node: node is evaluable
    )
    resolver = MagicMock()
    resolver.find_next_question_node.side_effect = lambda node, *_args, **_kwargs: (
        None if node is rejected else node
    )
    engine._InferenceEngine__question_resolver = resolver

    assert engine._askable_frontier_candidates() == [valid]

    strategy = MagicMock()
    strategy.should_ask.return_value = True
    engine.set_question_strategy(strategy)
    assert engine._question_strategy_allows_ask(valid, has_children=False) is True


def test_can_evaluate_without_mutation_variants():
    engine = InferenceEngine()
    state = engine.get_assessment_state()
    plain = _node("plain", variable="answer", plain=True)
    assert engine._can_evaluate_without_mutation(plain) is False
    state.set_fact("answer", FactValue(True), source=FactSource.ASSERTED)
    assert engine._can_evaluate_without_mutation(plain) is True

    listed = _node("listed", variable="choice", fact_value=FactValue("options"))
    listed.get_tokens().get_tokens_list.return_value = ["IS IN LIST: "]
    state.set_fact("options", FactValue([]), source=FactSource.ASSERTED)
    state.set_fact("choice", FactValue("a"), source=FactSource.ASSERTED)
    assert engine._can_evaluate_without_mutation(listed) is True

    comparison = _node("comparison", line_type=LineType.COMPARISON)
    comparison.get_lhs.return_value = "lhs"
    comparison.get_rhs.return_value = FactValue(2, FactValueType.INTEGER)
    assert engine._can_evaluate_without_mutation(comparison) is False
    state.set_fact("lhs", FactValue(2), source=FactSource.ASSERTED)
    assert engine._can_evaluate_without_mutation(comparison) is True
    comparison.get_rhs.return_value = FactValue("rhs", FactValueType.STRING)
    assert engine._can_evaluate_without_mutation(comparison) is False
    state.set_fact("rhs", FactValue(2), source=FactSource.ASSERTED)
    assert engine._can_evaluate_without_mutation(comparison) is True
    assert engine._can_evaluate_without_mutation(_node("expr", line_type=LineType.EXPR_CONCLUSION)) is False


def test_prune_resolution_pending_discriminator_and_or_ancestors(monkeypatch):
    engine = InferenceEngine()
    assert engine._prune_resolved_false_parent_branch("child") is False
    assert engine._has_pending_branch_discriminator("child") is False
    assert engine._or_branch_ancestors("child") == set()

    parent = _node("parent")
    child = _node("child", line_type=LineType.COMPARISON, variable="child question")
    sibling = _node("sibling", line_type=LineType.COMPARISON, variable="branch selector")
    root = _node("root")
    graph = _graph(
        parents={"child": {"parent"}, "sibling": {"parent"}, "parent": {"root"}},
        children={"parent": ["child", "sibling"], "root": ["parent"]},
        dep_types={("root", "parent"): DependencyType.get_or()},
    )
    engine = _engine_with_graph(
        {"root": root, "parent": parent, "child": child, "sibling": sibling}, graph
    )
    assert engine._or_branch_ancestors("child") == {"parent"}
    assert engine._has_pending_branch_discriminator("child") is True
    engine.get_assessment_state().set_fact(
        "parent", FactValue(True), source=FactSource.ASSERTED
    )
    assert engine._has_pending_branch_discriminator("child") is False

    engine.get_assessment_state().remove_fact("parent")
    engine._InferenceEngine__pruned_question_flow_nodes.add("parent")
    monkeypatch.setattr(engine, "_prune_question_flow_subtree", MagicMock())
    assert engine._prune_resolved_false_parent_branch("child") is False
    engine._InferenceEngine__pruned_question_flow_nodes.add("child")
    assert engine._prune_resolved_false_parent_branch("child", {"child"}) is True

    engine._InferenceEngine__pruned_question_flow_nodes.add("sibling")
    engine.get_assessment_state().remove_fact("parent")
    assert engine._has_pending_branch_discriminator("child") is False


def test_iterate_handler_missing_and_self_evaluation_paths():
    engine = InferenceEngine()
    iterate = _node("iterate", line_type=LineType.ITERATE)
    assessment = MagicMock()
    assert engine._handle_iterate_node(iterate, assessment, 1) is False

    engine.set_node_set(_node_set({"iterate": iterate}, graph=None))
    del iterate.get_iterate_next_question
    assert engine._handle_iterate_node(iterate, assessment, 1) is False

    iterate.get_iterate_next_question = MagicMock(return_value=None)
    iterate.can_be_self_evaluated.return_value = True
    iterate.self_evaluate.return_value = None
    assert engine._handle_iterate_node(iterate, assessment, 1) is False
    iterate.self_evaluate.return_value = FactValue(True)
    assert engine._handle_iterate_node(iterate, assessment, 1) is False
    assert engine.get_assessment_state().get_working_memory()["iterate"].get_value() is True


def test_edit_answer_non_summary_and_materialization_branches(monkeypatch):
    engine = InferenceEngine()
    with pytest.raises(ValueError):
        engine.edit_answer("")
    engine.get_assessment_state().set_fact(
        "answer", FactValue("yes"), source=FactSource.ASSERTED
    )
    engine.get_assessment_state().set_summary_list(["other"])
    assessment = MagicMock()
    engine.set_assessment(assessment)
    engine.edit_answer("answer")
    assert "answer" not in engine.get_assessment_state().get_working_memory()

    fact = FactValue("value")
    engine._materialize_ontology_derivations("source", fact)
    reasoning = InferenceEngine(feature_flags=FeatureFlags(ontology_reasoning=True))
    reasoning._materialize_ontology_derivations("source", fact)

    derived_asserted = SimpleNamespace(fact_name="asserted", fact_value=FactValue(True))
    derived_new = SimpleNamespace(fact_name="derived", fact_value=FactValue(True))
    result = SimpleNamespace(
        trace=[{"action": "derived"}],
        derived_facts=[derived_asserted, derived_new, derived_new],
    )
    reasoner = MagicMock()
    reasoner.materialize.return_value = result
    reasoning._InferenceEngine__ontology_reasoner = reasoner
    reasoning._InferenceEngine__ontology_index = object()
    reasoning.get_assessment_state().set_fact(
        "asserted", FactValue(False), source=FactSource.ASSERTED
    )
    monkeypatch.setattr(reasoning, "_propagate_inferred_truth_from", MagicMock())
    reasoning._materialize_ontology_derivations("source", fact)
    assert reasoning.get_ontology_derived_facts() == ["derived"]
    assert reasoning.get_ontology_materialization_trace() == [{"action": "derived"}]


def test_propagation_and_parent_truth_boundaries(monkeypatch):
    engine = InferenceEngine()
    engine._propagate_inferred_truth_from("child")
    assert engine._compute_parent_truth_from_children("parent") is None

    graph = _graph(parents={"child": {"parent"}})
    _set_graph(engine, graph)
    monkeypatch.setattr(engine, "_compute_parent_truth_from_children", lambda _name: None)
    engine._propagate_inferred_truth_from("child")
    engine._propagate_inferred_truth_from("child", {"child"})

    false_value = FactValue(False, FactValueType.BOOLEAN)
    monkeypatch.setattr(engine, "_compute_parent_truth_from_children", lambda _name: false_value)
    monkeypatch.setattr(engine, "_can_prune_false_parent_question_flow", lambda _name: True)
    prune_false = MagicMock()
    monkeypatch.setattr(engine, "_prune_children_skipped_by_false_parent", prune_false)
    engine._propagate_inferred_truth_from("child")
    prune_false.assert_called_once_with("parent")

    true_value = FactValue(True, FactValueType.BOOLEAN)
    monkeypatch.setattr(engine, "_compute_parent_truth_from_children", lambda _name: true_value)
    prune_true = MagicMock()
    monkeypatch.setattr(engine, "_prune_or_siblings_skipped_by_true_parent", prune_true)
    engine._propagate_inferred_truth_from("child")
    prune_true.assert_called_with("parent")


@pytest.mark.parametrize(
    ("groups", "truths", "expected"),
    [
        ([(DependencyType.get_and(), ())], [], None),
        ([(DependencyType.get_and(), ("a", "b"))], [False, None], False),
        ([(DependencyType.get_and(), ("a", "b"))], [True, None], None),
        (
            [(DependencyType.get_optional() | DependencyType.get_and(), ("a",))],
            [None],
            None,
        ),
        ([(DependencyType.get_or(), ("a", "b"))], [False, False], False),
        ([(DependencyType.get_or(), ("a", "b"))], [True, None], True),
        ([(DependencyType.get_or(), ("a", "b"))], [False, None], None),
        (
            [(DependencyType.get_optional() | DependencyType.get_or(), ("a",))],
            [None],
            None,
        ),
        ([(DependencyType.get_optional(), ("a",))], [None], None),
        ([(0, ("a",)), (0, ("b",))], [False, None], None),
        ([(0, ("a",))], [True], True),
        ([(0, ("a",))], [None], None),
    ],
)
def test_compute_parent_truth_group_variants(monkeypatch, groups, truths, expected):
    engine = InferenceEngine()
    _set_graph(engine, _graph(groups={"parent": groups}))
    monkeypatch.setattr(engine, "_dependency_child_truth", MagicMock(side_effect=truths))
    result = engine._compute_parent_truth_from_children("parent")
    assert (None if result is None else result.get_value()) is expected
    assert engine._compute_parent_truth_from_children("parent", {"parent"}) is None


def test_dependency_child_truth_known_not_and_nested_paths(monkeypatch):
    engine = InferenceEngine()
    graph = _graph(children={"child": []})
    _set_graph(engine, graph)
    monkeypatch.setattr(engine, "_evaluate_known_leaf_node", MagicMock())
    monkeypatch.setattr(engine, "_known_dependency_should_wait_for_input", lambda _name: True)
    assert engine._dependency_child_truth(DependencyType.get_known(), "child") is None

    monkeypatch.setattr(engine, "_known_dependency_should_wait_for_input", lambda _name: False)
    monkeypatch.setattr(engine, "_or_branch_ancestors", lambda _name: {"branch"})
    assert engine._dependency_child_truth(DependencyType.get_known(), "child") is None
    monkeypatch.setattr(engine, "_or_branch_ancestors", lambda _name: set())
    assert engine._dependency_child_truth(DependencyType.get_known(), "child") is False
    assert engine._dependency_child_truth(
        DependencyType.get_known() | DependencyType.get_not(), "child"
    ) is True
    assert engine._dependency_child_truth(DependencyType.get_and(), "child") is None

    engine.get_assessment_state().set_fact(
        "child", FactValue(True), source=FactSource.ASSERTED
    )
    assert engine._dependency_child_truth(DependencyType.get_not(), "child") is False


def test_known_dependency_and_known_leaf_validation(monkeypatch):
    engine = InferenceEngine()
    assert engine._known_dependency_should_wait_for_input("child") is False
    engine._evaluate_known_leaf_node("child")
    engine.set_node_set(_node_set({}, graph=None))
    engine.get_node_set().get_input_dictionary.side_effect = RuntimeError("bad")
    assert engine._known_dependency_should_wait_for_input("child") is False
    engine.get_node_set().get_input_dictionary.side_effect = None
    engine.get_node_set().get_input_dictionary.return_value = []
    assert engine._known_dependency_should_wait_for_input("child") is False
    engine.get_node_set().get_input_dictionary.return_value = {"answer": object()}
    assert engine._known_dependency_should_wait_for_input("answer") is True
    assert engine._known_dependency_should_wait_for_input("prefix  answer") is True

    graph = _graph(children={"known": [], "parent": ["child"]})
    node = _node("known", line_type=LineType.COMPARISON)
    engine = _engine_with_graph({"known": node}, graph)
    monkeypatch.setattr(engine, "_can_evaluate_without_mutation", lambda _node: False)
    engine._evaluate_known_leaf_node("missing")
    engine._evaluate_known_leaf_node("parent")
    engine._evaluate_known_leaf_node("known")
    monkeypatch.setattr(engine, "_can_evaluate_without_mutation", lambda _node: True)
    node.self_evaluate.return_value = None
    engine._evaluate_known_leaf_node("known")
    node.self_evaluate.return_value = FactValue(True)
    engine._evaluate_known_leaf_node("known")
    assert engine.get_assessment_state().get_working_memory()["known"].get_value() is True

    conclusion = _node("conclusion", plain=True, variable="answer")
    engine._InferenceEngine__node_set.get_node_dictionary.return_value["conclusion"] = conclusion
    graph.get_children_flat.side_effect = lambda name: []

    def determine_and_store(_node):
        engine.get_assessment_state().set_fact(
            "conclusion", FactValue(True), source=FactSource.INFERRED
        )
        return True

    monkeypatch.setattr(engine, "_can_evaluate", determine_and_store)
    engine._evaluate_known_leaf_node("conclusion")
    assert "conclusion" in engine.get_assessment_state().get_summary_list()


def test_back_propagation_and_leaf_evaluation_boundaries(monkeypatch):
    engine = InferenceEngine()
    engine._back_propagating(0)
    node = _node("node")
    graph = _graph()
    engine = _engine_with_graph({"node": node}, graph, sorted_nodes=[node])
    process = MagicMock()
    evaluate = MagicMock()
    monkeypatch.setattr(engine, "_process_node_dependencies", process)
    monkeypatch.setattr(engine, "_evaluate_node_after_propagation", evaluate)
    engine._back_propagating(0)
    process.assert_called_once_with(node)
    evaluate.assert_called_once()

    leaf = _node("leaf", variable="input")
    engine.get_assessment_state().set_fact(
        "input", FactValue("yes"), source=FactSource.ASSERTED
    )
    leaf.self_evaluate.return_value = FactValue(True)
    engine._evaluate_leaf_node(leaf, LineType.VALUE_CONCLUSION)
    assert "leaf" in engine.get_assessment_state().get_working_memory()

    comparison = _node("comparison", line_type=LineType.COMPARISON)
    comparison.get_lhs.return_value = "lhs"
    comparison.get_rhs.return_value = FactValue(1, FactValueType.INTEGER)
    comparison.self_evaluate.return_value = FactValue(True)
    engine.get_assessment_state().set_fact("lhs", FactValue(1), source=FactSource.ASSERTED)
    engine._evaluate_leaf_node(comparison, LineType.COMPARISON)
    assert "comparison" in engine.get_assessment_state().get_working_memory()


def test_variable_listing_has_children_and_child_inclusion(monkeypatch):
    engine = InferenceEngine()
    assert engine.get_list_of_variable_name_and_value_of_nodes() == []
    assert engine._has_children("missing") is False

    leaf = _node("leaf", variable="variable", fact_value=FactValue("literal"))
    parent = _node("parent")
    child = _node("child")
    graph = _graph(children={"leaf": [], "parent": ["child"], "child": []})
    engine = _engine_with_graph({"leaf": leaf, "parent": parent, "child": child}, graph)
    assert engine.get_list_of_variable_name_and_value_of_nodes() == [
        "variable",
        "literal",
        "child",
        "value",
    ]

    engine._InferenceEngine__pruned_question_flow_nodes.add("parent")
    assert engine._has_children("parent") is False
    engine._InferenceEngine__pruned_question_flow_nodes.clear()
    engine.get_assessment_state().set_fact(
        "parent", FactValue(False), source=FactSource.ASSERTED
    )
    assert engine._has_children("parent") is True
    engine.get_assessment_state().remove_fact("parent")
    monkeypatch.setattr(engine, "_can_determine", lambda *_args: False)
    assert engine._has_children("parent") is True

    engine.get_assessment_state().add_item_to_mandatory_list("parent")
    engine._InferenceEngine__pruned_question_flow_nodes.add("child")
    engine._add_child_rule_into_inclusive_list(parent)
    assert "child" not in engine._InferenceEngine__pruned_question_flow_nodes


def test_iterate_ancestor_and_can_evaluate_variants():
    iterate = _node("iterate", line_type=LineType.ITERATE)
    child = _node("child")
    graph = _graph(parents={"child": {"iterate"}})
    engine = _engine_with_graph({"iterate": iterate, "child": child}, graph)
    assert engine._is_iterate_line_child("child") is True
    engine.get_assessment_state().add_item_to_mandatory_list("orphan")
    assert engine._is_iterate_line_child("orphan") is False
    assert "orphan" not in engine.get_assessment_state().get_mandatory_list()

    plain = _node("plain", variable="input", plain=True)
    engine.get_assessment_state().set_fact(
        "input", FactValue(True), source=FactSource.ASSERTED
    )
    assert engine._can_evaluate(plain) is True

    listed = _node("listed", variable="choice", fact_value=FactValue("options"))
    listed.get_tokens().get_tokens_list.return_value = ["IS IN LIST: "]
    listed.self_evaluate.return_value = FactValue(True)
    engine.get_assessment_state().set_fact("options", FactValue([]), source=FactSource.ASSERTED)
    engine.get_assessment_state().set_fact("choice", FactValue("a"), source=FactSource.ASSERTED)
    assert engine._can_evaluate(listed) is True

    comparison = _node("comparison", line_type=LineType.COMPARISON)
    comparison.get_lhs.return_value = "lhs"
    comparison.get_rhs.return_value = FactValue(2, FactValueType.INTEGER)
    comparison.self_evaluate.return_value = FactValue(True)
    engine.get_assessment_state().set_fact("lhs", FactValue(2), source=FactSource.ASSERTED)
    assert engine._can_evaluate(comparison) is True
    comparison.get_rhs.return_value = FactValue("rhs", FactValueType.STRING)
    engine.get_assessment_state().set_fact("rhs", FactValue(2), source=FactSource.ASSERTED)
    engine.get_assessment_state().remove_fact("comparison")
    assert engine._can_evaluate(comparison) is True


def test_comparison_dependency_readiness_variants(monkeypatch):
    engine = InferenceEngine()
    assert engine._comparison_dependencies_ready("parent") is False

    groups = {
        "parent": [
            (DependencyType.get_known(), ("known",)),
            (DependencyType.get_optional() | DependencyType.get_or(), ("optional",)),
        ]
    }
    _set_graph(engine, _graph(groups=groups))
    assert engine._comparison_dependencies_ready("parent") is True

    _set_graph(
        engine,
        _graph(groups={"parent": [(DependencyType.get_or(), ("a", "b"))]}),
    )
    monkeypatch.setattr(engine, "_has_deterministic_child_answer", lambda _name: False)
    assert engine._comparison_dependencies_ready("parent") is False
    monkeypatch.setattr(engine, "_has_deterministic_child_answer", lambda name: name == "a")
    assert engine._comparison_dependencies_ready("parent") is True

    _set_graph(engine, _graph(groups={"parent": [(DependencyType.get_and(), ("a", "b"))]}))
    assert engine._comparison_dependencies_ready("parent") is False
    _set_graph(engine, _graph(groups={"parent": [(DependencyType.get_and(), ())]}))
    assert engine._comparison_dependencies_ready("parent") is False
    _set_graph(
        engine,
        _graph(
            groups={
                "parent": [
                    (DependencyType.get_optional() | DependencyType.get_and(), ("a", "b"))
                ]
            }
        ),
    )
    monkeypatch.setattr(engine, "_has_deterministic_child_answer", lambda _name: False)
    assert engine._comparison_dependencies_ready("parent") is False


def test_can_determine_comparison_false_and_unknown_line(monkeypatch):
    node = _node("parent", line_type=LineType.COMPARISON)
    graph = _graph(groups={"parent": [(DependencyType.get_and(), ("child",))]})
    engine = _engine_with_graph({"parent": node}, graph)
    monkeypatch.setattr(engine, "_comparison_dependencies_ready", lambda _name: False)
    assert engine._can_determine(node, LineType.COMPARISON) is False
    monkeypatch.setattr(engine, "_comparison_dependencies_ready", lambda _name: True)
    node.self_evaluate.return_value = None
    assert engine._can_determine(node, LineType.COMPARISON) is False
    node.self_evaluate.return_value = FactValue(False)
    prune = MagicMock()
    monkeypatch.setattr(engine, "_prune_children_skipped_by_false_parent", prune)
    assert engine._can_determine(node, LineType.COMPARISON) is True
    prune.assert_called_once_with("parent")
    node.self_evaluate.return_value = FactValue(True)
    prune_true = MagicMock()
    monkeypatch.setattr(engine, "_prune_or_siblings_skipped_by_true_parent", prune_true)
    assert engine._can_determine(node, LineType.COMPARISON) is True
    prune_true.assert_called_once_with("parent")
    assert engine._can_determine(node, LineType.EXPR_CONCLUSION) is False

    empty = _node("empty")
    empty_engine = _engine_with_graph({"empty": empty}, _graph())
    assert empty_engine._can_determine(empty, LineType.VALUE_CONCLUSION) is False


def test_pruning_helpers_cover_empty_optional_possible_and_duplicates(monkeypatch):
    engine = InferenceEngine()
    engine._prune_or_siblings_skipped_by_true_parent("parent")
    engine._prune_children_skipped_by_false_parent("parent")
    engine._prune_question_flow_subtree(
        "child", parent_name="parent", reason="test"
    )
    assert engine._false_parent_prune_reason("parent") == "and_parent_failed"
    assert engine._prune_reason_for_dependency(
        "parent", "child", default_reason="default"
    ) == "default"
    assert engine._related_prunable_node_names("child") == []
    assert engine._has_non_false_alternate_parent("child", "parent") is False

    graph = _graph(
        groups={
            "parent": [
                (DependencyType.get_and(), ("ignored",)),
                (DependencyType.get_or(), ("true", "pending", "pending")),
            ]
        },
        parents={"branch": {"root"}, "child": {"parent", "alternate"}},
        dep_types={
            ("root", "branch"): DependencyType.get_or(),
            ("parent", "optional"): DependencyType.get_optional(),
            ("parent", "possible"): DependencyType.get_possible(),
        },
    )
    engine._InferenceEngine__dependency_graph = graph
    monkeypatch.setattr(
        engine,
        "_dependency_child_truth",
        lambda _dep, name: True if name == "true" else None,
    )
    prune = MagicMock()
    monkeypatch.setattr(engine, "_prune_question_flow_subtree", prune)
    engine._prune_or_siblings_skipped_by_true_parent("parent")
    assert prune.call_count == 1
    monkeypatch.setattr(engine, "_dependency_child_truth", lambda *_args: False)
    engine._prune_or_siblings_skipped_by_true_parent("parent")
    assert engine._false_parent_prune_reason("branch") == "parent_branch_false"
    assert engine._prune_reason_for_dependency(
        "parent", "optional", default_reason="default"
    ) == "optional_dependency_pruned"
    assert engine._prune_reason_for_dependency(
        "parent", "possible", default_reason="default"
    ) == "possible_dependency_pruned"

    child = _node("child", variable="shared")
    related = _node("related", variable="child")
    engine._InferenceEngine__node_set = _node_set(
        {"child": child, "related": related}, graph=graph
    )
    assert engine._related_prunable_node_names("missing") == []
    assert engine._related_prunable_node_names("child") == ["related"]

    engine._InferenceEngine__pruned_question_flow_nodes.add("alternate")
    assert engine._has_non_false_alternate_parent("child", "parent") is False
    engine._InferenceEngine__pruned_question_flow_nodes.clear()
    assert engine._has_non_false_alternate_parent("child", "parent") is True
    engine.get_assessment_state().set_fact(
        "alternate", FactValue(False), source=FactSource.ASSERTED
    )
    assert engine._has_non_false_alternate_parent("child", "parent") is False


def test_remaining_dependency_and_pruning_paths(monkeypatch):
    parent = _node("parent")
    child = _node("child")
    grand = _node("grand")
    mandatory_dep = DependencyType.get_and() | DependencyType.get_mandatory()
    graph = _graph(
        parents={"child": {"parent"}, "parent": {"grand"}},
        children={"parent": ["child"], "grand": ["parent"], "child": []},
        dep_types={("parent", "child"): mandatory_dep},
    )
    engine = _engine_with_graph(
        {"grand": grand, "parent": parent, "child": child}, graph
    )
    engine.get_assessment_state().get_inclusive_list().append("parent")
    monkeypatch.setattr(engine, "_is_iterate_line_child", lambda _name: False)
    engine._process_node_dependencies(child)
    assert engine.get_assessment_state().is_in_mandatory_list("child")
    assert InferenceEngine()._is_comparison_node("child") is False
    assert engine._is_comparison_node(3) is False

    cycle_graph = _graph(parents={"child": {"parent"}, "parent": {"child"}})
    cycle_engine = _engine_with_graph({"child": child, "parent": parent}, cycle_graph)
    assert cycle_engine._is_iterate_line_child("child") is False

    engine._InferenceEngine__pruned_question_flow_nodes.add("grand")

    def mark_parent_and_child(*_args, **_kwargs):
        engine._InferenceEngine__pruned_question_flow_nodes.update({"parent", "child"})

    monkeypatch.setattr(engine, "_prune_question_flow_subtree", mark_parent_and_child)
    assert engine._prune_resolved_false_parent_branch("child") is True

    false_engine = _engine_with_graph({"parent": parent, "child": child}, graph)
    false_engine.get_assessment_state().set_fact(
        "parent", FactValue(False), source=FactSource.ASSERTED
    )

    def mark_child(_parent):
        false_engine._InferenceEngine__pruned_question_flow_nodes.add("child")

    monkeypatch.setattr(
        false_engine, "_prune_children_skipped_by_false_parent", mark_child
    )
    assert false_engine._prune_resolved_false_parent_branch("child") is True

    subtree_engine = _engine_with_graph({"child": child}, _graph(children={"child": []}))
    subtree_engine._prune_question_flow_subtree(
        "child", parent_name="parent", reason="test", visited={"child"}
    )
    related = _node("related", variable="child")
    subtree_engine._InferenceEngine__node_set.get_node_dictionary.return_value[
        "related"
    ] = related
    subtree_engine.get_assessment_state().set_inclusive_list(["child", "related"])
    subtree_engine._prune_question_flow_subtree(
        "child", parent_name="parent", reason="test"
    )
    assert "related" in subtree_engine._InferenceEngine__pruned_question_flow_nodes

    mandatory_engine = InferenceEngine()
    mandatory_engine.get_assessment_state().add_item_to_mandatory_list("required")
    mandatory_engine._prune_question_flow_node(
        "required", parent_name="parent", reason="test"
    )
    assert "required" in mandatory_engine.get_assessment_state().get_inclusive_list()


def test_question_flow_removal_records_active_and_aux_nodes():
    engine = InferenceEngine()
    node = _node("remove")
    assessment = MagicMock()
    assessment.get_node_to_be_asked.return_value = node
    assessment.get_aux_node_to_be_asked.return_value = node
    engine.set_assessment(assessment)
    state = engine.get_assessment_state()
    state.set_inclusive_list(["remove"])
    state.set_mandatory_list(["remove"])

    removed = engine._remove_from_question_flow("remove")

    assert removed == ["inclusive_list", "mandatory_list", "active_node", "aux_node"]
    engine._record_question_flow_event(
        "remove",
        parent_name="parent",
        action="pruned",
        reason="test",
        removed_from=removed,
    )
    engine._record_question_flow_event(
        "remove",
        parent_name="parent",
        action="pruned",
        reason="test",
        removed_from=removed,
    )
    assert len(engine.get_branch_prune_trace()) == 1
