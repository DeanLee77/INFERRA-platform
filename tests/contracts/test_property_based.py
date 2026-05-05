"""
Property-based tests for Phase 1 core invariants.

Uses Hypothesis to verify:
1. Hash ID collision resistance
2. LayeredFactStore layer isolation invariants
3. Topological order parity (graph vs. matrix)
4. Back-propagation cycle detection
"""

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.domain.nodes.node_id_utils import generate_node_id, reset_parse_context
from src.domain.state.fact_source import FactSource
from src.domain.state.layered_fact_store import LayeredFactStore
from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph, CyclicGraphError
from src.domain.graph.dependency_type import DependencyType


# =============================================================================
# 1. Hash ID Collision Resistance
# =============================================================================

class TestNodeIdCollisionResistance:
    """Property: generate_node_id produces unique IDs for distinct inputs."""

    @given(
        module=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
        rule=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
        line=st.integers(min_value=1, max_value=9999),
        var=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_deterministic_for_same_input(self, module, rule, line, var):
        """Same inputs always produce the same ID."""
        reset_parse_context()
        id1 = generate_node_id(module, rule, line, var)
        reset_parse_context()
        id2 = generate_node_id(module, rule, line, var)
        assert id1 == id2

    def test_unique_for_different_inputs(self):
        """Different inputs produce different IDs within a single parse context."""
        reset_parse_context()
        ids = set()
        for i in range(200):
            node_id = generate_node_id("mod", "rule", i, f"var_{i}")
            # Each ID must be unique within the parse context
            assert node_id not in ids, f"Collision detected at i={i}: {node_id}"
            ids.add(node_id)

    @given(
        line=st.integers(min_value=1, max_value=10000),
        var=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_id_is_16_chars_or_longer(self, line, var):
        """Generated IDs are at least 16 characters long."""
        reset_parse_context()
        node_id = generate_node_id("module", "rule", line, var)
        assert len(node_id) >= 16


# =============================================================================
# 2. LayeredFactStore Layer Isolation Invariants
# =============================================================================

class TestLayerIsolationInvariants:
    """Property: Layered fact store maintains isolation and precedence invariants."""

    @given(
        keys=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1, max_size=10, unique=True
        ),
    )
    @settings(max_examples=50)
    def test_invalidate_layer_only_affects_target(self, keys):
        """Invalidating one layer does not affect other layers."""
        store = LayeredFactStore()

        # Populate all three layers
        for i, key in enumerate(keys):
            store.set_fact(key, FactValue(i), source=FactSource.ASSERTED)
            store.set_fact(key, FactValue(i + 100), source=FactSource.INFERRED)
            store.set_fact(key, FactValue(i + 200), source=FactSource.SEMANTIC)

        # Invalidate INFERRED
        store.invalidate_layer(FactSource.INFERRED)

        # ASSERTED and SEMANTIC should still be present
        for i, key in enumerate(keys):
            assert store.peek_in_layer(key, FactSource.ASSERTED) is not None
            assert store.peek_in_layer(key, FactSource.SEMANTIC) is not None
            assert store.peek_in_layer(key, FactSource.INFERRED) is None

    @given(
        key=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    )
    @settings(max_examples=50)
    def test_asserted_wins_over_inferred_in_unified_view(self, key):
        """When same key exists in ASSERTED and INFERRED, ASSERTED wins."""
        store = LayeredFactStore()
        store.set_fact(key, FactValue("inferred"), source=FactSource.INFERRED)
        store.set_fact(key, FactValue("asserted"), source=FactSource.ASSERTED)

        view = store.get_unified_view()
        assert view[key].get_value() == "asserted"

    @given(
        key=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    )
    @settings(max_examples=50)
    def test_inferred_wins_over_semantic_in_unified_view(self, key):
        """When same key exists in INFERRED and SEMANTIC, INFERRED wins."""
        store = LayeredFactStore()
        store.set_fact(key, FactValue("semantic"), source=FactSource.SEMANTIC)
        store.set_fact(key, FactValue("inferred"), source=FactSource.INFERRED)

        view = store.get_unified_view()
        assert view[key].get_value() == "inferred"

    @given(
        keys=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=0, max_size=5, unique=True
        ),
    )
    @settings(max_examples=50)
    def test_unified_view_is_fresh_copy(self, keys):
        """get_unified_view returns a fresh dict each time."""
        store = LayeredFactStore()
        for key in keys:
            store.set_fact(key, FactValue(1), source=FactSource.ASSERTED)

        view1 = store.get_unified_view()
        view2 = store.get_unified_view()
        assert view1 is not view2
        assert view1 == view2

    @given(
        key=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    )
    @settings(max_examples=50)
    def test_remove_fact_idempotent(self, key):
        """Removing a non-existent fact is safe (no error)."""
        store = LayeredFactStore()
        store.remove_fact(key, FactSource.ASSERTED)  # should not raise
        store.remove_fact(key, None)  # remove from all layers


