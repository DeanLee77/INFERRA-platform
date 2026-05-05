"""
Performance baseline benchmarks for INFERRA Phase 1.

Captures timing baselines for:
- Node ID generation (1k nodes)
- LayeredFactStore operations (1k facts)
- HyperAdjacencyGraph back-propagation (1k nodes)
- RuleValidationService validation (500-node rule set)
- MatrixToHyperGraphAdapter conversion

Run with: python -m pytest tests/benchmarks/ --benchmark-only
Or to regenerate baselines: python -m pytest tests/benchmarks/ --benchmark-only --benchmark-save=baseline_v0
"""

import json
import os
import time
from pathlib import Path

import pytest

from src.domain.nodes.node_id_utils import generate_node_id, reset_parse_context
from src.domain.state.fact_source import FactSource
from src.domain.state.layered_fact_store import LayeredFactStore
from src.domain.fact_values import FactValue, FactValueType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.dependency_type import DependencyType
from src.services.rule_validation_service import RuleValidationService


BENCHMARK_DIR = Path(__file__).parent.parent.parent / "benchmarks"
BASELINE_FILE = BENCHMARK_DIR / "baseline_v0.json"


# =============================================================================
# Benchmark helpers
# =============================================================================

def _build_large_rule_text(num_inputs: int = 50, num_rules: int = 50) -> str:
    """Build a rule text with num_inputs INPUT lines and num_rules comparison lines."""
    lines = []
    for i in range(num_inputs):
        lines.append(f"INPUT var_{i} AS NUMBER")
    for i in range(num_rules):
        lines.append(f"var_{i % num_inputs} > {i}")
    return "\n".join(lines) + "\n"


def _build_linear_graph(size: int) -> HyperAdjacencyGraph:
    """Build a linear dependency graph: n0 -> n1 -> n2 -> ... -> n(size-1)."""
    graph = HyperAdjacencyGraph()
    for i in range(size - 1):
        graph.add_dependency_group(f"n{i}", DependencyType.MANDATORY, {f"n{i+1}"})
    return graph


def _build_diamond_graph(size: int) -> HyperAdjacencyGraph:
    """Build a diamond-shaped graph with shared parents."""
    graph = HyperAdjacencyGraph()
    for i in range(size):
        children = set()
        if 2 * i + 1 < size:
            children.add(f"n{2*i+1}")
        if 2 * i + 2 < size:
            children.add(f"n{2*i+2}")
        if children:
            graph.add_dependency_group(f"n{i}", DependencyType.MANDATORY, children)
    return graph


# =============================================================================
# Manual benchmark runner (no pytest-benchmark dependency)
# =============================================================================

