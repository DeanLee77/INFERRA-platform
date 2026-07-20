# INFERRA Production Readiness and Technology Stack

Status: implementation advisory and executable readiness plan
Date: 2026-05-06
Last architecture update: 2026-07-20
Last execution audit: 2026-07-17

This document records the recommended production stack for INFERRA and the
non-LLM work that remains after the current phase implementation pass. It is
intended to sit beside `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`, and
`OPERATIONS.md` as the practical "how do we ship this?" decision record.
The old phase plans are archived under `archive/phase-plans/`.

`inferra-platform` is the behavioral source of truth. `PALOS-PyRest` may be used
as an implementation reference, but adopted features must be adapted to the
current ABC-port, graph-first, layered-fact-store, and feature-flag contracts.

The accepted target architecture now creates an internal, independently
buildable `inferra-core` Python distribution for the deterministic kernel while
retaining `inferra-platform` as the official authoritative runtime. This target
is partially implemented: P0.1 inventory/behavior freezing and P0.2a-P0.2b's
internal 0.1.1 distribution, leaf contracts, private executable
graph/node/token/parser/validation layer, compatibility re-exports, and
installed-wheel parser proof are complete. The 0.1.1 bounded evaluator,
fail-closed validation, typed cycles, zero runtime dependencies, and adversarial
security gates are also complete. The public compile/validation facade and
Platform vertical integration are next; state/import/inference/provenance
extraction and complete application-service rewiring remain. Evidence is in
`INFERRA_Core_Extraction_P0_1_Baseline.md` and
`INFERRA_Core_Extraction_P0_2_Distribution.md`.
`INFERRA_Core_Package_and_Runtime_Architecture.md` controls that boundary and
supersedes earlier library-versus-service and frontend-framework
recommendations in this document.

`INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md` controls the
minimum tenant/account/case/execution identity, immutable rule and case graph
versions, fact source-versus-authority policy, AXIOM/AEGIS semantic boundaries,
and indefinite-default configurable retention. The current implementation does
not yet satisfy that contract.

## Executive Recommendation

INFERRA should be treated as a hybrid reasoning platform, not a simple REST
wrapper around a rule engine. The best implementation path is to keep the
Python domain core clean and deterministic, run all slow semantic/inductive
work out of the request path, and invest in proof-grade observability and
repeatable verification.