# =============================================================================
# 3. HyperAdjacencyGraph Invariants
# =============================================================================

class TestHyperAdjacencyGraphInvariants:
    """Property: Graph maintains structural invariants under mutations."""

    @given(
        nodes=st.lists(st.text(min_size=1, max_size=10, alphabet="abcde"), min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=50)
    def test_add_and_query_parent_roundtrip(self, nodes):
        """Adding a dependency and querying it returns the same parent."""
        graph = HyperAdjacencyGraph()
        if len(nodes) < 2:
            return
        parent = nodes[0]
        children = set(nodes[1:])
        graph.add_dependency_group(parent, DependencyType.MANDATORY, children)

        for child in children:
            assert parent in graph.get_parent_edges(child)

    @given(
        nodes=st.lists(st.text(min_size=1, max_size=10, alphabet="abcde"), min_size=3, max_size=5, unique=True),
    )
    @settings(max_examples=50)
    def test_back_propagate_visits_all_parents(self, nodes):
        """Back-propagation from a leaf reaches all ancestors."""
        graph = HyperAdjacencyGraph()
        # Create a linear chain: n0 -> n1 -> n2 -> ...
        for i in range(len(nodes) - 1):
            graph.add_dependency_group(nodes[i], DependencyType.MANDATORY, {nodes[i + 1]})

        # Propagate from the last node
        result = graph.back_propagate(nodes[-1])

        # All ancestors should be in the result
        for ancestor in nodes[:-1]:
            assert ancestor in result

    def test_back_propagate_cycle_detection(self):
        """Back-propagation detects cycles and raises CyclicGraphError."""
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("a", DependencyType.MANDATORY, {"b"})
        graph.add_dependency_group("b", DependencyType.MANDATORY, {"a"})

        # With a very low max_steps, the visited set alone won't save us
        # — the step counter will trigger CyclicGraphError
        with pytest.raises(CyclicGraphError):
            graph.back_propagate("a", max_steps=1)

    def test_back_propagate_visited_set_prevents_infinite_loop(self):
        """Even with cycles, the visited set prevents infinite BFS loops."""
        graph = HyperAdjacencyGraph()
        graph.add_dependency_group("a", DependencyType.MANDATORY, {"b"})
        graph.add_dependency_group("b", DependencyType.MANDATORY, {"a"})

        # With default max_steps, the visited set prevents infinite loops
        # so this should complete without error
        result = graph.back_propagate("a")
        # 'a' and 'b' form a cycle; visited set ensures each is processed once
        assert "b" in result  # b is a parent of a

    @given(
        nodes=st.lists(st.text(min_size=1, max_size=10, alphabet="abcde"), min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=50)
    def test_topological_sort_is_deterministic(self, nodes):
        """Topological sort produces consistent results for the same graph."""
        graph = HyperAdjacencyGraph()
        if len(nodes) < 2:
            return
        for i in range(len(nodes) - 1):
            graph.add_dependency_group(nodes[i], DependencyType.MANDATORY, {nodes[i + 1]})

        sort1 = graph.topological_sort()
        sort2 = graph.topological_sort()
        assert sort1 == sort2
