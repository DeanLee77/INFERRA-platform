"""Phase 2.5 sparse graph bridge benchmarks.

Captures 1k/5k/10k sparse graph evidence for the DependencyMatrix bridge:
- graph build
- graph-native topological sort
- MLTopologicalSortStrategy topological and DFS traversal
- back-propagation
- edge iteration

The 1k case also materializes a legacy dense matrix and verifies adapter
parity. The 5k and 10k cases compare against projected dense matrix cell
counts because materializing those matrices would be the deprecated runtime
behavior this bridge is retiring.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.matrix_to_hyper_adapter import MatrixToHyperGraphAdapter
from src.domain.graph.ml_topological_sort_strategy import MLTopologicalSortStrategy
from src.domain.nodes.record import HistoryRecord
from tests.benchmarks.benchmark_utils import quiet_benchmark_logging
from tests.benchmarks.test_phase2_performance_baselines import _time_it

BENCHMARK_DIR = Path(__file__).parent.parent.parent / "benchmarks"
BASELINE_FILE = BENCHMARK_DIR / "baseline_phase2_5_sparse.json"

FANOUT = 4
SCALES = (1000, 5000, 10000)
ITERATIONS_BY_SIZE = {1000: 20, 5000: 10, 10000: 5}
BUILD_ITERATIONS_BY_SIZE = {1000: 10, 5000: 5, 10000: 3}
REGRESSION_THRESHOLD = 0.75
ABSOLUTE_TOLERANCE_MS = 600.0
MATRIX_CELL_REFERENCE_BYTES = 8

LOGGER_PATCHES = (
    ("src.domain.graph.hyper_adjacency_graph", "_logger"),
    ("src.domain.graph.ml_topological_sort_strategy", "_logger"),
)

P95_LIMITS_MS = {
    1000: {
        "build_graph": 250,
        "topological_sort": 75,
        "ml_topological_sort": 150,
        "ml_depth_first_sort": 150,
        "back_propagate": 75,
        "edge_iteration": 25,
    },
    5000: {
        "build_graph": 1000,
        "topological_sort": 350,
        "ml_topological_sort": 700,
        "ml_depth_first_sort": 700,
        "back_propagate": 350,
        "edge_iteration": 100,
    },
    10000: {
        "build_graph": 2500,
        "topological_sort": 900,
        "ml_topological_sort": 1600,
        "ml_depth_first_sort": 1600,
        "back_propagate": 900,
        "edge_iteration": 200,
    },
}

METRICS_TO_COMPARE = (
    "build_graph",
    "topological_sort",
    "ml_topological_sort",
    "ml_depth_first_sort",
    "back_propagate",
    "edge_iteration",
)

TIMING_FIELDS = ("p50_ms",)


def _sparse_edge_specs(size: int, fanout: int = FANOUT) -> Iterable[Tuple[int, int, DependencyType]]:
    for parent in range(size):
        for offset in range(1, fanout + 1):
            child = parent + offset
            if child >= size:
                continue
            dep_type = DependencyType.MANDATORY | (
                DependencyType.OR if offset % 2 == 0 else DependencyType.AND
            )
            yield parent, child, dep_type


def _build_sparse_dag(size: int, fanout: int = FANOUT) -> HyperAdjacencyGraph:
    graph = HyperAdjacencyGraph()
    for idx in range(size):
        graph.register_node(f"n{idx}", {"runtime_id": idx})

    for parent in range(size):
        and_children = {
            f"n{parent + offset}"
            for offset in range(1, fanout + 1, 2)
            if parent + offset < size
        }
        or_children = {
            f"n{parent + offset}"
            for offset in range(2, fanout + 1, 2)
            if parent + offset < size
        }
        if and_children:
            graph.add_dependency_group(
                f"n{parent}",
                DependencyType.MANDATORY | DependencyType.AND,
                and_children,
            )
        if or_children:
            graph.add_dependency_group(
                f"n{parent}",
                DependencyType.MANDATORY | DependencyType.OR,
                or_children,
            )
    return graph


def _history_records(size: int) -> Dict[str, HistoryRecord]:
    return {
        f"n{idx}": HistoryRecord(
            name=f"n{idx}",
            true_count=(idx % 7) + 1,
            false_count=((idx * 3) % 11) + 1,
        )
        for idx in range(size)
    }


def _edge_count(size: int, fanout: int = FANOUT) -> int:
    return sum(1 for _ in _sparse_edge_specs(size, fanout))


def _dense_matrix_profile(size: int, edge_count: int) -> dict:
    cells = size * size
    return {
        "dense_matrix_cells": cells,
        "dense_matrix_cell_ref_mb": round(
            cells * MATRIX_CELL_REFERENCE_BYTES / (1024 * 1024),
            3,
        ),
        "edge_to_dense_cell_ratio": round(edge_count / cells, 8),
        "dense_cells_per_graph_edge": round(cells / edge_count, 3),
    }


def _clear_topo_cache(graph: HyperAdjacencyGraph) -> None:
    graph._topo_cache = None


def _profile_sparse_graph(size: int) -> dict:
    build_iterations = BUILD_ITERATIONS_BY_SIZE[size]
    iterations = ITERATIONS_BY_SIZE[size]

    def _build():
        _build_sparse_dag(size)

    build_result = _time_it(_build, build_iterations)
    graph = _build_sparse_dag(size)
    records = _history_records(size)
    strategy = MLTopologicalSortStrategy(graph)

    def _topo():
        _clear_topo_cache(graph)
        order = graph.topological_sort()
        assert len(order) == size

    def _ml_topo():
        _clear_topo_cache(graph)
        order = strategy.sort(records)
        assert len(order) == size

    def _ml_dfs():
        _clear_topo_cache(graph)
        order = strategy.sort_depth_first(records)
        assert len(order) == size

    def _back_propagate():
        affected = graph.back_propagate(f"n{size - 1}")
        assert affected

    def _edge_iter():
        assert sum(1 for _ in graph.edges()) == edge_count

    edge_count = _edge_count(size)
    results = {
        "nodes": size,
        "edges": edge_count,
        "fanout": FANOUT,
        **_dense_matrix_profile(size, edge_count),
        "build_graph": build_result,
        "topological_sort": _time_it(_topo, iterations),
        "ml_topological_sort": _time_it(_ml_topo, iterations),
        "ml_depth_first_sort": _time_it(_ml_dfs, iterations),
        "back_propagate": _time_it(_back_propagate, iterations),
        "edge_iteration": _time_it(_edge_iter, iterations),
    }
    return results


def _profile_all_sparse_graphs() -> dict:
    return {
        f"sparse_graph_{size // 1000}k_fanout{FANOUT}": _profile_sparse_graph(size)
        for size in SCALES
    }


def _load_baseline() -> dict:
    if not BASELINE_FILE.exists():
        pytest.skip(f"Baseline file not found: {BASELINE_FILE}")
    with open(BASELINE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _assert_absolute_limits(name: str, profile: dict) -> None:
    limits = P95_LIMITS_MS[profile["nodes"]]
    failures = []
    for metric, limit in limits.items():
        actual = profile[metric]["p95_ms"]
        if actual > limit:
            failures.append(f"{name}.{metric}.p95_ms={actual}ms > {limit}ms")

    assert not failures, "Sparse graph benchmark limit failures:\n  " + "\n  ".join(failures)


def _assert_not_regressed(name: str, baseline: dict, current: dict) -> None:
    regressions = []
    for metric in METRICS_TO_COMPARE:
        for field in TIMING_FIELDS:
            base_value = baseline[metric].get(field)
            current_value = current[metric].get(field)
            if base_value is None or current_value is None:
                continue
            allowed = max(
                base_value * (1.0 + REGRESSION_THRESHOLD),
                base_value + ABSOLUTE_TOLERANCE_MS,
            )
            if current_value > allowed:
                pct_over = ((current_value - base_value) / base_value) * 100 if base_value else 0
                regressions.append(
                    f"{name}.{metric}.{field}: baseline={base_value:.3f}ms, "
                    f"current={current_value:.3f}ms (+{pct_over:.1f}%)"
                )

    assert not regressions, "Phase 2.5 sparse graph regressions:\n  " + "\n  ".join(regressions)


class TestPhase25SparseGraphBenchmarks:
    @pytest.mark.skipif(
        sys.gettrace() is not None,
        reason="Sparse graph benchmark timings are invalid under coverage/tracing.",
    )
    def test_1k_5k_10k_sparse_graphs_against_baseline(self):
        baseline = _load_baseline()
        with quiet_benchmark_logging(LOGGER_PATCHES):
            current = _profile_all_sparse_graphs()

        for name, profile in current.items():
            assert profile["dense_cells_per_graph_edge"] >= 200
            assert profile["edge_to_dense_cell_ratio"] <= 0.005
            _assert_absolute_limits(name, profile)
            _assert_not_regressed(name, baseline[name], profile)
            print(f"\n  {name}: {profile}")

    def test_1k_legacy_matrix_adapter_parity(self):
        size = 1000
        matrix: List[List[int]] = [[-1] * size for _ in range(size)]
        for parent, child, dep_type in _sparse_edge_specs(size):
            matrix[parent][child] = int(dep_type)

        adapter = MatrixToHyperGraphAdapter.from_legacy_list(
            matrix,
            {idx: f"n{idx}" for idx in range(size)},
        )
        graph = _build_sparse_dag(size)

        assert sum(1 for _ in adapter.edges()) == sum(1 for _ in graph.edges())
        assert adapter.topological_sort() == graph.topological_sort()
        for parent, child, dep_type in graph.edges():
            assert adapter.get_dependency_type(parent, child) == dep_type


class TestPhase25SparseGraphBaselineGenerator:
    @pytest.mark.skipif(
        os.environ.get("INFERRA_GENERATE_PHASE25_SPARSE_BASELINE") != "1",
        reason="Set INFERRA_GENERATE_PHASE25_SPARSE_BASELINE=1 to rewrite the sparse graph baseline.",
    )
    def test_generate_baseline(self):
        BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
        with quiet_benchmark_logging(LOGGER_PATCHES):
            baseline = _profile_all_sparse_graphs()
        baseline["_metadata"] = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "phase": 2.5,
            "purpose": "1k/5k/10k sparse graph bridge acceptance",
            "fanout": FANOUT,
            "matrix_baseline": (
                "1k materialized for adapter parity; 5k/10k use dense matrix "
                "cell-count and memory projections because dense Python matrices "
                "are deprecated compatibility payloads."
            ),
        }
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)
        print(f"\n  Phase 2.5 sparse graph baseline saved to {BASELINE_FILE}")
