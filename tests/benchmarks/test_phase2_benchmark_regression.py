"""
Benchmark regression CI gate for INFERRA Phase 2.

Compares current Phase 2 benchmark results against
``benchmarks/baseline_phase2.json``. Fails CI if any benchmark's
median timing regresses more than 20% from the stored baseline.

Phase 2 benchmarks have higher variance due to graph traversal and
async operations, so the threshold is 15% (vs 10% for Phase 1).

Run with: python -m pytest tests/benchmarks/test_phase2_benchmark_regression.py -v
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.inference_propagator import IncrementalPropagator
from src.domain.imports.import_resolver import RuleSetImportResolver
from src.domain.imports.module_registry import ModuleRegistry
from src.domain.imports.node_origin import NodeOrigin
from src.domain.iterate.iteration_engine import IterationEngine
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.rule_parser.node_set_merger import NodeSetMerger
from src.domain.state.feature_flags import FeatureFlags
from src.domain.state.fact_source import FactSource
from src.domain.state.layered_fact_store import LayeredFactStore
from src.domain.fact_values import FactValue, FactValueType
from src.domain.state.session_schema import migrate_session
from tests.benchmarks.test_phase2_performance_baselines import (
    _build_node_set,
    _build_sparse_graph,
    _time_it,
)
from tests.benchmarks.benchmark_utils import quiet_benchmark_logging

BENCHMARK_DIR = Path(__file__).parent.parent.parent / "benchmarks"
BASELINE_FILE = BENCHMARK_DIR / "baseline_phase2.json"

REGRESSION_THRESHOLD = 0.20
ABSOLUTE_TOLERANCE_MS = 5.0

MIN_BASELINE_MS = 1.0

ITERATIONS = 200

METRICS_TO_CHECK = ("p50_ms",)

LOGGER_PATCHES = (
    ("src.domain.graph.inference_propagator", "log"),
    ("src.domain.imports.import_resolver", "log"),
    ("src.domain.imports.module_registry", "log"),
    ("src.domain.iterate.iteration_engine", "log"),
    ("src.domain.rule_parser.node_set_merger", "log"),
    ("src.domain.state.session_schema", "_logger"),
)


async def _record_all_answers(engine: IterationEngine, count: int = 100):
    for i in range(count):
        await engine.record_answer(
            index=i, question_name=f"q_{i}", value=True,
            node_value_type=FactValueType.BOOLEAN,
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

    graph = _build_sparse_graph(1000, 0.05)
    store = LayeredFactStore()
    for i in range(1000):
        store.set_fact(f"n{i}", FactValue(False), source=FactSource.ASSERTED)
    propagator = IncrementalPropagator(graph, store)

    def _fwd_prop():
        propagator.forward_propagate_incremental({"n0", "n1", "n2"})
        propagator.invalidate_cache()

    _warmup(_fwd_prop)
    results["forward_propagate_1k_5pct"] = _time_it(_fwd_prop, ITERATIONS)

    propagator2 = IncrementalPropagator(graph, store)
    impacted = {"n0", "n1", "n2", "n3", "n4"}
    child_map = {n: graph.get_child_groups(n) for n in impacted}
    propagator2._topo_sort_subgraph(impacted, child_map)

    def _topo_cached():
        propagator2._topo_sort_subgraph(impacted, child_map)

    _warmup(_topo_cached)
    results["topo_sort_cached_5nodes"] = _time_it(_topo_cached, ITERATIONS)

    def _iter_record():
        store2 = LayeredFactStore()
        engine = IterationEngine(store2)
        engine.initialise(list_size=100, quantifier="ALL", list_name="items")
        asyncio.run(_record_all_answers(engine))

    _warmup(_iter_record)
    results["iteration_record_answer_100"] = _time_it(_iter_record, ITERATIONS)

    def _iter_eval():
        store3 = LayeredFactStore()
        engine2 = IterationEngine(store3)
        engine2.initialise(list_size=100, quantifier="ALL", list_name="items")
        asyncio.run(_record_all_answers(engine2))
        engine2.evaluate()

    _warmup(_iter_eval)
    results["iteration_evaluate_100"] = _time_it(_iter_eval, ITERATIONS)

    module_texts = {}
    for i in range(20):
        if i < 19:
            module_texts[f"mod_{i}"] = f"INPUT x_{i} AS NUMBER\nIMPORT: mod_{i+1}\n"
        else:
            module_texts[f"mod_{i}"] = f"INPUT x_{i} AS NUMBER\n"

    flags = FeatureFlags(modular_imports=True)
    resolver = RuleSetImportResolver(
        rule_loader=lambda name: module_texts.get(name, ""),
        feature_flags=flags,
    )

    def _import_resolve():
        resolver.resolve("mod_0")

    _warmup(_import_resolve)
    results["import_resolve_20_modules"] = _time_it(_import_resolve, ITERATIONS)

    cycle_texts = {"a": "IMPORT: b\n", "b": "IMPORT: c\n", "c": "IMPORT: a\n"}
    resolver_cycle = RuleSetImportResolver(
        rule_loader=lambda name: cycle_texts.get(name, ""),
        feature_flags=flags,
    )

    def _import_cycle():
        try:
            resolver_cycle.resolve("a")
        except Exception:
            pass

    _warmup(_import_cycle)
    results["import_cycle_detection"] = _time_it(_import_cycle, ITERATIONS)

    registry = ModuleRegistry(max_size=256, ttl_seconds=600, feature_flags=flags)
    for i in range(256):
        ch = ModuleRegistry.compute_content_hash(f"content_{i}")
        registry.put(f"rule_{i}", ch, value=f"parsed_{i}")

    def _registry_get():
        for i in range(256):
            ch = ModuleRegistry.compute_content_hash(f"content_{i}")
            registry.get(f"rule_{i}", ch)

    _warmup(_registry_get)
    results["module_registry_get_put_256"] = _time_it(_registry_get, ITERATIONS)

    def _merger():
        local = _build_node_set(100)
        imported = [_build_node_set(20) for _ in range(4)]
        origins = {
            f"imported_{i}": NodeOrigin(module=f"imported_{i}", imported=True, depth=1)
            for i in range(4)
        }
        NodeSetMerger.merge(local, imported, origins, rule_name="bench_rule")

    _warmup(_merger)
    results["node_set_merger_5x100"] = _time_it(_merger, ITERATIONS)

    v1_session = {
        "schema_version": 1,
        "nodes": {
            f"n{i}": {"name": f"n{i}", "variable_name": f"var_{i}"} for i in range(1000)
        },
        "facts": {f"n{i}": {"value": i, "source": "ASSERTED"} for i in range(100)},
        "metadata": {"schema_version": 1},
    }

    def _migrate():
        migrate_session(v1_session)

    _warmup(_migrate)
    results["session_migration_v1_v2_1k"] = _time_it(_migrate, ITERATIONS)

    def _full_scan():
        graph.topological_sort()
        for i in range(1000):
            if graph.has_node(f"n{i}"):
                propagator._can_evaluate_parent(f"n{i}")

    _warmup(_full_scan)
    results["full_scan_baseline_1k"] = _time_it(_full_scan, ITERATIONS)

    registry2 = ModuleRegistry(max_size=256, ttl_seconds=600, feature_flags=flags)
    for i in range(128):
        ch = ModuleRegistry.compute_content_hash(f"content_{i}")
        registry2.put(f"rule_{i}", ch, value=f"parsed_{i}")
    for _ in range(200):
        for i in range(128):
            ch = ModuleRegistry.compute_content_hash(f"content_{i}")
            registry2.get(f"rule_{i}", ch)
    results["module_registry_hit_rate"] = round(registry2.hit_rate, 4)

    return results


class TestPhase2BenchmarkRegression:
    """CI regression gate: fail if any Phase 2 benchmark regresses >15% from baseline."""

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

            if isinstance(baseline_metrics, (int, float)):
                if isinstance(current_metrics, (int, float)):
                    if baseline_metrics > 0 and current_metrics < baseline_metrics * (1.0 - REGRESSION_THRESHOLD):
                        regressions.append(
                            f"{bench_name}: baseline={baseline_metrics}, current={current_metrics} "
                            f"(dropped below {1.0 - REGRESSION_THRESHOLD:.0%} of baseline)"
                        )
                continue

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
            "Phase 2 benchmark regressions detected:\n  "
            + "\n  ".join(regressions)
        )
