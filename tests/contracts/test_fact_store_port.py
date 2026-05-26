"""
FactStorePort contract test suite.

Parametrised over every concrete implementation of FactStorePort.
Any new implementation must pass every test in this file — this is the
behavioural contract that guarantees interchangeability across the port.

Add new implementations to the ``implementations`` fixture below.
"""

import time
from typing import Type

import pytest

from src.domain.fact_values import FactValue
from src.domain.state import FactSource, LayeredFactStore
from src.ports.fact_store_port import FactStorePort


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

IMPLEMENTATIONS: list[Type[FactStorePort]] = [
    LayeredFactStore,
    # Future implementations (e.g. RedisFactStore, ShadowFactStore) go here.
]


@pytest.fixture(params=IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def store(request) -> FactStorePort:
    """Provide a fresh FactStorePort implementation for each test."""
    return request.param()


# ===================================================================
# 1. set_fact — default source & explicit source
# ===================================================================


def test_set_fact_defaults_to_asserted_layer(store):
    store.set_fact("k", FactValue(1))

    assert store.get_fact_sources("k") == {FactSource.ASSERTED}


def test_set_fact_writes_to_explicit_inferred_layer(store):
    store.set_fact("k", FactValue(2), FactSource.INFERRED)

    assert store.get_fact_sources("k") == {FactSource.INFERRED}


def test_set_fact_writes_to_explicit_semantic_layer(store):
    store.set_fact("k", FactValue(3), FactSource.SEMANTIC)

    assert store.get_fact_sources("k") == {FactSource.SEMANTIC}


def test_set_fact_same_key_in_multiple_layers(store):
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    assert store.get_fact_sources("k") == {
        FactSource.ASSERTED,
        FactSource.INFERRED,
        FactSource.SEMANTIC,
    }


# ===================================================================
# 2. get_unified_view — precedence & isolation
# ===================================================================


def test_unified_view_merges_all_layers(store):
    store.set_fact("a", FactValue(1), FactSource.ASSERTED)
    store.set_fact("b", FactValue(2), FactSource.INFERRED)
    store.set_fact("c", FactValue(3), FactSource.SEMANTIC)

    unified = store.get_unified_view()

    assert set(unified.keys()) == {"a", "b", "c"}


def test_unified_view_precedence_asserted_over_inferred_over_semantic(store):
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    assert store.get_unified_view()["k"].get_value() == "A"


def test_unified_view_precedence_inferred_over_semantic(store):
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)

    assert store.get_unified_view()["k"].get_value() == "I"


