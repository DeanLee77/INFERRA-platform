# INFERRA Platform - Agent Context

## Project Overview
Rule-based inference platform with a FastAPI backend. Python 3.10+. The codebase uses a port/adapter architecture: domain logic lives in `src/domain/`, contracts in `src/ports/`, inbound adapters in `src/adapters/inbound/`, outbound adapters in `src/adapters/outbound/`, and operational infrastructure in `src/infrastructure/`.

Accepted target architecture (P0.2 extraction in progress): the internal
`inferra-core==0.1.1` distribution, leaf contracts, and private executable
graph/node/token/parser/validation layer now exist under the `inferra_core`
import namespace. The security correction removed SymPy/string evaluation,
made declaration validation fail closed, and made topological cycles typed.
Define the narrow public compile/validation facade and rewire Platform for the
completed slice before moving fact-store/iteration/imports or inference/
provenance. `inferra-platform` remains the
authoritative API/persistence/audit runtime. Core must not import FastAPI,
SQLAlchemy, Redis, Celery, Fuseki, LLM, environment/secrets, AEGIS, AXIOM, or
other extensions. Follow
`docs/INFERRA_Core_Package_and_Runtime_Architecture.md`; preserve behavior with
golden vectors and installed-wheel tests during extraction.

## Architecture Conventions

### Port Pattern
- All ports use `ABCMeta` abstract base classes. Do not introduce `Protocol` ports.
- Ports use primitive types (`str`, `int`, `Set`, `Tuple`) to avoid circular imports with `src.domain.graph`.
- `DependencyGraphPort.get_child_groups()` returns `Tuple[Tuple[int, Tuple[str, ...]], ...]`. Port-compliant code destructures: `for dep_type_int, children_tuple in graph.get_child_groups(nid)`.
- `HyperAdjacencyGraph.get_typed_child_groups()` returns `Tuple[DependencyGroup, ...]` and is a domain convenience, not a port method.
- Graph node IDs are node names. There is no `get_node_name()` method.

### Feature Flags
- Located at `src/domain/state/feature_flags.py`.
- Flags are start-of-session sticky. Mid-session flips must be rejected or treated as session-ending corruption, not silently absorbed.
- Phase 1 flags: `use_hypergraph`, `legacy_iterate`, `layered_memory`, `ml_optimized_dfs`.
- Phase 2 flags: `async_sync_enabled`, `modular_imports`.
- Phase 3 flags: `hybrid_orchestrator`, `async_post_reasoning`, `prov_o_trace`, `enriched_api`.
- Phase 4 flags: `redis_session_store`, `llm_enhancements`, `strict_port_contracts`, `observability_enabled`, `auth_enabled`.
- Phase 5 flags: `abduction_enabled`, `induction_pipeline`, `reasoning_router`, `confidence_thresholds`.
- `layered_memory` must stay enabled for Phase 2+ truth maintenance.

### Structured Logging
- Production modules use `structlog`; do not add bare `print()` or raw `logging` calls.
- `inferra_core` is the exception: it creates neutral values/events and must not import Platform logging or Structlog.
- Core log context fields: `session_id`, `node_id`, `fact_source`, `correlation_id`.
- Extended fields used across later phases include `rule_name`, `import_depth`, `propagation_depth`, `source_hash`, `task_id`, and reasoning confidence metadata.

### Data Classes and Domain Types
- `DependencyGroup` is `NamedTuple(dep_type=DependencyType, children=FrozenSet[str])`.
- `HistoryRecord` is `@dataclass(frozen=True)` with `name`, `true_count`, `false_count`, computed rates, and `with_increment()`.
- `IterateContext` is a dataclass with `list_name`, `list_size`, `quantifier`, `progress: Dict[int, bool]`, and `is_initialised`.

### Expression Security
- `IS CALC` source is untrusted data and may use only documented arithmetic, comparison/ternary, and `ROUND`/`MAX`/`MIN` constructs.
- Never pass rule source to `eval`, `exec`, `compile`, SymPy string parsing, or another general-purpose evaluator.
- Preserve the bounded manual AST, fail-closed diagnostics, expression limits, and adversarial installed-wheel tests.