| Area | Recommendation | Why this is the best fit | Current repo alignment | Remaining action |
| --- | --- | --- | --- | --- |
| Deterministic package | Internal `inferra-core` Python wheel/source distribution with a small facade | Makes the engine embeddable and enforces infrastructure/product independence without duplicating production authority | P0.1 and P0.2a-P0.2b complete; internal 0.1.1 adds a bounded expression interpreter, fail-closed validation, typed cycles, zero runtime dependencies, package/adversarial tests, exact leaf re-exports, and isolated installed-wheel proof | Define the public compile/validation facade and rewire the completed Platform slice first; then move fact-store/iteration/imports and inference/provenance and complete whole-engine/reproducible-artifact proof |
| Backend API | FastAPI, Pydantic v2, Uvicorn in Docker | Strong async API ergonomics, typed request models, OpenAPI by default | Already implemented | Add production worker/process sizing per deployment target |
| Domain architecture | ABCMeta ports with explicit adapters | Enforces implementation contracts at instantiation and matches project convention | Already implemented | Keep Protocol out of ports |
| Graph runtime | HyperAdjacencyGraph as canonical graph, DependencyMatrix only as compatibility format | Graph-native traversal scales better than dense N x N scans for sparse rule graphs | Implemented as default runtime path; graph package now owns DependencyMatrix, Dependency, and DependencyType | Keep guardrails until legacy node-level graph shims are fully retired |
| Dependency type model | Canonical `inferra_core.DependencyType` using IntFlag-style bitmask composition | Preserves existing AND, OR, NOT, KNOWN, MANDATORY combinations without brittle enum coercion | Implemented since Core 0.1.0 and present in 0.1.1; both `src.domain.graph.dependency_type` and `src.domain.nodes.dependency_type` are compatibility paths | Keep mixed-mask regression coverage active, especially around ML sort paths |
| Node identity | Use stable node names/IDs as graph keys | Avoids non-portable numeric IDs and makes persistence, RDF, and trace lookup stable | Current graph is name-keyed | Do not reintroduce numeric node_id in new code |
| Async jobs | Celery + Redis broker/result backend | Good fit for induction, RDF sync, ontology post-reasoning, background promotion workflows | Docker compose includes worker and Redis; induction has retry, DLQ, source-hash idempotency, post-reasoning has Redis delta events, and circuit/retry proof exists | Run live candidate-quality and Fuseki-read/post-reasoning drills in local-prod Compose and staging |
| Semantic store | PostgreSQL-authoritative audit/outbox and graph catalogue plus Apache Jena Fuseki derived RDF/PROV-O projection | Separates durable governed events from critical rebuildable semantic query views | Fuseki and projection code exist; account/case ownership, immutable normal-path case graphs, retention policy, durable audit contract, and reconciliation remain incomplete | Add append-only audit events, ownership-scoped graph catalogue, outbox, immutable rule/case versions, authorization, rebuild/reconciliation, indefinite-default versioned retention, backup/restore and namespace governance |
| Account/case decision identity | Tenant/workspace scope plus opaque Account, Case, and Execution identifiers on every governed decision | Gives authorization, audit, retention, and graph projection a real domain boundary without making Core a CRM | Not implemented end to end; current sessions/runs are insufficient | Add migrations, constraints, services, OpenAPI/generated-client fields, negative cross-account tests, and product ownership mappings before Core release |
| Fact authority | Store source, verification, eligibility, scope, validity, derivation, and supersession separately | Preserves all provenance without treating every historical conclusion or assertion as present truth | Layered fact source exists; authority behavior is inconsistent across product modes | Enforce the accepted AXIOM deterministic and AEGIS typed semantic-gate policies server-side |
| Persistence | PostgreSQL for durable sessions, rules, audit index; Redis for hot session/cache | PostgreSQL is the durable source; Redis is operationally fast but ephemeral by default | Docker compose includes both | Avoid pickle for untrusted state; prefer JSON/msgpack schemas |
| Observability | OpenTelemetry traces, Prometheus metrics, Grafana dashboards, Loki logs | Hybrid reasoning needs explainability at system and domain levels | Grafana, Prometheus, Loki, Promtail, OTel collector, dashboards, and Prometheus alert rules exist | Tune alert thresholds against staging traffic |
| Frontends | Existing Svelte 5/SvelteKit AXIOM and AEGIS repositories with hardened Express BFFs and generated TypeScript clients | Preserves substantial product work while keeping browsers and hand-written contracts outside the authority boundary | Separate candidate repositories exist; AXIOM and AEGIS have independent blockers | Remove obsolete embedded prototypes from release assumptions; harden BFFs and pass each product's quality/security gates |
| Load and chaos | k6 load smoke, multi-profile k6 runs, Docker compose service interruption drills | Prevents confidence based only on unit tests | Smoke, production gate, and smoke/load/stress/spike/soak runner artifacts are present | Run in CI/staging with threshold history |
| CI quality gate | GitHub Actions for backend coverage, frontend checks, Docker build | Makes phase plan acceptance repeatable | Added by this readiness package | Add protected-branch enforcement |

## Latest Execution Evidence - 2026-07-17

