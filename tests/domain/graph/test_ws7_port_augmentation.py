"""
Phase 2.5 WS-7 tests — Port augmentation and DependencyType IntFlag migration.

Covers:
- FactStorePort ABCMeta conversion
- DependencyGraphPort default method implementations
- HyperAdjacencyGraph register_node / edges / NodeRecord
- HyperAdjacencyGraph O(1) lookup_by_id / lookup_by_name / get_dependency_type
- DependencyType IntFlag bitmask operations
- subgraph preserves all edge types
"""

from typing import Type

import pytest

from src.domain.graph.dependency_group import DependencyGroup
from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import (
    HyperAdjacencyGraph,
    NodeRecord,
)
from src.ports.dependency_graph_port import DependencyGraphPort
from src.ports.fact_store_port import FactStorePort
from src.domain.state.layered_fact_store import LayeredFactStore


# ===================================================================
# 1. FactStorePort is ABCMeta
# ===================================================================


class TestFactStorePortABCMeta:
    def test_isinstance_layered_fact_store(self):
        store = LayeredFactStore()
        assert isinstance(store, FactStorePort)

    def test_cannot_instantiate_port_directly(self):
        with pytest.raises(TypeError):
            FactStorePort()

    def test_subclass_must_implement_all_methods(self):
        class IncompleteStore(FactStorePort):
            pass

        with pytest.raises(TypeError):
            IncompleteStore()


# ===================================================================
# 2. DependencyGraphPort default methods
# ===================================================================


class TestDefaultMethods:
    """Test that default method implementations work on the port base."""

    def test_get_children_by_type_default(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"A", "B"})
        g.add_dependency_group("P", int(DependencyType.OR), {"C"})
        result = g.get_children_by_type("P", int(DependencyType.AND))
        assert set(result) == {"A", "B"}

    def test_get_children_flat_default(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"A"})
        g.add_dependency_group("P", int(DependencyType.OR), {"B"})
        result = g.get_children_flat("P")
        assert set(result) == {"A", "B"}

    def test_has_children_of_type_true(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"A"})
        assert g.has_children_of_type("P", int(DependencyType.AND)) is True

    def test_has_children_of_type_false(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"A"})
        assert g.has_children_of_type("P", int(DependencyType.OR)) is False

    def test_subgraph_preserves_edge_types(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        g.add_dependency_group("B", int(DependencyType.OR), {"D"})
        sub = g.subgraph({"A", "B", "C"})
        assert sub.get_dependency_type("A", "B") == int(DependencyType.AND)
        assert sub.get_dependency_type("A", "C") == int(DependencyType.AND)
        assert sub.has_node("D") is False

    def test_subgraph_preserves_multiple_dep_types(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"A"})
        g.add_dependency_group("P", int(DependencyType.OR), {"B"})
        sub = g.subgraph({"P", "A", "B"})
        groups = sub.get_child_groups("P")
        types = {g[0] for g in groups}
        assert int(DependencyType.AND) in types
        assert int(DependencyType.OR) in types

    def test_subgraph_preserves_isolated_nodes_and_records(self):
        g = HyperAdjacencyGraph()
        g.register_node(
            "lonely",
            {
                "stable_id": "stable-lonely",
                "runtime_id": 7,
                "module": "rules",
                "import_namespace": "common@1.0",
                "imported": True,
                "import_depth": 1,
            },
        )
        g.add_dependency_group("A", int(DependencyType.AND), {"B"})

        sub = g.subgraph({"lonely"})

        assert sub.has_node("lonely") is True
        assert sub.lookup_by_name("lonely") == 7
        record = sub.get_node_record("lonely")
        assert record is not None
        assert record.stable_id == "stable-lonely"
        assert record.module == "rules"
        assert record.import_namespace == "common@1.0"
        assert record.imported is True
        assert record.import_depth == 1

    def test_lookup_by_id_default_returns_none(self):
        g = HyperAdjacencyGraph()
        assert g.lookup_by_id(0) is None

    def test_lookup_by_name_default_returns_none(self):
        g = HyperAdjacencyGraph()
        assert g.lookup_by_name("A") is None


