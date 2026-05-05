"""
Phase 2.5 WS-3 and WS-4 tests — Graph serialization, GraphToMatrixAdapter,
and MLTopologicalSortStrategy.
"""

import json

import pytest

from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.graph_serialization import deserialize_graph, serialize_graph
from src.domain.graph.graph_to_matrix_adapter import GraphToMatrixAdapter
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.ml_topological_sort_strategy import MLTopologicalSortStrategy
from src.domain.nodes.record import HistoryRecord


# ===================================================================
# WS-3: GraphToMatrixAdapter
# ===================================================================


class TestGraphToMatrixAdapter:
    def test_empty_graph(self):
        g = HyperAdjacencyGraph()
        adapter = GraphToMatrixAdapter(g)
        assert adapter.get_dependency_two_dimension_list() == [[]]

    def test_single_edge(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B"})
        adapter = GraphToMatrixAdapter(g)
        matrix = adapter.get_dependency_two_dimension_list()
        id_map = adapter.get_node_id_dictionary()
        assert len(matrix) == 2
        a_id = [k for k, v in id_map.items() if v == "A"][0]
        b_id = [k for k, v in id_map.items() if v == "B"][0]
        assert matrix[a_id][b_id] == int(DependencyType.AND)

    def test_no_storage_drift(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B"})
        adapter = GraphToMatrixAdapter(g)
        m1 = adapter.get_dependency_two_dimension_list()
        g.add_dependency_group("B", int(DependencyType.OR), {"C"})
        m2 = adapter.get_dependency_two_dimension_list()
        assert len(m2) > len(m1) or any(
            any(c2 != c1 for c1, c2 in zip(r1, r2))
            for r1, r2 in zip(m1, m2)
        )

    def test_bitmask_or_in_matrix(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B"})
        g.add_dependency_group("A", int(DependencyType.MANDATORY), {"B"})
        adapter = GraphToMatrixAdapter(g)
        matrix = adapter.get_dependency_two_dimension_list()
        id_map = adapter.get_node_id_dictionary()
        a_id = [k for k, v in id_map.items() if v == "A"][0]
        b_id = [k for k, v in id_map.items() if v == "B"][0]
        assert matrix[a_id][b_id] == int(DependencyType.MANDATORY | DependencyType.AND)

    def test_legacy_matrix_methods_are_supported(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.MANDATORY | DependencyType.AND), {"B"})
        adapter = GraphToMatrixAdapter(g)
        id_map = adapter.get_node_id_dictionary()
        a_id = [k for k, v in id_map.items() if v == "A"][0]
        b_id = [k for k, v in id_map.items() if v == "B"][0]

        assert adapter.get_dependency_type(a_id, b_id) == int(DependencyType.MANDATORY | DependencyType.AND)
        assert adapter.get_to_child_dependency_list(a_id) == [b_id]
        assert adapter.get_and_to_child_dependency_list(a_id) == [b_id]
        assert adapter.get_mandatory_to_child_dependency_list(a_id) == [b_id]
        assert adapter.get_from_parent_dependency_list(b_id) == [a_id]


# ===================================================================
# WS-3: Graph Serialization
# ===================================================================


class TestGraphSerialization:
    def test_roundtrip_simple(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        g.add_dependency_group("B", int(DependencyType.OR), {"D"})

        data = serialize_graph(g)
        g2 = deserialize_graph(data)

        assert g2.get_dependency_type("A", "B") == int(DependencyType.AND)
        assert g2.get_dependency_type("A", "C") == int(DependencyType.AND)
        assert g2.get_dependency_type("B", "D") == int(DependencyType.OR)
        assert g2.has_node("A")
        assert g2.has_node("D")

    def test_roundtrip_with_node_records(self):
        g = HyperAdjacencyGraph()
        g.register_node("A", {"stable_id": "abc", "module": "rules", "imported": True, "import_depth": 1})
        g.add_dependency_group("A", int(DependencyType.AND), {"B"})

        data = serialize_graph(g)
        g2 = deserialize_graph(data)

        record = g2.get_node_record("A")
        assert record is not None
        assert record.stable_id == "abc"
        assert record.module == "rules"
        assert record.imported is True

    def test_deserialize_preserves_runtime_ids_and_next_id(self):
        g = HyperAdjacencyGraph()
        g.register_node("A", {"stable_id": "abc", "runtime_id": 9})
        data = serialize_graph(g)

        g2 = deserialize_graph(data)

        assert g2.lookup_by_name("A") == 9
        assert g2.lookup_by_id(9) == "A"
        assert g2.get_node_record("A").runtime_id == 9
        assert g2.register_node("B") == 10

    def test_schema_version_in_output(self):
        g = HyperAdjacencyGraph()
        data = serialize_graph(g)
        payload = json.loads(data)
        assert "schema_version" in payload

    def test_empty_graph_roundtrip(self):
        g = HyperAdjacencyGraph()
        data = serialize_graph(g)
        g2 = deserialize_graph(data)
        assert len(g2.all_node_names()) == 0


# ===================================================================
# WS-4: MLTopologicalSortStrategy
# ===================================================================


class TestMLTopologicalSortStrategy:
    def test_no_records_falls_back_to_topo_sort(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        g.add_dependency_group("B", int(DependencyType.AND), {"D"})

        strategy = MLTopologicalSortStrategy(g)
        result = strategy.sort()
        assert isinstance(result, tuple)
        assert result.index("A") < result.index("B")
        assert result.index("A") < result.index("C")
        assert result.index("B") < result.index("D")

    def test_with_records_produces_valid_topo_order(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B", "C"})
        g.add_dependency_group("B", int(DependencyType.AND), {"D"})
        g.add_dependency_group("C", int(DependencyType.AND), {"D"})

        records = {
            "A": HistoryRecord(name="A", true_count=8, false_count=2),
            "B": HistoryRecord(name="B", true_count=7, false_count=3),
            "C": HistoryRecord(name="C", true_count=3, false_count=7),
            "D": HistoryRecord(name="D", true_count=5, false_count=5),
        }

        strategy = MLTopologicalSortStrategy(g)
        result = strategy.sort(records)
        assert isinstance(result, tuple)
        assert set(result) == {"A", "B", "C", "D"}
        assert result.index("A") < result.index("B")
        assert result.index("A") < result.index("C")

    def test_or_children_most_true_first(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("P", int(DependencyType.OR), {"A", "B", "C"})

        records = {
            "P": HistoryRecord(name="P", true_count=5, false_count=5),
            "A": HistoryRecord(name="A", true_count=9, false_count=1),
            "B": HistoryRecord(name="B", true_count=5, false_count=5),
            "C": HistoryRecord(name="C", true_count=1, false_count=9),
        }

        strategy = MLTopologicalSortStrategy(g)
        result = strategy.sort(records)
        assert result[0] == "P"

    def test_empty_records_returns_topo_sort(self):
        g = HyperAdjacencyGraph()
        g.add_dependency_group("A", int(DependencyType.AND), {"B"})

        strategy = MLTopologicalSortStrategy(g)
        result = strategy.sort({})
        assert result == g.topological_sort()