These results supersede older "previous run" language and should be used with
`IMPLEMENTATION_STATUS.md` as the current implementation baseline.

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend regression | Pass | `pytest -q`: 3,471 passed, 70 skipped, 146 warnings in 309.00 seconds after the Core 0.1.1 security and numeric-precision corrections |
| Backend coverage | Pass | Current combined instrumented run plus the targeted new adapter-branch test covers 20,932/21,579 statements (97.0017%) against the unchanged 97% threshold; no exclusions were added |
| Core 0.1.1 security correction | Pass | 33 package tests; 221 focused Platform compatibility/security tests; 99-package lock without SymPy/mpmath; clean external wheel with no runtime requirements or forbidden modules; adversarial Python expression rejected; typed cycle/fail-closed guards active |
| Benchmarks | Pass | `pytest tests/benchmarks/ -q`: 22 passed, 3 skipped |
| Reference examples | Pass | 30 `vea*` / `mrca*` examples validate and parse under the stricter declaration/reference validator |
| Topology bridge | Pass | `pytest tests/domain/graph/test_ws3_ws4_persistence_topology.py tests/domain/inference/test_topo_sort.py tests/domain/inference/test_topo_sort_with_record.py -q`: 67 passed; legacy `TopologicalSort` matrix entry points now emit deprecation warnings |
| Phase 2.5 import/persistence slice | Pass | Imported node collision handling now uses canonical qualified names and rule-file writes persist graph edge-list envelopes; `pytest tests/domain/imports tests/domain/rule_parser/test_node_set_merger.py tests/domain/rule_parser/test_rule_set_parser.py tests/domain/rule_parser/test_rule_set_scanner.py tests/domain/graph/test_ws3_ws4_persistence_topology.py tests/services/test_rule_service.py tests/adapters/outbound/persistence/test_rule_repository.py -q`: 299 passed |
| DependencyMatrix deprecation | Pass | Legacy matrix construction, node-level matrix shim import, `NodeSet.get/set_dependency_matrix()`, and `RuleSetParser.create_dependency_matrix()` now emit `DeprecationWarning`; sanctioned graph/matrix adapters suppress internal bridge noise |
| Phase 2.5 sparse graph benchmarks | Pass | `benchmarks/baseline_phase2_5_sparse.json` captures 1k/5k/10k sparse graph build, topo, ML topo/DFS, back-propagation, and edge iteration; 1k legacy matrix adapter parity passes and 5k/10k compare graph edges against dense matrix projections |
| Docker readiness | Pass | `docker compose up -d --build`; API, Redis, Postgres, Fuseki, Celery worker, Prometheus, Grafana, Loki, Promtail, and OTel collector running; Redis `6379` and Fuseki `3030` published for local checks |
| Live service smoke | Pass | `/api/v1/health` reports Redis, Celery, Fuseki, database, Z3, and induction workers as `ok`; Redis `PING`, internal Fuseki `$/ping`, Celery `inspect ping`, and PostgreSQL readiness passed |
| Phase readiness script | Pass | `scripts/verify_phase_readiness.ps1 -SkipUnitTests -SkipFrontend` passed against the live compose stack, including metrics, reasoning smoke, and Grafana health |
| Frontend checks | Pass | `npm.cmd test` and `npm.cmd run check` passed in both `frontends/inferra-rule-studio` and `frontends/inferra-ai-harness` |
| k6 smoke | Pass | Dockerized k6 at 20 VUs for 1 minute passed |
| k6 production-load gate | Pass | `powershell -ExecutionPolicy Bypass -File tests/load/run_k6_production_gate.ps1 -Vus 500 -Duration 1m` passed through the compose network at `http://api:8000`: 100.00% checks, 0.00% HTTP failures, overall p95 197.99ms; endpoint p95s were goal 203.9ms, abduct 220.09ms, disabled induction 167.83ms, and live 160.49ms. The low-rate metrics probe uses median + p99 thresholds; latest metrics median was 5.8ms and max was 654.41ms |
| Phase 4 hardening slice | Pass | Redis session handoff/state persistence, stale session conflict handling, API-key owner scoping, HS256 JWT auth, opt-in CSRF protection, Prometheus alert artifacts, secret-template checks, chaos-suite artifacts, route metrics, and import-linter CI wiring pass: targeted pytest hardening batch: 132 passed, 5 skipped; reasoning route batch: 14 passed; `lint-imports --config .importlinter`: 2 kept, 0 broken |
| Prometheus alert rules | Pass | `docker run --rm --entrypoint promtool -v ${PWD}/monitoring/prometheus/rules:/rules:ro prom/prometheus:v2.54.1 check rules /rules/inferra-alerts.yml`: 6 rules found |
| Phase 4 restart chaos | Pass | `powershell -ExecutionPolicy Bypass -File tests/chaos/run_phase4_chaos_suite.ps1` passed locally against Compose, restarting Redis, Fuseki, and worker with health recovery |
| Phase 5 dedicated acceptance | Pass | `pytest tests/integration/test_phase5_acceptance.py -q --run-integration`: 7 passed; covers Abduction/Induction ports, bounded/read-only Z3 abduction, FactSource/session migration, router threshold precedence, context mode switches, induction idempotency/circuit breaker, and sandbox rejection |
| LLM hardening proof | Pass | `pytest tests/adapters/outbound/llm/test_real_llm_orchestrator.py -q`: real LLM adapter now has bounded timeout, retry, circuit-open fallback, and half-open recovery tests without network calls |
| Reference-inspired local hardening | Pass | `pytest tests/services/test_declaration_validator.py tests/tasks/test_ontology_post_reasoner.py tests/domain/reasoning/test_trace_extractor.py tests/infrastructure/test_ontology_delta_consumer.py -q`: 33 passed; covers NodeSet declaration validation, async ontology post-reasoning payload/Fuseki/delta behavior, trace extraction, and Redis delta consumption |
| Reference-learning completion slice | Pass | `pytest tests/adapters/outbound/reasoning/test_llm_abduction_adapter.py tests/adapters/outbound/llm/test_real_llm_orchestrator.py tests/infrastructure/test_otel_logging_bridge.py tests/infrastructure/test_orchestrator_factory.py tests/infrastructure/test_small_coverage_edges.py tests/infrastructure/test_phase_readiness_artifacts.py -q`: 46 passed; covers optional LLM abduction, OTel log/span correlation, orchestrator factory, local-prod Compose secrets, and k6 profiles |
| Release-candidate hooks | Present | `scripts/verify_release_candidate.ps1`, `docs/INFERRA_Production_Decision_Register.md`, `docs/INFERRA_Legacy_Retirement_Register.md`, and `FeatureFlags.legacy_retirement_report()` define the remaining external and legacy-retirement gates |

