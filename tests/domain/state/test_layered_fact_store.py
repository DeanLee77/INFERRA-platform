import time

import pytest

from src.domain.fact_values import FactValue
from src.domain.state import FactSource, LayeredFactStore


@pytest.fixture
def store() -> LayeredFactStore:
    return LayeredFactStore()


def test_set_fact_defaults_to_asserted_layer(store):
    store.set_fact("k", FactValue(1))

    assert store.get_fact_sources("k") == {FactSource.ASSERTED}


def test_unified_view_precedence_asserted_over_inferred_over_semantic(store):
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)
    store.set_fact("k", FactValue("H"), FactSource.HYPOTHETICAL)
    store.set_fact("k", FactValue("L"), FactSource.LEARNED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    assert store.get_unified_view()["k"].get_value() == "A"


def test_phase5_layer_precedence_without_asserted_or_inferred(store):
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)
    store.set_fact("k", FactValue("H"), FactSource.HYPOTHETICAL)
    store.set_fact("k", FactValue("L"), FactSource.LEARNED)

    assert store.get_unified_view()["k"].get_value() == "L"


def test_unified_view_returns_fresh_copy(store):
    store.set_fact("k", FactValue(1))

    snapshot = store.get_unified_view()
    snapshot["ghost"] = FactValue("x")

    assert "ghost" not in store.get_unified_view()


def test_get_layer_snapshot_returns_copy(store):
    store.set_fact("k", FactValue(1), FactSource.INFERRED)

    snap = store.get_layer_snapshot(FactSource.INFERRED)
    snap["mutated"] = FactValue("x")

    assert "mutated" not in store.get_layer_snapshot(FactSource.INFERRED)


def test_peek_in_layer_returns_value_only_for_that_layer(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)

    assert store.peek_in_layer("k", FactSource.ASSERTED).get_value() == "A"
    assert store.peek_in_layer("k", FactSource.INFERRED).get_value() == "I"
    assert store.peek_in_layer("k", FactSource.SEMANTIC) is None


def test_remove_fact_targets_specific_layer(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)

    store.remove_fact("k", FactSource.ASSERTED)

    assert store.get_fact_sources("k") == {FactSource.INFERRED}


def test_remove_fact_without_source_clears_all_layers(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("L"), FactSource.LEARNED)
    store.set_fact("k", FactValue("H"), FactSource.HYPOTHETICAL)
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)

    store.remove_fact("k")

    assert store.get_fact_sources("k") == set()


def test_invalidate_layer_clears_only_that_layer(store):
    store.set_fact("a", FactValue(1), FactSource.ASSERTED)
    store.set_fact("b", FactValue(2), FactSource.INFERRED)
    store.set_fact("c", FactValue(3), FactSource.SEMANTIC)
    store.set_fact("h", FactValue(4), FactSource.HYPOTHETICAL)

    store.invalidate_layer(FactSource.INFERRED)

    assert store.get_fact_sources("a") == {FactSource.ASSERTED}
    assert store.get_fact_sources("b") == set()
    assert store.get_fact_sources("c") == {FactSource.SEMANTIC}
    assert store.get_fact_sources("h") == {FactSource.HYPOTHETICAL}


def test_invalidate_hypotheses_clears_only_hypothetical_layer(store):
    store.set_fact("h", FactValue("hypothesis"), FactSource.HYPOTHETICAL)
    store.set_fact("l", FactValue("learned"), FactSource.LEARNED)

    store.invalidate_hypotheses()

    assert store.get_fact_sources("h") == set()
    assert store.get_fact_sources("l") == {FactSource.LEARNED}


# --- Truth-maintenance / override-tracking hook ---

def test_asserted_overriding_inferred_records_override(store):
    store.set_fact("decision", FactValue("rule-engine"), FactSource.INFERRED)
    store.set_fact("decision", FactValue("user-input"), FactSource.ASSERTED)

    assert "decision" in store.get_overrides()


def test_asserted_overriding_hypothetical_records_override(store):
    store.set_fact("decision", FactValue("maybe"), FactSource.HYPOTHETICAL)
    store.set_fact("decision", FactValue("user-input"), FactSource.ASSERTED)

    assert "decision" in store.get_overrides()


def test_setting_asserted_with_no_inferred_does_not_record_override(store):
    store.set_fact("greenfield", FactValue("user-input"), FactSource.ASSERTED)

    assert "greenfield" not in store.get_overrides()


def test_invalidating_inferred_clears_override_set(store):
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    assert "k" in store.get_overrides()

    store.invalidate_layer(FactSource.INFERRED)

    assert store.get_overrides() == set()


def test_removing_asserted_drops_override(store):
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    store.remove_fact("k", FactSource.ASSERTED)

    assert "k" not in store.get_overrides()


def test_get_overrides_returns_copy(store):
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    snapshot = store.get_overrides()
    snapshot.add("ghost")

    assert "ghost" not in store.get_overrides()


# --- Timestamp-based change tracking ---

def test_get_changed_since_returns_only_recent_keys(store):
    store.set_fact("old", FactValue(1))
    cutoff = time.time()
    time.sleep(0.01)
    store.set_fact("new", FactValue(2))

    changed = store.get_changed_since(cutoff)

    assert "new" in changed
    assert "old" not in changed


def test_get_changed_since_zero_returns_everything(store):
    store.set_fact("a", FactValue(1))
    store.set_fact("b", FactValue(2))

    assert store.get_changed_since(0.0) == {"a", "b"}