# ===================================================================
# 3. HyperAdjacencyGraph register_node / NodeRecord
# ===================================================================


class TestRegisterNode:
    def test_register_node_returns_id(self):
        g = HyperAdjacencyGraph()
        nid = g.register_node("applicant_is_eligible")
        assert isinstance(nid, int)
        assert nid >= 0

    def test_register_node_idempotent(self):
        g = HyperAdjacencyGraph()
        id1 = g.register_node("A")
        id2 = g.register_node("A")
        assert id1 == id2

    def test_register_node_sequential_ids(self):
        g = HyperAdjacencyGraph()
        id_a = g.register_node("A")
        id_b = g.register_node("B")
        assert id_a != id_b

    def test_register_node_with_metadata(self):
        g = HyperAdjacencyGraph()
        nid = g.register_node("A", {
            "stable_id": "abc123",
            "module": "eligibility_rules",
            "import_namespace": "common@1.0",
            "import_version": "1.0",
            "imported": True,
            "import_depth": 2,
        })
        record = g.get_node_record("A")
        assert record is not None
        assert record.name == "A"
        assert record.stable_id == "abc123"
        assert record.runtime_id == nid
        assert record.module == "eligibility_rules"
        assert record.import_namespace == "common@1.0"
        assert record.imported is True
        assert record.import_depth == 2

    def test_register_node_preserves_requested_runtime_id(self):
        g = HyperAdjacencyGraph()
        nid = g.register_node("A", {"runtime_id": 12, "stable_id": "abc123"})
        next_id = g.register_node("B")

        assert nid == 12
        assert g.lookup_by_name("A") == 12
        assert g.lookup_by_id(12) == "A"
        assert next_id == 13

    def test_register_node_update_metadata(self):
        g = HyperAdjacencyGraph()
        g.register_node("A", {"module": "old"})
        g.register_node("A", {"module": "new"})
        record = g.get_node_record("A")
        assert record.module == "new"

    def test_get_node_record_unregistered(self):
        g = HyperAdjacencyGraph()
        assert g.get_node_record("nope") is None

    def test_find_nodes_by_module(self):
        g = HyperAdjacencyGraph()
        g.register_node("A", {"module": "rules"})
        g.register_node("B", {"module": "rules"})
        g.register_node("C", {"module": "other"})
        found = g.find_nodes_by_module("rules")
        assert len(found) == 2
        assert {r.name for r in found} == {"A", "B"}

    def test_find_nodes_by_namespace(self):
        g = HyperAdjacencyGraph()
        g.register_node("A", {"import_namespace": "common@1.0"})
        g.register_node("B", {"import_namespace": "common@1.0"})
        g.register_node("C", {"import_namespace": "special@2.0"})
        found = g.find_nodes_by_namespace("common@1.0")
        assert len(found) == 2


# ===================================================================
# 4. HyperAdjacencyGraph edges iterator
# ===================================================================


class TestEdges:
    def test_edges_empty_graph(self):
        g = HyperAdjacencyGraph()
        assert list(g.edges()) == []

    def test_edges_returns_all_edges(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        g.add_dependency_group("B", int(DependencyType.OR), {"D"})
        edges = list(g.edges())
        assert len(edges) == 3
        assert ("A", "B", int(DependencyType.AND)) in edges
        assert ("A", "C", int(DependencyType.AND)) in edges
        assert ("B", "D", int(DependencyType.OR)) in edges


# ===================================================================
# 5. HyperAdjacencyGraph O(1) lookups
# ===================================================================


class TestO1Lookups:
    def test_get_dependency_type_found(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"C"})
        assert g.get_dependency_type("P", "C") == int(DependencyType.AND)

    def test_get_dependency_type_not_found(self):
        g = HyperAdjacencyGraph()
        assert g.get_dependency_type("P", "C") == -1

    def test_lookup_by_id(self):
        g = HyperAdjacencyGraph()
        nid = g.register_node("A")
        assert g.lookup_by_id(nid) == "A"

    def test_lookup_by_name(self):
        g = HyperAdjacencyGraph()
        nid = g.register_node("A")
        assert g.lookup_by_name("A") == nid

    def test_lookup_by_id_not_found(self):
        g = HyperAdjacencyGraph()
        assert g.lookup_by_id(999) is None

    def test_lookup_by_name_not_found(self):
        g = HyperAdjacencyGraph()
        assert g.lookup_by_name("nope") is None