The 500-VU production-load gate is now closed for the local Docker Compose production profile. The passing run used the direct compose network, ASGI middleware paths, separated low-rate operational probes, production log level, OpenTelemetry trace sampling, a Prometheus-scrape-aligned metrics payload cache, and a 3-second interactive user think time.

## Stack Comparisons

### Frontend Framework

| Option | Strengths | Weaknesses | INFERRA fit | Recommendation |
| --- | --- | --- | --- | --- |
| Static JavaScript | Very low dependency cost, easy to serve | Weak typing, limited graph-editor ecosystem, harder to scale UI state | Good prototype layer | Keep only for demos and smoke tools |
| React + TypeScript + Vite | Strong graph/editor ecosystem, React Flow, mature testing and query tooling | A rewrite would discard substantial current Svelte product work | Viable for a future product only if evidence justifies migration | Not the accepted AXIOM/AEGIS direction |
| Vue + TypeScript + Vite | Excellent ergonomics, good state patterns, smaller-feeling app code | Graph editor ecosystem is thinner than React Flow | Good alternative for operational dashboards | Viable, but second choice for graph drawing |
| SvelteKit | Fast, concise, and already used by both first-party products | Requires disciplined server/auth, generated contracts, testing and graph-performance work | Accepted AXIOM/AEGIS implementation | Keep; harden existing products rather than migrate frameworks before release |

### Graph Storage and Reasoning Runtime

| Option | Strengths | Weaknesses | INFERRA fit | Recommendation |
| --- | --- | --- | --- | --- |
| DependencyMatrix | Simple dense representation, legacy-compatible | O(N^2) memory, row-scan traversal, awkward subgraphs | Keep only as graph-owned compatibility payload and bridge format | Retire from hot paths |
| HyperAdjacencyGraph | Sparse adjacency, typed child groups, natural parent lookup | Needs parity tests for every legacy traversal mode | Best runtime graph | Canonical domain graph |
| NetworkX | Rich algorithms, fast prototyping | Adds dependency and object-model mismatch | Useful for offline analysis | Do not put in hot runtime unless justified |
| graphlib.TopologicalSorter | Standard library, deterministic topological sort | No ML child ordering by itself | Good impacted-subgraph helper for propagation | Keep in `IncrementalPropagator`; public topo facade routes through `MLTopologicalSortStrategy` |

### Async and Workflow Execution

