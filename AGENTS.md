# INFERRA PyRest — Agent Context

## Project Overview
Rule-based inference engine with FastAPI backend. Python 3.10+. Structured as a port/adapter architecture with domain logic in `src/domain/`, port contracts in `src/ports/`, and adapters in `src/adapters/`.

## Architecture Conventions

### Port Pattern
- All ports use `ABCMeta` (abstract base class) — **never** `Protocol`.
- Ports use primitive types (`str`, `int`, `Set`, `Tuple`) to avoid circular imports with `src.domain.graph`.
- `get_child_groups()` on `DependencyGraphPort` returns `Tuple[Tuple[int, Tuple[str, ...]], ...]` (primitive tuples), NOT `Tuple[DependencyGroup, ...]`. Use destructuring: `for dep_type_int, children_tuple in graph.get_child_groups(nid)`.
- `HyperAdjacencyGraph` has `get_typed_child_groups()` returning `Tuple[DependencyGroup, ...]` — this is a domain-level convenience, NOT part of the port. Port-compliant code must NOT call it.
- Graph node IDs ARE node names (name-based keys). There is no `get_node_name()` method.

### Feature Flags
- Located at `src/domain/state/feature_flags.py`.
- Flags are **start-of-session sticky** — cannot flip mid-session. Violations produce warning log + session termination, not silent corruption.
- Current flags:
  - `use_hypergraph` (default `False`, env `INFERRA_USE_HYPERGRAPH`)
  - `legacy_iterate` (default `True`, env `INFERRA_LEGACY_ITERATE`)
  - `layered_memory` (default `True`, env `INFERRA_LAYERED_MEMORY`) — **must be `True`** for Phase 2+ features
  - `ml_optimized_dfs` (default `False`, env `INFERRA_ML_OPTIMIZED_DFS`)
- Phase 2 flags: `async_sync_enabled` (env `INFERRA_ASYNC_SYNC_ENABLED`), `modular_imports` (env `INFERRA_MODULAR_IMPORTS`)

### Structured Logging
- All modules use `structlog`, never bare `logging` or `print()`.
- Mandatory fields: `session_id`, `node_id`, `fact_source`, `correlation_id`.
- Phase 2 additional fields: `rule_name`, `import_depth`, `propagation_depth`, `source_hash`.

### Data Classes
- `DependencyGroup` is `NamedTuple(dep_type=DependencyType, children=FrozenSet[str])` — immutable.
- `HistoryRecord` is `@dataclass(frozen=True)` with `name`, `true_count`, `false_count` + computed properties `true_rate`/`false_rate`/`total` + `with_increment()` factory.
- `IterateContext` is `@dataclass` with `list_name`, `list_size`, `quantifier`, `progress: Dict[int, bool]`, `is_initialised: bool`.

### FactStorePort Contract
- `set_fact(name, value, source=FactSource.ASSERTED)` — **NO** `metadata` kwarg.
- `remove_fact(name, source=None)`, `invalidate_layer(source)`, `get_fact_sources(name)`, `get_overrides()`, `get_changed_since(timestamp)`, `get_layer_snapshot(source)`, `peek_in_layer(name, source)`, `get_unified_view()` — all fully wired in `LayeredFactStore`.
- `_overrides` and `get_changed_since()` are wired from Phase 1; Phase 2 consumers (`IterationEngine`, `IncrementalPropagator`) use them correctly.

## Key Directories
- `src/ports/` — ABC port contracts (primitive types only)
- `src/domain/graph/` — `HyperAdjacencyGraph`, `DependencyGroup`, `DependencyType`, `CyclicGraphError`, `IncrementalPropagator`
- `src/domain/inference/` — `InferenceEngine`, `topo_sort.py` (`bfs_topological_sort`, `dfs_topological_sort`, `dfs_topological_sort_with_record`)
- `src/domain/iterate/` — `IterationEngine` (implements `IterationPort`)
- `src/domain/imports/` — `RuleSetImportResolver`, `ModuleRegistry`, `NodeOrigin`, `import_matchers`
- `src/domain/nodes/` — `Node`, `IterateLine`, `IterateContext`, `HistoryRecord`, `node_id_utils`
- `src/domain/state/` — `LayeredFactStore`, `FactSource`, `FeatureFlags`, `SessionMetadata`/`session_schema.py`
- `src/domain/rule_parser/` — `RuleSetScanner`, `RuleSetParser`, `RuleSetReader`, `NodeSetMerger`, tokenizer
- `src/domain/models/` — `create_file.py`, `update_rule_description.py`, `update_rule_details.py` (moved from `src/domain/` in Phase 1)
- `src/adapters/outbound/persistence/` — `InMemoryHistoryRecordStore`, `SqlAlchemyHistoryRecordStore`
- `src/adapters/outbound/ontology/` — `FusekiAdapter`, `SemanticCache`, `InferraToRdfCompiler`, `type_bridge`
- `src/adapters/inbound/http/routes/` — `system.py`, `metrics.py`, `sync_imports.py`
- `src/tasks/` — `celery_app.py`, `rule_sync.py`, `event_publisher.py`
- `tests/contracts/` — Port contract tests (`FactStorePort`, `DependencyGraphPort`, `IterationPort`)
- `tests/benchmarks/` — Performance baselines (`baseline_v0.json`, `baseline_phase2.json`)

## Commands
- Run tests: `pytest`
- Run with coverage: `pytest --cov=src --cov-fail-under=97`
- Run benchmarks: `pytest tests/benchmarks/`
- Install: `pip install -e ".[dev]"`

## Phase Status
- Phase 1: **Complete** (v3.0 signed off). 1,472 tests, 96.5% branch coverage.
- Phase 2: **Complete** (v3.1). All 29 tasks done (Task #8 deferred to Phase 2.5). See `INFERRA_Phase2_Implementation_Plan.md`.
- Phase 2.5: **Plan ready**. See `INFERRA_Phase2_5_DependencyMatrix_Bridge_Plan.md`.

## Session Schema
- `CURRENT_SCHEMA_VERSION = 2` (in `src/domain/state/session_schema.py`)
- Phase 2 bumped to 2 with `NodeOrigin` + `iteration_state` migration.
