# INFERRA Document / Implementation Alignment Audit

Date: 2026-05-10
Latest verification refresh: 2026-05-12
Scope: `docs/` excluding `docs/reference/`

## Executive Result

The current implementation is broadly aligned with the reconciled phase-plan direction, but several documents still mix three different meanings of "done":

1. code exists,
2. targeted tests pass,
3. full production acceptance has passed under live services/load.

Update after follow-up implementation: `src/domain/inference/topo_sort.py` is now explicitly deprecated. It remains only as a compatibility facade that converts legacy matrix inputs to `DependencyGraphPort` and delegates traversal to `MLTopologicalSortStrategy`. The private dense-matrix helper algorithms have been removed.

Reference-project policy confirmed on 2026-05-12: the current `inferra-platform` implementation is the behavioral source of truth. `C:\Users\user\.pi\projects\PALOS-PyRest\` is an implementation reference only; useful ideas are adapted into the current port/adapter architecture rather than copied wholesale.

## Latest Verification Evidence

| Area | Current evidence |
| --- | --- |
| Reference examples | 30 `vea*` / `mrca*` examples validate and parse after strict declaration/reference checks |
| Offline regression suite | `pytest -q`: 2444 passed, 69 skipped |
| Benchmarks | `pytest tests/benchmarks/ -q`: 22 passed, 3 skipped |
| Live service slice | 81 live Docker/service tests passed |
| Phase readiness | `scripts/verify_phase_readiness.ps1 -SkipUnitTests -SkipFrontend` passed against compose |
| k6 smoke | Dockerized 20-VU smoke passed |
| k6 production gate | Dockerized 500-VU production profile passed for 1 minute on the compose network: 100.00% checks, 0.00% HTTP failures, 197.99ms overall p95 |
| Phase 4 hardening slice | Targeted hardening batch passed: 132 passed, 5 skipped; reasoning routes passed: 14 passed; `lint-imports --config .importlinter`: 2 kept, 0 broken |
| Phase 4 restart chaos | `powershell -ExecutionPolicy Bypass -File tests/chaos/run_phase4_chaos_suite.ps1` passed locally for Redis, Fuseki, and worker restarts |
| Topology regression slice | `pytest tests/domain/graph/test_ws3_ws4_persistence_topology.py tests/domain/inference/test_topo_sort.py tests/domain/inference/test_topo_sort_with_record.py -q`: 67 passed |
| Coverage gate | `pytest --cov=src --cov-fail-under=97 -q`: 2441 passed, 72 skipped, 97.01% total coverage |
| Phase 5 dedicated acceptance | `pytest tests/integration/test_phase5_acceptance.py -q --run-integration`: 7 passed |
| LLM hardening proof | `pytest tests/adapters/outbound/llm/test_real_llm_orchestrator.py -q`: retry, circuit-open fallback, and half-open recovery pass |
| Reference-inspired local enhancements | Declaration validator, ontology post-reasoner, trace extraction, ontology-delta, optional LLM abduction, OTel log/span bridge, orchestrator factory, local-prod Compose secrets, and k6 profiles have focused proof. Latest focused completion slice: `pytest tests/adapters/outbound/reasoning/test_llm_abduction_adapter.py tests/adapters/outbound/llm/test_real_llm_orchestrator.py tests/infrastructure/test_otel_logging_bridge.py tests/infrastructure/test_orchestrator_factory.py tests/infrastructure/test_small_coverage_edges.py tests/infrastructure/test_phase_readiness_artifacts.py -q`: 46 passed |

Coverage is now current after the topology and graph-adapter reconciliation pass.

## Topology Decision

Recommendation: new code should bypass `topo_sort.py` and use `MLTopologicalSortStrategy` directly with a `DependencyGraphPort`.

| Functionality | Recommended owner | Current alignment |
| --- | --- | --- |
| Public BFS/topological order from legacy matrix inputs | `TopologicalSort` facade -> `MatrixToHyperGraphAdapter` -> `MLTopologicalSortStrategy.sort()` | Aligned |
| Public DFS from legacy matrix inputs | `TopologicalSort` facade -> `MatrixToHyperGraphAdapter` -> `MLTopologicalSortStrategy.sort_depth_first()` | Aligned |
| DFS with `HistoryRecord` | `TopologicalSort` facade -> `MLTopologicalSortStrategy.sort_depth_first(records)` | Aligned |
| Impacted-subgraph propagation ordering | `IncrementalPropagator` using `graphlib.TopologicalSorter` | Still appropriate |
| Private matrix helper tests | Removed; behavior covered through graph/strategy tests | Aligned |

`MLTopologicalSortStrategy` is the right shared strategy for DFS, DFS-with-history, and public BFS/topological ordering. `graphlib.TopologicalSorter` should remain for strict impacted-subgraph topological sorting inside propagation because that code needs cycle behavior and graphlib's release semantics, not ML child-prioritization.

## Document-by-Document Alignment

| Document | Alignment status | Notes |
| --- | --- | --- |
| `fastapi_conversion_plan.md` | Aligned as historical completion note | FastAPI migration is done; old 47-test count is historical and should not be used as current readiness evidence |
| `furture name of engine INFERRA.md` | Aligned as branding note | No implementation checklist impact |
| `fuseki_connection.md` | Partially stale operational note | Manual local Fuseki startup is useful, but Docker Compose is now the meaningful runtime path |
| `INFERRA Fuseki_connection.md` | Partially stale operational note | Contains standalone Docker commands; should eventually point to compose as the preferred INFERRA setup |
| `INFERRA Redis run in container.md` | Partially stale operational note | Standalone Redis command works, but compose is now authoritative for integrated testing |
| `INFERRA_Architecture_Combined_Recommendations_revised_V2.md` | Historical blueprint, not current status | Many unchecked tasks are already implemented elsewhere; label as superseded or keep only as architecture background |
| `INFERRA_Consolidated_Architecture_and_Implementation_Plan.md` | Mostly aligned as consolidated blueprint | It says ready for implementation, but much of it is already implemented; should be labeled historical/consolidated architecture |
| `INFERRA_Phase1_Bug_Analysis_and_Library_Research.md` | Historical research | No direct implementation blocker identified in this audit |
| `INFERRA_Phase1_Implementation_Plan.md` | Aligned | Phase 1 remains complete; schema references are historical because runtime schema is now v5 |
| `INFERRA_Phase2_Implementation_Plan.md` | Aligned with carry-forward blockers | Phase 2 is code-complete; Task #8 is now Phase 2.5 bridge work, with topology public paths graph-backed |
| `INFERRA_Phase2_5_DependencyMatrix_Bridge_Plan.md` | Aligned and bridge-complete | Topology is graph-backed through `MLTopologicalSortStrategy`; private dense-matrix helpers are removed; imported node collision handling, rule-file graph edge-list persistence, deprecation boundaries, and full 1k/5k/10k sparse benchmark acceptance are validated; the 500-VU load evidence is tracked under Phase 4 |
| `INFERRA_Phase3_Implementation_Plan.md` | Partially aligned | Orchestrator/convergence/PROV-O pieces exist; async post-reasoning publisher/task, ontology delta consumer, convergence metrics, and orchestrator factory now exist; live local-prod Compose proof and `origin_module` enrichment still need path-specific validation |
| `INFERRA_Phase4_Implementation_Plan.md` | Partially aligned | Redis, Docker, observability, frontends, API key/JWT/rate limits/CSRF/session ownership, 20-VU k6 smoke, local-compose 500-VU k6 production gate, multi-profile k6 runner, alert rules, import-linter CI contracts, local restart chaos, local-prod Compose secret overlay, OTel log/span correlation, and real LLM retry/circuit proof exist; staging chaos/load repetition, external secret-manager integration, OIDC/RBAC policy, and final legacy/flag retirement remain open |
| `INFERRA_Phase5_Implementation_Plan.md` | Aligned with evidence-scored acceptance | Section 7 is reconciled after dedicated acceptance; trace mining/compiler, optional LLM abduction, and NodeSet declaration validation are now implemented locally; live/staging induction candidate-quality, persistent promotion workflow, and external sign-off remain partial |
| `INFERRA_Production_Readiness_and_Tech_Stack.md` | Aligned as operational readiness register | Includes current local evidence, RC hook, decision register, and legacy-retirement register |
| `future extension plan for the Induction and abduction implementation.md` | Partially superseded | Phase 5 implements several items; full trace mining, promotion workflow, API/UI confidence override surface, and production induction hardening remain open |
| `future INFERRA GraphRAG Integration Plan.md` | Aligned as deferred future plan | No production GraphRAG implementation exists; deferral is correct |
| `inferra_prompt.md` | Advisory/prompt reference | No implementation blocker identified |
| `INFERRA_Rule_Syntax_Dictionary.md` | Mostly aligned | Declaration/reference validation was strengthened; examples should continue to be checked against this dictionary |
| `IterateLine recommendations.md` | Mostly superseded by Phase 2 work | Iterate engine delegation exists; keep only as background unless more legacy iterate cleanup is planned |
| `suggested_enhancement_for_phase1_implementation.md` | Historical recommendation | Superseded by Phase 1 plan/status |
| `suggested_enhancement_for_phase2_implementation.md` | Historical recommendation | Superseded by Phase 2 and Phase 2.5 plan/status |
| `suggested_enhancement_for_phase3_implementation.md` | Historical recommendation | Superseded by Phase 3 plan/status |
| `suggested_enhancement_for_phase4_implementation.md` | Historical recommendation | Superseded by Phase 4 plan/status |
| `suggested_enhancement_for_phase5_implementation.md` | Historical recommendation | Superseded by Phase 5 plan/status |

## Implementation Changes Made During This Audit

| Area | Change |
| --- | --- |
| Topology facade | Public BFS, DFS, and DFS-with-history paths in `topo_sort.py` now adapt matrix inputs into a graph and delegate to `MLTopologicalSortStrategy` |
| ML DFS fallback | `MLTopologicalSortStrategy.sort_depth_first()` now performs deterministic DFS even when no records are supplied |
| Regression coverage | Added DFS no-record and no-runtime-node-id regressions for topology compatibility paths |
| Fact source documentation | Updated `FactSource` docstring to include `LEARNED` and `HYPOTHETICAL` |
| Topology deprecation | Removed private dense-matrix helper algorithms from `topo_sort.py`; it is now a deprecated adapter facade only |
| Parser graph default | `IScanFeeder.create_dependency_graph()` now returns the NodeSet graph instead of rebuilding from a legacy matrix |
| NodeSet matrix payloads | `NodeSet.set_dependency_matrix()` converts legacy payloads into graph state and discards the payload when runtime IDs are available |
| Compatibility coverage | Added adapter coverage for graph-derived matrix query wrappers, unmapped legacy matrix entries, and lazy graph initialization |
| Imported node keys | `NodeSetMerger` now qualifies imported nodes with canonical module names, preserves local raw names, rekeys imported graph edges, and avoids runtime-ID collisions during merge |
| Rule-file graph persistence | New and updated rule files now persist an envelope containing raw rule text, graph edge-list JSON, schema metadata, and `source_hash`, while legacy raw file blobs still decode normally |
| DependencyMatrix deprecation | Legacy matrix construction, node-level matrix shim import, `NodeSet.get/set_dependency_matrix()`, and `RuleSetParser.create_dependency_matrix()` now emit `DeprecationWarning`; sanctioned adapters suppress internal bridge warnings |
| Sparse graph benchmark acceptance | Added `benchmarks/baseline_phase2_5_sparse.json` and 1k/5k/10k sparse graph benchmarks with 1k legacy-matrix adapter parity and 5k/10k dense-matrix projection comparisons |
| Graph mutation performance | Added a per-parent outgoing index to `HyperAdjacencyGraph`, reducing 10k sparse graph build from tens of seconds to sub-second baseline territory |
| Phase 5 acceptance reconciliation | Added a dedicated acceptance test file, converted Phase 5 Section 7 to `[x]` / `[~]`, and closed local proof for induction idempotency/circuit, router confidence precedence, summary/trace enrichment, and unknown `FactSource` fallback |
| LLM external-call hardening | Added retry, circuit-open fallback, half-open recovery, and `.env.example` configuration for the real LLM adapter |
| Production hooks | Added `scripts/verify_release_candidate.ps1`, `INFERRA_Production_Decision_Register.md`, `INFERRA_Legacy_Retirement_Register.md`, and `FeatureFlags.legacy_retirement_report()` |
| Reference-inspired deterministic safety | Added `src/services/declaration_validator.py` and integrated parser/graph-backed declaration checking into `RuleValidationService` without changing the current text-level contract |
| Reference-inspired ontology loop | Added `src/tasks/ontology_post_reasoner.py`; completed facts are projected to Fuseki, emitted as Redis ontology-delta events, and left for main-process semantic-layer injection via `OntologyDeltaConsumer` |
| Reference-inspired LLM abduction | Added `src/adapters/outbound/reasoning/llm_abduction_adapter.py` behind `INFERRA_ABDUCTION_ADAPTER=llm` and `INFERRA_LLM_ENHANCEMENTS`, with prompt sanitization, graph-candidate filtering, and empty fallback when unavailable |
| Reference-inspired observability and ops | Added `src/infrastructure/otel_logging_bridge.py`, `src/infrastructure/orchestrator_factory.py`, `docker-compose.prod.yml`, local secret initialization scripts, and a multi-profile k6 runner |

## Remaining Implementation Gaps

| Priority | Gap |
| --- | --- |
| P1 | Phase 3 ontology pre/post-reasoning now has local code/tests but still needs live local-prod Compose workflow proof, not just service availability |
| P1 | Phase 4 production hardening remains incomplete: staging chaos/load repetition, external secret-manager integration, OIDC/RBAC policy, and final legacy/flag retirement |
| P1 | Phase 5 induction hardening remains partial: persistent promotion workflow validation, API/UI confidence override surface, live candidate-quality drills, load/chaos |
| P2 | Operational docs for Redis/Fuseki should converge on Docker Compose as the preferred integrated setup |
| P2 | Historical architecture/recommendation documents should be marked "superseded" or linked to this audit to avoid checklist confusion |

## Supersession and Acceptance Policy

Decision confirmed on 2026-05-11:

1. Old blueprint/recommendation documents should be edited in place and marked superseded, while remaining available as historical context.
2. Phase 5 Section 7 acceptance criteria should be converted from unchecked boxes to `[x]` / `[~]` only after a dedicated Phase 5 acceptance test pass.
3. Phase and future plans should be updated when required features are implemented, but production acceptance checklists remain evidence-driven.