| Option | Strengths | Weaknesses | INFERRA fit | Recommendation |
| --- | --- | --- | --- | --- |
| Inline request execution | Simple, easy to debug | Blocks user path, poor for induction/ontology jobs | Only for deterministic deduction | Keep hot path small |
| Celery + Redis | Mature Python job queue, retries, rate limits, monitoring | Requires broker operations discipline | Already in compose and code | Recommended now |
| Dramatiq + Redis | Simpler than Celery | Less feature-complete for complex workflows | Good future simplification candidate | Consider later only |
| Temporal | Strong durable workflows and retries | Operationally heavier, new programming model | Excellent for enterprise promotion pipelines | Future option after product-market clarity |

### Semantic and Retrieval Layer

| Option | Strengths | Weaknesses | INFERRA fit | Recommendation |
| --- | --- | --- | --- | --- |
| Fuseki derived projection | Standards-based RDF/SPARQL, PROV-O friendly and rebuildable | Cannot atomically own the relational decision transaction | Good semantic query/visualization projection | Keep as a versioned projection; PostgreSQL audit/outbox remains authoritative |
| PostgreSQL + pgvector | One database for relational and vector search | Less RDF-native | Good retrieval adjunct | Add when GraphRAG moves beyond blueprint |
| Qdrant | Strong vector search and filtering | Additional service to operate | Good for AI harness context retrieval | Consider for production GraphRAG |
| Neo4j | Great property graph UX | Different model from RDF and current stack | Could confuse source-of-truth boundaries | Not recommended unless product pivots |

## Remaining Work Matrix

This table separates implementation work that can be finished inside this
repository from work that depends on external operational decisions or LLM
provider readiness.

| Work item | Type | Status after this package | Non-LLM blocker | Recommended next action |
| --- | --- | --- | --- | --- |
| Internal Core distribution | Architecture/release | P0.1 and P0.2a-P0.2b plus the 0.1.1 security correction complete: independent wheel/source, leaf contracts, private parser/graph/validation, bounded expression interpreter, fail-closed validation and typed cycles pass package and installed-wheel gates; public facade integration and state/import/inference/provenance remain | P0 before Core 1.0 | Prove the narrow public compile/validation facade and Platform vertical slice first; then finish remaining extraction, rewiring and whole-engine equivalence/reproducibility/hash proof |
| Backend unit, integration, regression coverage | Code verification | Green in latest full coverage run: 2441 passed, 72 skipped, 97.01% coverage | None known | Keep 97% coverage gate in CI |
| AXIOM release gates | Separate product verification | Build/audit pass, but type-check, unit, lint and formatting gates fail in the inspected candidate | Blocks AXIOM 1.0, not API-only Core | Fix current Svelte product and test against generated Core client; do not substitute old Platform prototypes |
| AEGIS release gates | Separate product verification | Type-check, unit, main/embed build and audit pass; lint/format plus security, persistence, synthetic-state and licensing blockers remain | Blocks AEGIS 1.0, not Core | Establish authenticated application backend/BFF and AEGIS-owned persistence consuming Core APIs/events |
| Live Docker smoke | Runtime verification | Green in current run against Redis, Fuseki, Postgres, worker, OTel, Prometheus, Grafana, API health, metrics, and reasoning smoke | Local Docker must be running | Keep `scripts/verify_phase_readiness.ps1` in CI/staging smoke |
| Load smoke | Runtime verification | 20-VU Dockerized k6 smoke passes; 500-VU Dockerized production gate passes in the local compose profile; multi-profile smoke/load/stress/spike/soak runner is available | Staging/CI must preserve equivalent worker, network, and threshold policy | Keep smoke, profile, and production-gate threshold history in CI/staging |
| Redis session handoff | Runtime verification | Cross-store handoff preserves mutated session state and rejects stale saves; HTTP question/answer/reset paths now persist session mutations | Live multi-worker staging repetition still recommended | Keep Redis handoff tests in CI and repeat against staging |
| Chaos smoke | Runtime verification | Compose-scoped reversible drill plus Phase 4 restart-suite wrapper are present, artifact-tested, and passed locally for Redis, Fuseki, and worker restarts | Staging repetition still required | Run `tests/chaos/run_phase4_chaos_suite.ps1` in staging on a scheduled basis |
| Core ontology audit projection | Runtime verification | Rule/case artifact and Fuseki code exist, but the normal path is not a PostgreSQL-outbox-backed immutable account/case graph contract | P0 before Core 1.0 | Prove decision commit -> outbox -> versioned Fuseki graph -> authorized read -> reconciliation/rebuild in local-prod and staging |
| Ontology post-reasoning/materialization | Runtime verification | Local code and unit tests exist for Fuseki projection, Redis delta events, DLQ, and convergence delta metrics | P0 only before a product profile may let semantic facts affect decisions; otherwise disabled | Add the product authority, fact eligibility, stale/failure, and live workflow gates before activation |
| CI gate | Automation | GitHub workflow includes backend coverage, import-linter, frontend checks, and Docker build | Repository must enable Actions and branch protection | Make CI required before merge |
| Production auth | Security | API key, HS256 JWT, owner scoping, session-owner enforcement, rate limiting, and opt-in CSRF are implemented and tested | OIDC/RBAC/tenant policy still require product decision | Use API key or HS256 JWT for protected environments; defer OIDC to enterprise auth work |
| Secrets management | Security | `.env.example`, `docker-compose.prod.yml`, `secrets/init-secrets.sh`, `secrets/init-secrets.ps1`, and local Docker secret files support a local production rehearsal path | Need target platform: local, cloud, Kubernetes, or managed PaaS | Move real secrets to platform secret manager before production traffic |
| Production frontend integration | Product engineering | AXIOM and AEGIS Svelte candidates exist in separate repositories | Package-backed API profiles, generated clients, BFF security and product-specific quality gates | Keep Svelte; generate contracts and harden the existing repositories |
| GraphRAG production | Future plan | Blueprint exists, partial semantic foundation exists | Need corpus, ontology governance, vector-store choice, evaluation set | Start as separate Phase 7 project |
| LLM reasoning | Future/optional | Null/fallback flows implemented; real adapter has timeout, retry, circuit-open fallback, half-open recovery proof, cost/metrics/tracing, and optional LLM abduction behind feature flags | Provider/model/key/evaluation policy | Keep disabled until model gate is approved |

