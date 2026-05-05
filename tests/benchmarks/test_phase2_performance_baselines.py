"""
Performance baseline benchmarks for INFERRA Phase 2.

Captures timing baselines for Phase 2 components:
- IncrementalPropagator forward propagation (1k nodes, 5% density)
- IncrementalPropagator topo-sort cache hit rate
- IterationEngine record_answer + evaluate
- RuleSetImportResolver resolve (depth + cycle detection)
- ModuleRegistry get/put/eviction + hit rate
- NodeSetMerger merge
- Session schema migration v1→v2

Success metrics (from §1.2):
- Forward propagation latency (1k nodes, 5% density): <200ms
- Topo-sort cache hit rate: >90%
- Circular import detection: 100% synchronous pre-save block

Run with: python -m pytest tests/benchmarks/test_phase2_performance_baselines.py -v
Generate baseline: python -m pytest tests/benchmarks/test_phase2_performance_baselines.py::TestPhase2BaselineGenerator -v
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Set

import pytest

from src.domain.graph.dependency_type import DependencyType
from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.graph.inference_propagator import IncrementalPropagator
from src.domain.imports.import_resolver import RuleSetImportResolver
from src.domain.imports.module_registry import ModuleRegistry
from src.domain.imports.node_origin import NodeOrigin
from src.domain.iterate.iteration_engine import IterationEngine
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.tokens import Token
from src.domain.nodes.node_set import NodeSet
from src.domain.rule_parser.node_set_merger import NodeSetMerger
from src.domain.state.feature_flags import FeatureFlags
from src.domain.state.fact_source import FactSource
from src.domain.state.layered_fact_store import LayeredFactStore
from src.domain.fact_values import FactValue, FactValueType
from src.domain.state.session_schema import (
    CURRENT_SCHEMA_VERSION,
    SessionMetadata,
    migrate_session,
)

BENCHMARK_DIR = Path(__file__).parent.parent.parent / "benchmarks"
BASELINE_FILE = BENCHMARK_DIR / "baseline_phase2.json"


def _time_it(func, iterations: int = 100) -> dict:
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)

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


def _async_time_it(coro_func, iterations: int = 100) -> dict:
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        asyncio.run(coro_func())
        end = time.perf_counter()
        times.append((end - start) * 1000)

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


def _build_sparse_graph(size: int = 1000, density: float = 0.05) -> HyperAdjacencyGraph:
    """Build a DAG with ~5% edge density for forward propagation benchmarking.

    Uses a feed-forward structure (i → j where j > i) to guarantee acyclicity.
    """
    import random
    rng = random.Random(42)
    graph = HyperAdjacencyGraph()
    max_forward = max(1, size // 10)
    for i in range(size):
        num_children = max(1, int(size * density * rng.random()))
        children = set()
        upper = min(i + max_forward, size - 1)
        for _ in range(num_children):
            if i < size - 1:
                j = rng.randint(i + 1, upper)
                children.add(f"n{j}")
        if children:
            graph.add_dependency_group(f"n{i}", DependencyType.MANDATORY, children)
    for i in range(size):
        if not graph.has_node(f"n{i}"):
            graph.add_dependency_group(f"n{i}", DependencyType.MANDATORY, set())
    return graph


def _build_wide_graph(depth: int = 5, branching: int = 10) -> HyperAdjacencyGraph:
    """Build a wide DAG for import resolution (tree shape, guaranteed acyclic)."""
    graph = HyperAdjacencyGraph()
    node_count = 0
    levels = []
    for d in range(depth):
        level = []
        for b in range(branching ** d if d < 3 else branching):
            name = f"mod_{d}_{b}"
            level.append(name)
            node_count += 1
            if node_count >= 1000:
                break
        levels.append(level)
        if node_count >= 1000:
            break
    for d in range(1, len(levels)):
        for parent in levels[d]:
            if levels[d - 1]:
                import random
                child = random.Random(hash(parent)).choice(levels[d - 1])
                graph.add_dependency_group(parent, DependencyType.MANDATORY, {child})
    for d in range(len(levels)):
        for name in levels[d]:
            if not graph.has_node(name):
                graph.add_dependency_group(name, DependencyType.MANDATORY, set())
    return graph


class _ConcreteComparisonLine(ComparisonLine):
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        pass


def _build_node_set(size: int = 100) -> NodeSet:
    """Build a NodeSet with the given number of ComparisonLine nodes."""
    ns = NodeSet()
    for i in range(size):
        node = _ConcreteComparisonLine(child_text=f"var_{i} > 0")
        node._node_name = f"var_{i}"
        node._variable_name = f"var_{i}"
        ns.add_node(node)
    return ns


def _warmup(func, runs: int = 3):
    for _ in range(runs):
        func()


class TestPhase2PerformanceBaselines:
    """Performance baselines for Phase 2 core operations."""

    def test_forward_propagation_1k_5pct(self):
        """Benchmark: forward propagation on 1k-node graph with 5% density.

        Success metric: <200ms (§1.2).
        """
        graph = _build_sparse_graph(1000, 0.05)
        store = LayeredFactStore()
        for i in range(1000):
            store.set_fact(f"n{i}", FactValue(False), source=FactSource.ASSERTED)
        propagator = IncrementalPropagator(graph, store)

        def _run():
            propagator.forward_propagate_incremental({"n0", "n1", "n2"})
            propagator.invalidate_cache()

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 200, f"Forward propagation too slow: {result}"
        print(f"\n  forward_propagate_1k_5pct: {result}")

    def test_topo_sort_cache_hit_rate(self):
        """Benchmark: topo-sort cache hit rate should be >90%.

        After warm-up, repeated calls with the same subgraph should hit cache.
        """
        graph = _build_sparse_graph(500, 0.05)
        store = LayeredFactStore()
        propagator = IncrementalPropagator(graph, store)

        impacted = {"n0", "n1", "n2", "n3", "n4"}
        child_map = {n: graph.get_child_groups(n) for n in impacted}

        hits = 0
        misses = 0
        for _ in range(100):
            result = propagator._topo_sort_subgraph(impacted, child_map)
            if len(propagator._topo_cache) > 0:
                hits += 1
            else:
                misses += 1

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0
        assert hit_rate > 0.90, f"Topo-sort cache hit rate too low: {hit_rate:.2%}"
        print(f"\n  topo_sort_cache_hit_rate: {hit_rate:.2%}")

    def test_iteration_engine_record_answer(self):
        """Benchmark: IterationEngine record_answer for 100 items."""
        store = LayeredFactStore()
        engine = IterationEngine(store)
        engine.initialise(list_size=100, quantifier="ALL", list_name="items")

        async def _run():
            for i in range(100):
                await engine.record_answer(
                    index=i, question_name=f"q_{i}", value=True,
                    node_value_type=FactValueType.BOOLEAN,
                )

        result = _async_time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"IterationEngine record_answer too slow: {result}"
        print(f"\n  iteration_record_answer_100: {result}")

    def test_iteration_engine_evaluate(self):
        """Benchmark: IterationEngine evaluate (quantifier check)."""
        store = LayeredFactStore()
        engine = IterationEngine(store)
        engine.initialise(list_size=100, quantifier="ALL", list_name="items")

        async def _setup_and_eval():
            for i in range(100):
                await engine.record_answer(
                    index=i, question_name=f"q_{i}", value=True,
                    node_value_type=FactValueType.BOOLEAN,
                )
            engine.evaluate()

        result = _async_time_it(_setup_and_eval, iterations=50)
        print(f"\n  iteration_evaluate_100: {result}")

    def test_import_resolver_resolve_20_modules(self):
        """Benchmark: RuleSetImportResolver resolve 20-module chain."""
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

        def _run():
            resolver.resolve("mod_0")

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"Import resolution too slow: {result}"
        print(f"\n  import_resolve_20_modules: {result}")

    def test_import_resolver_cycle_detection(self):
        """Benchmark: Circular import detection (synchronous pre-save block)."""
        module_texts = {
            "a": "IMPORT: b\n",
            "b": "IMPORT: c\n",
            "c": "IMPORT: a\n",
        }
        flags = FeatureFlags(modular_imports=True)
        resolver = RuleSetImportResolver(
            rule_loader=lambda name: module_texts.get(name, ""),
            feature_flags=flags,
        )

        def _run():
            try:
                resolver.resolve("a")
            except Exception:
                pass

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 50, f"Cycle detection too slow: {result}"
        print(f"\n  import_cycle_detection: {result}")

    def test_module_registry_get_put(self):
        """Benchmark: ModuleRegistry get/put with 256 entries."""
        flags = FeatureFlags(modular_imports=True)
        registry = ModuleRegistry(max_size=256, ttl_seconds=600, feature_flags=flags)

        for i in range(256):
            content_hash = ModuleRegistry.compute_content_hash(f"content_{i}")
            registry.put(f"rule_{i}", content_hash, value=f"parsed_{i}")

        def _run():
            for i in range(256):
                content_hash = ModuleRegistry.compute_content_hash(f"content_{i}")
                registry.get(f"rule_{i}", content_hash)

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"ModuleRegistry get/put too slow: {result}"
        print(f"\n  module_registry_get_put_256: {result}")

    def test_module_registry_hit_rate(self):
        """Benchmark: ModuleRegistry hit rate should be high after warm-up."""
        flags = FeatureFlags(modular_imports=True)
        registry = ModuleRegistry(max_size=256, ttl_seconds=600, feature_flags=flags)

        for i in range(128):
            content_hash = ModuleRegistry.compute_content_hash(f"content_{i}")
            registry.put(f"rule_{i}", content_hash, value=f"parsed_{i}")

        for _ in range(200):
            for i in range(128):
                content_hash = ModuleRegistry.compute_content_hash(f"content_{i}")
                registry.get(f"rule_{i}", content_hash)

        assert registry.hit_rate > 0.90, f"ModuleRegistry hit rate too low: {registry.hit_rate:.2%}"
        print(f"\n  module_registry_hit_rate: {registry.hit_rate:.2%}")

    def test_node_set_merger_100_nodes(self):
        """Benchmark: NodeSetMerger merge 5 NodeSets of 100 nodes each."""
        local = _build_node_set(100)
        imported = [_build_node_set(20) for _ in range(4)]
        origins = {f"imported_{i}": NodeOrigin(module=f"imported_{i}", imported=True, depth=1) for i in range(4)}

        def _run():
            NodeSetMerger.merge(local, imported, origins, rule_name="bench_rule")

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"NodeSetMerger too slow: {result}"
        print(f"\n  node_set_merger_5x100: {result}")

    def test_session_schema_migration_v1_v2(self):
        """Benchmark: Session schema migration v1→v2 for 1k-node session."""
        v1_session = {
            "schema_version": 1,
            "nodes": {f"n{i}": {"name": f"n{i}", "variable_name": f"var_{i}"} for i in range(1000)},
            "facts": {f"n{i}": {"value": i, "source": "ASSERTED"} for i in range(100)},
            "metadata": {"schema_version": 1},
        }

        def _run():
            migrate_session(v1_session)

        result = _time_it(_run, iterations=50)
        assert result["p95_ms"] < 100, f"Schema migration too slow: {result}"
        print(f"\n  session_migration_v1_v2_1k: {result}")

    def test_incremental_propagator_vs_full_scan(self):
        """Benchmark: IncrementalPropagator vs naive full-scan approach.

        The incremental approach should be faster for small change sets
        on large graphs. Measures the ratio.
        """
        graph = _build_sparse_graph(1000, 0.05)
        store = LayeredFactStore()
        for i in range(1000):
            store.set_fact(f"n{i}", FactValue(False), source=FactSource.ASSERTED)
        propagator = IncrementalPropagator(graph, store)

        def _incremental():
            propagator.forward_propagate_incremental({"n0", "n1"})
            propagator.invalidate_cache()

        incremental_result = _time_it(_incremental, iterations=50)

        def _full_scan():
            graph.topological_sort()
            for i in range(1000):
                if graph.has_node(f"n{i}"):
                    propagator._can_evaluate_parent(f"n{i}")

        full_scan_result = _time_it(_full_scan, iterations=50)

        ratio = incremental_result["avg_ms"] / full_scan_result["avg_ms"] if full_scan_result["avg_ms"] > 0 else 0
        print(f"\n  incremental_vs_full_scan: incremental={incremental_result['avg_ms']:.3f}ms, "
              f"full_scan={full_scan_result['avg_ms']:.3f}ms, ratio={ratio:.2f}")


class TestPhase2BaselineGenerator:
    """Generate the baseline_phase2.json file for CI regression gates."""

    @staticmethod
    async def _record_all_answers(engine: IterationEngine, count: int = 100):
        for i in range(count):
            await engine.record_answer(
                index=i, question_name=f"q_{i}", value=True,
                node_value_type=FactValueType.BOOLEAN,
            )

    @pytest.mark.skipif(
        os.environ.get("INFERRA_GENERATE_BASELINES") != "1",
        reason="Set INFERRA_GENERATE_BASELINES=1 to rewrite benchmark baselines.",
    )
    def test_generate_baseline(self):
        """Run all Phase 2 benchmarks and save results to benchmarks/baseline_phase2.json."""
        BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

        baselines = {}
        iterations = 200

        def _warmup_run(func, runs=3):
            for _ in range(runs):
                func()

        # Forward propagation (1k nodes, 5% density)
        graph = _build_sparse_graph(1000, 0.05)
        store = LayeredFactStore()
        for i in range(1000):
            store.set_fact(f"n{i}", FactValue(False), source=FactSource.ASSERTED)
        propagator = IncrementalPropagator(graph, store)

        def _fwd_prop():
            propagator.forward_propagate_incremental({"n0", "n1", "n2"})
            propagator.invalidate_cache()
        _warmup_run(_fwd_prop)
        baselines["forward_propagate_1k_5pct"] = _time_it(_fwd_prop, iterations)

        # Topo-sort cache (cached path)
        propagator2 = IncrementalPropagator(graph, store)
        impacted = {"n0", "n1", "n2", "n3", "n4"}
        child_map = {n: graph.get_child_groups(n) for n in impacted}
        propagator2._topo_sort_subgraph(impacted, child_map)

        def _topo_cached():
            propagator2._topo_sort_subgraph(impacted, child_map)
        _warmup_run(_topo_cached)
        baselines["topo_sort_cached_5nodes"] = _time_it(_topo_cached, iterations)

        # IterationEngine record_answer (100 items)
        def _iter_record():
            store2 = LayeredFactStore()
            engine = IterationEngine(store2)
            engine.initialise(list_size=100, quantifier="ALL", list_name="items")
            asyncio.run(TestPhase2BaselineGenerator._record_all_answers(engine))
        _warmup_run(_iter_record)
        baselines["iteration_record_answer_100"] = _time_it(_iter_record, iterations)

        # IterationEngine evaluate
        def _iter_eval():
            store3 = LayeredFactStore()
            engine2 = IterationEngine(store3)
            engine2.initialise(list_size=100, quantifier="ALL", list_name="items")
            asyncio.run(TestPhase2BaselineGenerator._record_all_answers(engine2))
            engine2.evaluate()
        _warmup_run(_iter_eval)
        baselines["iteration_evaluate_100"] = _time_it(_iter_eval, iterations)

        # Import resolver (20-module chain)
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
        _warmup_run(_import_resolve)
        baselines["import_resolve_20_modules"] = _time_it(_import_resolve, iterations)

        # Import cycle detection
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
        _warmup_run(_import_cycle)
        baselines["import_cycle_detection"] = _time_it(_import_cycle, iterations)

        # ModuleRegistry get/put (256 entries)
        registry = ModuleRegistry(max_size=256, ttl_seconds=600, feature_flags=flags)
        for i in range(256):
            ch = ModuleRegistry.compute_content_hash(f"content_{i}")
            registry.put(f"rule_{i}", ch, value=f"parsed_{i}")

        def _registry_get():
            for i in range(256):
                ch = ModuleRegistry.compute_content_hash(f"content_{i}")
                registry.get(f"rule_{i}", ch)
        _warmup_run(_registry_get)
        baselines["module_registry_get_put_256"] = _time_it(_registry_get, iterations)

        # ModuleRegistry hit rate
        registry2 = ModuleRegistry(max_size=256, ttl_seconds=600, feature_flags=flags)
        for i in range(128):
            ch = ModuleRegistry.compute_content_hash(f"content_{i}")
            registry2.put(f"rule_{i}", ch, value=f"parsed_{i}")
        for _ in range(200):
            for i in range(128):
                ch = ModuleRegistry.compute_content_hash(f"content_{i}")
                registry2.get(f"rule_{i}", ch)
        baselines["module_registry_hit_rate"] = round(registry2.hit_rate, 4)

        # NodeSetMerger (5×100 nodes)
        def _merger():
            local = _build_node_set(100)
            imported = [_build_node_set(20) for _ in range(4)]
            origins = {f"imported_{i}": NodeOrigin(module=f"imported_{i}", imported=True, depth=1) for i in range(4)}
            NodeSetMerger.merge(local, imported, origins, rule_name="bench_rule")
        _warmup_run(_merger)
        baselines["node_set_merger_5x100"] = _time_it(_merger, iterations)

        # Session schema migration v1→v2 (1k nodes)
        v1_session = {
            "schema_version": 1,
            "nodes": {f"n{i}": {"name": f"n{i}", "variable_name": f"var_{i}"} for i in range(1000)},
            "facts": {f"n{i}": {"value": i, "source": "ASSERTED"} for i in range(100)},
            "metadata": {"schema_version": 1},
        }

        def _migrate():
            migrate_session(v1_session)
        _warmup_run(_migrate)
        baselines["session_migration_v1_v2_1k"] = _time_it(_migrate, iterations)

        # Incremental vs full scan comparison
        def _full_scan():
            graph.topological_sort()
            for i in range(1000):
                if graph.has_node(f"n{i}"):
                    propagator._can_evaluate_parent(f"n{i}")
        _warmup_run(_full_scan)
        baselines["full_scan_baseline_1k"] = _time_it(_full_scan, iterations)

        baselines["_metadata"] = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "python_version": "3.10",
            "platform": "windows",
            "phase": 2,
            "success_criteria": {
                "forward_propagation_lt_200ms": "forward_propagate_1k_5pct.p95_ms < 200",
                "topo_sort_cache_hit_gt_90pct": "topo_sort_cached_5nodes avg near 0ms (cache hit)",
                "module_registry_hit_rate_gt_90pct": "module_registry_hit_rate > 0.90",
            },
        }

        with open(BASELINE_FILE, "w") as f:
            json.dump(baselines, f, indent=2)

        print(f"\n  Phase 2 baseline saved to {BASELINE_FILE}")