def test_unified_view_asserted_alone(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    assert store.get_unified_view()["k"].get_value() == "A"


def test_unified_view_returns_fresh_copy(store):
    store.set_fact("k", FactValue(1))

    snapshot = store.get_unified_view()
    snapshot["ghost"] = FactValue("x")

    assert "ghost" not in store.get_unified_view()


def test_unified_view_empty_store(store):
    assert store.get_unified_view() == {}


# ===================================================================
# 3. get_layer_snapshot — single-layer copy
# ===================================================================


def test_get_layer_snapshot_returns_only_that_layer(store):
    store.set_fact("a", FactValue(1), FactSource.ASSERTED)
    store.set_fact("b", FactValue(2), FactSource.INFERRED)

    inferred_snap = store.get_layer_snapshot(FactSource.INFERRED)

    assert "b" in inferred_snap
    assert "a" not in inferred_snap


def test_get_layer_snapshot_returns_copy(store):
    store.set_fact("k", FactValue(1), FactSource.INFERRED)

    snap = store.get_layer_snapshot(FactSource.INFERRED)
    snap["mutated"] = FactValue("x")

    assert "mutated" not in store.get_layer_snapshot(FactSource.INFERRED)


def test_get_layer_snapshot_empty_layer(store):
    assert store.get_layer_snapshot(FactSource.SEMANTIC) == {}


# ===================================================================
# 4. peek_in_layer — targeted lookup without copy
# ===================================================================


def test_peek_in_layer_returns_value_in_correct_layer(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)

    assert store.peek_in_layer("k", FactSource.ASSERTED).get_value() == "A"
    assert store.peek_in_layer("k", FactSource.INFERRED).get_value() == "I"


def test_peek_in_layer_returns_none_when_absent(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    assert store.peek_in_layer("k", FactSource.INFERRED) is None


def test_peek_in_layer_nonexistent_key(store):
    assert store.peek_in_layer("no_such_key", FactSource.ASSERTED) is None


# ===================================================================
# 5. get_fact_sources — layer membership
# ===================================================================


def test_get_fact_sources_empty_when_key_absent(store):
    assert store.get_fact_sources("no_such_key") == set()


def test_get_fact_sources_single_layer(store):
    store.set_fact("k", FactValue(1), FactSource.SEMANTIC)

    assert store.get_fact_sources("k") == {FactSource.SEMANTIC}


def test_get_fact_sources_multi_layer(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)

    assert store.get_fact_sources("k") == {FactSource.ASSERTED, FactSource.INFERRED}


# ===================================================================
# 6. remove_fact — targeted & global removal
# ===================================================================


def test_remove_fact_targets_specific_layer(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)

    store.remove_fact("k", FactSource.ASSERTED)

    assert store.get_fact_sources("k") == {FactSource.INFERRED}


def test_remove_fact_without_source_clears_all_layers(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)

    store.remove_fact("k")

    assert store.get_fact_sources("k") == set()


def test_remove_fact_idempotent_on_missing_key(store):
    store.remove_fact("no_such_key", FactSource.ASSERTED)
    store.remove_fact("no_such_key")

    assert store.get_fact_sources("no_such_key") == set()


def test_remove_fact_from_one_layer_preserves_others(store):
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)

    store.remove_fact("k", FactSource.INFERRED)

    assert store.get_fact_sources("k") == {FactSource.ASSERTED, FactSource.SEMANTIC}


# ===================================================================
# 7. invalidate_layer — bulk layer clearance
# ===================================================================


def test_invalidate_layer_clears_only_that_layer(store):
    store.set_fact("a", FactValue(1), FactSource.ASSERTED)
    store.set_fact("b", FactValue(2), FactSource.INFERRED)
    store.set_fact("c", FactValue(3), FactSource.SEMANTIC)

    store.invalidate_layer(FactSource.INFERRED)

    assert store.get_fact_sources("a") == {FactSource.ASSERTED}
    assert store.get_fact_sources("b") == set()
    assert store.get_fact_sources("c") == {FactSource.SEMANTIC}


def test_invalidate_layer_asserted(store):
    store.set_fact("a", FactValue(1), FactSource.ASSERTED)
    store.set_fact("b", FactValue(2), FactSource.INFERRED)

    store.invalidate_layer(FactSource.ASSERTED)

    assert store.get_fact_sources("a") == set()
    assert store.get_fact_sources("b") == {FactSource.INFERRED}


def test_invalidate_layer_semantic(store):
    store.set_fact("a", FactValue(1), FactSource.SEMANTIC)
    store.set_fact("b", FactValue(2), FactSource.ASSERTED)

    store.invalidate_layer(FactSource.SEMANTIC)

    assert store.get_fact_sources("a") == set()
    assert store.get_fact_sources("b") == {FactSource.ASSERTED}


def test_invalidate_layer_idempotent_on_empty_layer(store):
    store.invalidate_layer(FactSource.INFERRED)

    assert store.get_layer_snapshot(FactSource.INFERRED) == {}


# ===================================================================
# 8. get_overrides — truth-maintenance override tracking
# ===================================================================


def test_asserted_overriding_inferred_records_override(store):
    store.set_fact("decision", FactValue("rule-engine"), FactSource.INFERRED)
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


def test_overrides_empty_on_fresh_store(store):
    assert store.get_overrides() == set()


# ===================================================================
# 9. get_changed_since — timestamp-based change tracking
# ===================================================================


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


def test_get_changed_since_empty_store(store):
    assert store.get_changed_since(0.0) == set()


def test_get_changed_since_after_removal(store):
    store.set_fact("k", FactValue(1))
    store.remove_fact("k")

    # After full removal the key should not appear (timestamp cleared)
    assert "k" not in store.get_changed_since(0.0)


# ===================================================================
# 10. Cross-method integration contracts
# ===================================================================


def test_set_then_remove_then_set_again(store):
    store.set_fact("k", FactValue(1), FactSource.ASSERTED)
    store.remove_fact("k")
    store.set_fact("k", FactValue(2), FactSource.INFERRED)

    assert store.get_unified_view()["k"].get_value() == 2
    assert store.get_fact_sources("k") == {FactSource.INFERRED}


def test_invalidate_then_repopulate_layer(store):
    store.set_fact("k", FactValue("old"), FactSource.INFERRED)
    store.invalidate_layer(FactSource.INFERRED)
    store.set_fact("k", FactValue("new"), FactSource.INFERRED)

    assert store.peek_in_layer("k", FactSource.INFERRED).get_value() == "new"


def test_override_lifecycle(store):
    """Full lifecycle: INFERRED → ASSERTED override → remove ASSERTED → no override."""
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)
    assert "k" in store.get_overrides()

    store.remove_fact("k", FactSource.ASSERTED)
    assert "k" not in store.get_overrides()
    assert store.peek_in_layer("k", FactSource.INFERRED).get_value() == "I"


def test_all_three_layers_same_key_then_invalidate_middle(store):
    store.set_fact("k", FactValue("S"), FactSource.SEMANTIC)
    store.set_fact("k", FactValue("I"), FactSource.INFERRED)
    store.set_fact("k", FactValue("A"), FactSource.ASSERTED)

    store.invalidate_layer(FactSource.INFERRED)

    # ASSERTED still wins
    assert store.get_unified_view()["k"].get_value() == "A"
    # Override set cleared (INFERRED layer gone)
    assert "k" not in store.get_overrides()
    # ASSERTED + SEMANTIC remain
    assert store.get_fact_sources("k") == {FactSource.ASSERTED, FactSource.SEMANTIC}


def test_unified_view_reflects_removal(store):
    store.set_fact("k", FactValue(1), FactSource.ASSERTED)
    store.set_fact("k", FactValue(2), FactSource.INFERRED)

    store.remove_fact("k", FactSource.ASSERTED)

    unified = store.get_unified_view()
    assert unified["k"].get_value() == 2