## Best-Practice Architecture Rules

| Rule | Keep doing | Avoid | Reason |
| --- | --- | --- | --- |
| Package boundary | Keep pure deterministic logic in `inferra-core`; inject time, IDs, settings and source ports | FastAPI, SQLAlchemy, Redis, Celery, Fuseki, LLM, env/secret or extension imports in Core | Makes local embedding reproducible without turning every consumer into a second Platform |
| Runtime authority | Keep migrations, transactions, identity, rule revisions, sessions, durable audit/outbox and ontology projection in Platform | Treating an in-process library result as a durable governed service record | A library computes; the runtime establishes authority and operations |
| Port contracts | ABCMeta ports; the five deterministic ports are canonical in `inferra_core` with temporary `src/ports` re-exports | `typing.Protocol` for domain ports | Explicit inheritance and instantiation-time enforcement are valuable here |
| Graph traversal | Use `DependencyGraphPort`, `HyperAdjacencyGraph`, or graph strategy objects | Direct matrix scans in new runtime code | Keeps Phase 2.5 migration direction intact |
| Matrix compatibility | Treat `DependencyMatrix` APIs as deprecated compatibility only | New runtime code constructing or setting matrices directly | Warnings plus guardrails keep legacy loading available while making accidental use visible |
| ML topological sort | Standalone strategy taking graph + history store | Embedding history ordering into graph core | Keeps the graph deterministic and testable |
| Identity | Stable node names/IDs in graph, RDF, trace, history | New numeric `node_id` lookups | Reduces migration and persistence ambiguity |
| Bitmask dependency type | Preserve composable masks | Flattening to incompatible enum values | Existing rule semantics depend on composition |
| Structured logging | `structlog` with mandatory fields and OTel trace/span correlation | `print()` or bare logging | Traceability matters for regulated reasoning |
| Slow work | Worker jobs, event/delta handoff, idempotency | Mutating hot session state from workers directly | Protects session consistency |
| External calls | Circuit breakers, fallbacks, metrics | Blocking unbounded provider calls | Keeps deterministic deduction reliable |

## Production Checklist