### FactStorePort Contract
- `set_fact(name, value, source=FactSource.ASSERTED)` has no `metadata` kwarg.
- `remove_fact(name, source=None)`, `invalidate_layer(source)`, `get_fact_sources(name)`, `get_overrides()`, `get_changed_since(timestamp)`, `get_layer_snapshot(source)`, `peek_in_layer(name, source)`, and `get_unified_view()` are wired through `LayeredFactStore`.
- Phase 2+ consumers such as `IterationEngine` and `IncrementalPropagator` must use the port contract rather than concrete store internals.

## Key Directories
- `packages/inferra-core/` - independently buildable internal Core distribution; leaf values/ports plus private graph/node/token/parser/validation and bounded expression implementations live here. It currently has no third-party runtime dependencies; `_internal` is not stable public API.
- `src/ports/` - Platform/runtime ports plus temporary re-exports of the five Core-owned ABC ports.
- `src/domain/graph/` - `HyperAdjacencyGraph`, graph serialization, sparse graph bridges, propagation, and legacy matrix compatibility.
- `src/domain/inference/` - inference engine, orchestrators, sessions, topological sorting, and backward chaining.
- `src/domain/iterate/` - `IterationEngine` implementing `IterationPort`.
- `src/domain/imports/` - rule-set import resolution, module registry, origins, and import matchers.
- `src/domain/reasoning/` - hybrid reasoning models, routing, tracing, pattern mining, and compiler pieces.
- `src/domain/state/` - `LayeredFactStore`, `FactSource`, feature flags, and session schema migration.
- `src/adapters/inbound/http/` - FastAPI routes, schemas, dependencies, middleware, and auth.
- `src/adapters/outbound/` - persistence, ontology/Fuseki, LLM, reasoning, and session adapters.
- `src/infrastructure/` - logging, secrets, guardrails, observability, metrics, and ontology-delta consumption.
- `src/tasks/` - Celery app and async rule/ontology/induction workers.
- `tests/contracts/` - port contract tests.
- `tests/benchmarks/`, `tests/load/`, `tests/chaos/` - performance, load, and resilience gates.

## Commands
- Run tests: `pytest`
- Run with coverage: `pytest --cov=src --cov-fail-under=97`
- Run benchmarks: `pytest tests/benchmarks/`
- Install Core first: `pip install -e "packages/inferra-core"`
- Install Platform dev dependencies: `pip install -e ".[dev,async,semantic,reasoning,observability]"`
- Build local images: `docker compose build api worker`

## Documentation Source of Truth
- Package/runtime architecture: `docs/INFERRA_Core_Package_and_Runtime_Architecture.md`
- Core extraction P0.1 baseline: `docs/INFERRA_Core_Extraction_P0_1_Baseline.md`
- Core extraction P0.2 progress: `docs/INFERRA_Core_Extraction_P0_2_Distribution.md`
- Cross-project ownership and priority: `docs/INFERRA_Cross_Project_Technical_Direction.md`
- Account/case hierarchy, ontology/provenance authority, graph versioning,
  retention, and AXIOM/AEGIS semantic boundaries:
  `docs/INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md`
- Current implementation status: `docs/IMPLEMENTATION_STATUS.md`
- Current roadmap: `docs/ROADMAP.md`
- Current operations runbook: `docs/OPERATIONS.md`
- Historical phase/future/enhancement plans live under `docs/archive/` and are not the active backlog.

## Phase Status
- Phase 1: complete and retained as the stable baseline.
- Phase 2: complete; async sync/import foundations are present.
- Phase 2.5: graph-first sparse bridge is implemented; `DependencyMatrix` is legacy compatibility only.
- Phase 3: orchestration, convergence, PROV-O, and ontology post-reasoning code paths are implemented; live local-prod proof remains the main validation risk.
- Phase 4: production hardening is partially implemented, including auth, Redis sessions, observability, load scripts, chaos scripts, and Dockerized monitoring.
- Phase 5: abduction, induction, routing, confidence thresholds, and LLM adapter work are implemented behind flags, with production promotion workflow still open.

## Session Schema
- `CURRENT_SCHEMA_VERSION = 5` in `src/domain/state/session_schema.py`.
- v1 adds fact-source tagging.
- v2 adds `NodeOrigin`, `iteration_state`, and `semantic_cache_loaded`.
- v3 adds convergence and ontology trace state.
- v4 adds ownership, feature flag snapshots, and API enrichment.
- v5 adds hybrid reasoning mode, confidence, hypothesis trace, induction job ID, and abduction counters.