# ===================================================================
# 6. DependencyType IntFlag operations
# ===================================================================


class TestDependencyTypeIntFlag:
    def test_bitwise_or(self):
        result = DependencyType.MANDATORY | DependencyType.AND
        assert int(result) == 72

    def test_bitwise_and(self):
        combined = DependencyType.MANDATORY | DependencyType.AND
        assert DependencyType.AND in combined
        assert DependencyType.OR not in combined

    def test_membership_check(self):
        combined = DependencyType.MANDATORY | DependencyType.AND
        assert DependencyType.AND in combined

    def test_value_preserved(self):
        assert DependencyType.AND.value == 8
        assert int(DependencyType.MANDATORY | DependencyType.AND) == 72

    def test_backward_compat_getter(self):
        assert DependencyType.AND == 8
        assert DependencyType.MANDATORY == 64

    def test_legacy_getter_methods_return_plain_ints(self):
        assert DependencyType.get_and() == 8
        assert DependencyType.get_or() == 4
        assert DependencyType.get_mandatory() == 64
        assert isinstance(DependencyType.get_and(), int)

    def test_dependency_array_is_idempotent(self):
        expected = [8, 4, 2, 1, 64, 32, 16]
        DependencyType.populating_dependency()
        first = DependencyType.get_dependency_array()
        DependencyType.populating_dependency()
        second = DependencyType.get_dependency_array()

        assert first == expected
        assert second == expected

    def test_node_dependency_type_shim_points_to_canonical_graph_type(self):
        from src.domain.nodes.dependency_type import DependencyType as NodeDependencyType

        assert NodeDependencyType is DependencyType
        assert NodeDependencyType.get_dependency_array() == DependencyType.get_dependency_array()


# ===================================================================
# 7. NodeRecord dataclass
# ===================================================================


class TestNodeRecord:
    def test_frozen(self):
        r = NodeRecord(name="A", runtime_id=0)
        with pytest.raises(AttributeError):
            r.name = "B"

    def test_defaults(self):
        r = NodeRecord(name="A")
        assert r.stable_id == ""
        assert r.runtime_id == -1
        assert r.module == ""
        assert r.import_namespace == ""
        assert r.import_version == ""
        assert r.imported is False
        assert r.import_depth == 0

    def test_full_record(self):
        r = NodeRecord(
            name="A",
            stable_id="abc",
            runtime_id=5,
            module="rules",
            import_namespace="common@1.0",
            import_version="1.0",
            imported=True,
            import_depth=3,
        )
        assert r.stable_id == "abc"
        assert r.imported is True
        assert r.import_depth == 3


# ===================================================================
# 8. has_node includes registered nodes
# ===================================================================


class TestHasNodeRegistered:
    def test_registered_node_exists(self):
        g = HyperAdjacencyGraph()
        g.register_node("lonely")
        assert g.has_node("lonely") is True

    def test_registered_node_in_all_names(self):
        g = HyperAdjacencyGraph()
        g.register_node("lonely")
        assert "lonely" in g.all_node_names()


# ===================================================================
# 9. Bitmask write-time merge
# ===================================================================


class TestBitmaskMerge:
    def test_merge_overlapping_edge(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"C"})
        g.add_dependency_group("P", int(DependencyType.MANDATORY), {"C"})
        assert g.get_dependency_type("P", "C") == int(DependencyType.MANDATORY | DependencyType.AND)

    def test_merge_does_not_affect_unrelated_edge(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.AND), {"A"})
        g.add_dependency_group("P", int(DependencyType.MANDATORY), {"C"})
        assert g.get_dependency_type("P", "A") == int(DependencyType.AND)