| Gate | Required evidence | Local command |
| --- | --- | --- |
| Core package | Reproducible wheel/sdist, installed-artifact tests, forbidden-import checks, package-content audit and golden-vector equivalence | `python scripts/verify_inferra_core_distribution.py`; package build/isolation passes, while reproducibility and whole-engine equivalence remain P0.4 |
| Backend correctness | Unit, integration, regression tests pass with coverage | `pytest --cov=src --cov-fail-under=97` |
| Frontend correctness | Both frontend checks and tests pass | `npm.cmd test`; `npm.cmd run check` in each frontend |
| Docker readiness | Compose stack is healthy | `docker compose up -d --build`; `docker compose ps` |
| Live API smoke | Health, metrics, abduction, disabled LLM fallback pass | `powershell -ExecutionPolicy Bypass -File scripts/verify_phase_readiness.ps1 -SkipUnitTests` |
| Load smoke | P95 and failure thresholds pass | `k6 run tests/load/k6_api_smoke.js`, `powershell -ExecutionPolicy Bypass -File tests/load/run_k6_docker.ps1`, `powershell -ExecutionPolicy Bypass -File tests/load/run_k6_profiles.ps1 -Profile smoke`, and `powershell -ExecutionPolicy Bypass -File tests/load/run_k6_production_gate.ps1 -Vus 500 -Duration 1m` |
| Chaos smoke | System recovers from controlled service interruption | `powershell -ExecutionPolicy Bypass -File tests/chaos/docker_chaos_smoke.ps1 -Service redis -Action pause` then `-Action unpause`; broader restart suite: `powershell -ExecutionPolicy Bypass -File tests/chaos/run_phase4_chaos_suite.ps1` |
| Import boundary | No new runtime imports from legacy node-level graph modules; DependencyMatrix remains graph-owned compatibility only; import-linter contracts pass | `pytest tests/infrastructure/test_guardrails.py`; `lint-imports --config .importlinter` |
| Phase 5 acceptance | Dedicated acceptance pass for abduction, induction, router thresholds, FactSource migration, context mode switches, and sandbox rejection | `pytest tests/integration/test_phase5_acceptance.py -q --run-integration` |
| Release candidate | Aggregated RC evidence, including coverage, Phase 5 acceptance, benchmarks, guardrails, import-linter, optional production flag enforcement, frontend, live smoke, load, and chaos | `powershell -ExecutionPolicy Bypass -File scripts/verify_release_candidate.ps1` |

## Immediate Technical Recommendations

| Priority | Recommendation | Why |
| --- | --- | --- |
| P0 | Extract and prove the internal `inferra-core` package before freezing the service release | This is the accepted reusable-kernel boundary and must not be retrofitted after clients depend on broad internals |
| P0 | Implement the package-backed Core API profile and generated clients immediately after extraction | Separates local Python embedding from the official service contract |
| P0 | Keep `HyperAdjacencyGraph` canonical and keep matrix guardrails active | This protects the largest migration decision already made |
| P0 | Add CI branch protection around the coverage and frontend checks | Prevents the phase plans from becoming aspirational documents |
| P0 | Use the production decision and legacy-retirement registers as release blockers | Keeps external decisions and compatibility debt visible instead of hiding them in phase-plan prose |
| P1 | Run load and chaos scripts in a staging compose environment weekly | The biggest remaining non-LLM risk is operational behavior under service interruption |
| P1 | Convert session serialization to a schema-safe format if any untrusted input can reach it | Pickle-style state is not a production security boundary |
| P1 | Freeze Rule Studio API shapes before rewriting the UI | Avoids churn in the highest-novelty frontend |
| P2 | Tune alert thresholds for reasoning and queue health | Alert rules now exist; operators still need staging-calibrated thresholds and notification routing |
| P2 | Start GraphRAG as an evaluation harness first, not a production feature | Retrieval quality must be measured before it drives answers |

## References

- FastAPI deployment and Docker guidance: https://fastapi.tiangolo.com/deployment/docker/
- Vite production build guidance: https://vite.dev/guide/build
- OpenTelemetry Python instrumentation: https://opentelemetry.io/docs/languages/python/instrumentation/
- Redis security and ACLs: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
- Celery monitoring guide: https://docs.celeryq.dev/en/stable/userguide/monitoring.html
- k6 thresholds: https://grafana.com/docs/k6/latest/using-k6/thresholds/
- Import Linter contracts: https://import-linter.readthedocs.io/en/stable/
