"""
Benchmark regression CI gate for INFERRA Phase 1.

Compares current benchmark results against ``benchmarks/baseline_v0.json``.
Fails CI if any benchmark's median timing regresses more than 10% from the
stored baseline.

Uses higher iteration counts (200) than the casual baseline generator (50)
to reduce run-to-run variance on Windows where OS scheduling jitter causes
significant noise at sub-5ms timings.

Run with: python -m pytest tests/benchmarks/test_benchmark_regression.py -v
"""

import json
import sys
from pathlib import Path

import pytest

from src.domain.nodes.node_id_utils import generate_node_id, reset_parse_context
from src.domain.state.fact_source import FactSource
from src.domain.state.layered_fact_store import LayeredFactStore
from src.domain.fact_values import FactValue
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.dependency_type import DependencyType
from src.services.rule_validation_service import RuleValidationService
from tests.benchmarks.test_performance_baselines import (
    _build_large_rule_text,
    _build_linear_graph,
    _time_it,
)
from tests.benchmarks.benchmark_utils import quiet_benchmark_logging

BENCHMARK_DIR = Path(__file__).parent.parent.parent / "benchmarks"
BASELINE_FILE = BENCHMARK_DIR / "baseline_v0.json"

REGRESSION_THRESHOLD = 0.10
ABSOLUTE_TOLERANCE_MS = 2.0

MIN_BASELINE_MS = 1.0

ITERATIONS = 200

METRICS_TO_CHECK = ("p50_ms",)

LOGGER_PATCHES = (
    ("src.services.rule_validation_service", "_logger"),
)


def _load_baseline() -> dict:
    if not BASELINE_FILE.exists():
        pytest.skip(f"Baseline file not found: {BASELINE_FILE}")
    with open(BASELINE_FILE) as f:
        return json.load(f)


def _warmup(func, runs: int = 3):
    for _ in range(runs):
        func()


def _run_all_benchmarks() -> dict:
    results = {}

    def _node_id():
        reset_parse_context()
        for i in range(1000):
            generate_node_id("module", "rule", i, f"var_{i}")

    _warmup(_node_id)
    results["node_id_gen_1k"] = _time_it(_node_id, ITERATIONS)

    def _fact_set():
        store = LayeredFactStore()
        for i in range(1000):
            store.set_fact(f"key_{i}", FactValue(i), source=FactSource.ASSERTED)

    _warmup(_fact_set)
    results["fact_store_set_1k"] = _time_it(_fact_set, ITERATIONS)

    def _unified():
        store = LayeredFactStore()
        for i in range(333):
            store.set_fact(f"k_{i}", FactValue(i), source=FactSource.ASSERTED)
            store.set_fact(f"k_{i}", FactValue(i + 100), source=FactSource.INFERRED)
            store.set_fact(f"k_{i}", FactValue(i + 200), source=FactSource.SEMANTIC)
        store.get_unified_view()

    _warmup(_unified)
    results["unified_view_1k"] = _time_it(_unified, ITERATIONS)

    graph = _build_linear_graph(1000)

    def _bp():
        graph.back_propagate("n999")

    _warmup(_bp)
    results["back_propagate_1k"] = _time_it(_bp, ITERATIONS)

    def _topo():
        graph.topological_sort()

    _warmup(_topo)
    results["topo_sort_1k"] = _time_it(_topo, ITERATIONS)

    rule_text = _build_large_rule_text(50, 50)
    svc = RuleValidationService()

    def _val():
        svc.validate(rule_text, "bench_rule")

    _warmup(_val)
    results["validation_100rules"] = _time_it(_val, ITERATIONS)

    svc.validate(rule_text, "bench_rule")

    def _cache():
        svc.validate(rule_text, "bench_rule")

    _warmup(_cache)
    results["validation_cache_hit"] = _time_it(_cache, ITERATIONS)

    return results


class TestBenchmarkRegression:
    """CI regression gate: fail if any benchmark regresses >10% from baseline."""

    @pytest.mark.skipif(
        sys.gettrace() is not None,
        reason="Benchmark regression timings are invalid under coverage/tracing.",
    )
    def test_no_regression_from_baseline(self):
        baseline = _load_baseline()
        with quiet_benchmark_logging(LOGGER_PATCHES):
            current = _run_all_benchmarks()

        regressions = []

        for bench_name, baseline_metrics in baseline.items():
            if bench_name.startswith("_"):
                continue

            if bench_name not in current:
                regressions.append(
                    f"{bench_name}: present in baseline but not in current results"
                )
                continue

            current_metrics = current[bench_name]

            for metric in METRICS_TO_CHECK:
                base_val = baseline_metrics.get(metric)
                cur_val = current_metrics.get(metric)

                if base_val is None or cur_val is None:
                    continue

                if base_val < MIN_BASELINE_MS:
                    continue

                allowed = max(
                    base_val * (1.0 + REGRESSION_THRESHOLD),
                    base_val + ABSOLUTE_TOLERANCE_MS,
                )

                if cur_val > allowed:
                    pct_over = ((cur_val - base_val) / base_val) * 100
                    regressions.append(
                        f"{bench_name}.{metric}: "
                        f"baseline={base_val:.3f}ms, current={cur_val:.3f}ms "
                        f"(+{pct_over:.1f}%, threshold=+{REGRESSION_THRESHOLD * 100:.0f}% "
                        f"or +{ABSOLUTE_TOLERANCE_MS:.1f}ms)"
                    )

        assert not regressions, (
            "Benchmark regressions detected:\n  "
            + "\n  ".join(regressions)
        )
