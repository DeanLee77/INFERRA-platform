# INFERRA Legacy Retirement Register

Status: active migration control
Last updated: 2026-07-15

This register names compatibility paths that are still present for regression safety but should not be treated as production architecture.

Current implementation status is consolidated in `IMPLEMENTATION_STATUS.md`; original phase-specific migration plans are archived under `archive/phase-plans/`.

## Runtime Flags

| Flag | Current default | Production expectation | Retirement state | Enforcement hook |
| --- | --- | --- | --- | --- |
| `INFERRA_USE_HYPERGRAPH` | `true` | Must remain `true` | Unsupported `false` is rejected at API/worker startup and session creation; direct construction remains for migration tests | `validate_runtime_feature_flags()` and `FeatureFlags.legacy_retirement_report()` |
| `INFERRA_LAYERED_MEMORY` | `true` | Must remain `true` | Unsupported `false` is rejected because Phase 2+ truth-maintenance requires layered memory | `validate_runtime_feature_flags()` and session-creation tests |
| `INFERRA_LEGACY_ITERATE` | `true` | Should be `false` for production candidates once final iterate parity is signed off | Deprecated compatibility path | `FeatureFlags.legacy_retirement_report()` and RC evidence |
| `INFERRA_ML_OPTIMIZED_DFS` | `false` | Deployment decision | Retained optional strategy; history reaches `MLTopologicalSortStrategy` only when enabled | Session-service strategy-selection tests |
| `INFERRA_STRICT_PORT_CONTRACTS` | `true` | Must remain `true` until the environment name is removed | Runtime off switch is obsolete because CI port/import contracts are unconditional; compatibility snapshot entry is pending retirement | Startup validation plus unconditional CI architecture gate |

## Deprecated Compatibility APIs

| API or module | Current use | Production direction | Evidence |
| --- | --- | --- | --- |
| `src.domain.inference.topo_sort` | Compatibility facade | New code should call `MLTopologicalSortStrategy` with `DependencyGraphPort` | Topology regression slice and audit |
| `DependencyMatrix` construction | Legacy payload and adapter bridge | Keep only as graph-owned compatibility format | Deprecation warnings and guardrail tests |
| `src.domain.nodes.dependency*` shims | Legacy imports | New production code imports from `src.domain.graph` | `tests/infrastructure/test_guardrails.py` |
| `NodeSet.get_dependency_matrix()` / `set_dependency_matrix()` | Legacy serialization bridge | Prefer graph edge-list persistence | Deprecation warnings and rule-file graph payload tests |

## Exit Criteria

The compatibility paths above can be removed only after:

- reference examples still parse and validate,
- graph edge-list persistence can read all supported rule files,
- iterate parity is signed off with `INFERRA_LEGACY_ITERATE=false`,
- import-linter and guardrail tests still pass,
- a migration note is added to the release notes.

Until then, compatibility paths remain available but visibly deprecated.