def _time_it(func, iterations: int = 100) -> dict:
    """Time a function over multiple iterations."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # ms

    times.sort()
    avg = sum(times) / len(times)
    p50 = times[len(times) // 2]
    p95 = times[int(len(times) * 0.95)]
    p99 = times[int(len(times) * 0.99)]
    return {
        "iterations": iterations,
        "avg_ms": round(avg, 3),
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
    }


# =============================================================================
# Baseline benchmarks
# =============================================================================

class TestPerformanceBaselines:
    """Performance baselines for Phase 1 core operations."""

    def test_node_id_generation_baseline(self):
        """Benchmark: generate 1000 node IDs."""
        def _run():
            reset_parse_context()
            for i in range(1000):
                generate_node_id("module", "rule", i, f"var_{i}")

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"Node ID generation too slow: {result}"
        print(f"\n  node_id_gen_1k: {result}")

    def test_layered_fact_store_set_baseline(self):
        """Benchmark: set 1000 facts in LayeredFactStore."""
        def _run():
            store = LayeredFactStore()
            for i in range(1000):
                store.set_fact(f"key_{i}", FactValue(i), source=FactSource.ASSERTED)

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"LayeredFactStore set too slow: {result}"
        print(f"\n  fact_store_set_1k: {result}")

    def test_layered_fact_store_unified_view_baseline(self):
        """Benchmark: get_unified_view with 1000 facts across 3 layers."""
        def _run():
            store = LayeredFactStore()
            for i in range(333):
                store.set_fact(f"k_{i}", FactValue(i), source=FactSource.ASSERTED)
                store.set_fact(f"k_{i}", FactValue(i+100), source=FactSource.INFERRED)
                store.set_fact(f"k_{i}", FactValue(i+200), source=FactSource.SEMANTIC)
            store.get_unified_view()

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"Unified view too slow: {result}"
        print(f"\n  unified_view_1k: {result}")

    def test_graph_back_propagate_baseline(self):
        """Benchmark: back-propagate in a 1000-node linear graph."""
        graph = _build_linear_graph(1000)

        def _run():
            graph.back_propagate("n999")

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"Back-propagate too slow: {result}"
        print(f"\n  back_propagate_1k: {result}")

    def test_graph_topo_sort_baseline(self):
        """Benchmark: topological sort on a 1000-node graph."""
        graph = _build_linear_graph(1000)

        def _run():
            graph.topological_sort()

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"Topo sort too slow: {result}"
        print(f"\n  topo_sort_1k: {result}")

    def test_validation_service_baseline(self):
        """Benchmark: validate a 500-node rule set."""
        rule_text = _build_large_rule_text(50, 50)
        svc = RuleValidationService()

        def _run():
            svc.validate(rule_text, "bench_rule")

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 50, f"Validation too slow: {result}"
        print(f"\n  validation_100rules: {result}")

    def test_validation_cache_hit_baseline(self):
        """Benchmark: cache hit on already-validated rule."""
        rule_text = _build_large_rule_text(50, 50)
        svc = RuleValidationService()
        svc.validate(rule_text, "bench_rule")  # warm cache

        def _run():
            svc.validate(rule_text, "bench_rule")

        result = _time_it(_run, iterations=100)
        assert result["p95_ms"] < 5, f"Cache hit too slow: {result}"
        print(f"\n  validation_cache_hit: {result}")


# =============================================================================
# Generate / update baseline file
# =============================================================================

class TestBaselineGenerator:
    """Generate the baseline_v0.json file for CI regression gates."""

    @pytest.mark.skipif(
        os.environ.get("INFERRA_GENERATE_BASELINES") != "1",
        reason="Set INFERRA_GENERATE_BASELINES=1 to rewrite benchmark baselines.",
    )
    def test_generate_baseline(self):
        """Run all benchmarks and save results to benchmarks/baseline_v0.json."""
        BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

        baselines = {}
        iterations = 200

        def _warmup(func, runs=3):
            for _ in range(runs):
                func()

        # Node ID generation
        def _node_id():
            reset_parse_context()
            for i in range(1000):
                generate_node_id("module", "rule", i, f"var_{i}")
        _warmup(_node_id)
        baselines["node_id_gen_1k"] = _time_it(_node_id, iterations)

        # Fact store set
        def _fact_set():
            store = LayeredFactStore()
            for i in range(1000):
                store.set_fact(f"key_{i}", FactValue(i), source=FactSource.ASSERTED)
        _warmup(_fact_set)
        baselines["fact_store_set_1k"] = _time_it(_fact_set, iterations)

        # Unified view
        def _unified():
            store = LayeredFactStore()
            for i in range(333):
                store.set_fact(f"k_{i}", FactValue(i), source=FactSource.ASSERTED)
                store.set_fact(f"k_{i}", FactValue(i+100), source=FactSource.INFERRED)
                store.set_fact(f"k_{i}", FactValue(i+200), source=FactSource.SEMANTIC)
            store.get_unified_view()
        _warmup(_unified)
        baselines["unified_view_1k"] = _time_it(_unified, iterations)

        # Graph back-propagate
        graph = _build_linear_graph(1000)
        def _bp():
            graph.back_propagate("n999")
        _warmup(_bp)
        baselines["back_propagate_1k"] = _time_it(_bp, iterations)

        # Topo sort
        def _topo():
            graph.topological_sort()
        _warmup(_topo)
        baselines["topo_sort_1k"] = _time_it(_topo, iterations)

        # Validation
        rule_text = _build_large_rule_text(50, 50)
        svc = RuleValidationService()
        def _val():
            svc.validate(rule_text, "bench_rule")
        _warmup(_val)
        baselines["validation_100rules"] = _time_it(_val, iterations)

        # Cache hit
        svc.validate(rule_text, "bench_rule")
        def _cache():
            svc.validate(rule_text, "bench_rule")
        _warmup(_cache)
        baselines["validation_cache_hit"] = _time_it(_cache, iterations)

        baselines["_metadata"] = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "python_version": "3.10",
            "platform": "windows",
        }

        with open(BASELINE_FILE, "w") as f:
            json.dump(baselines, f, indent=2)

        print(f"\n  Baseline saved to {BASELINE_FILE}")
