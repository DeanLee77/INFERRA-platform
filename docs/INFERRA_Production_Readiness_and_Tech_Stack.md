# INFERRA Production Readiness and Technology Stack

Status: implementation advisory and executable readiness plan
Date: 2026-05-06
Last execution audit: 2026-05-13

This document records the recommended production stack for INFERRA and the
non-LLM work that remains after the current phase implementation pass. It is
intended to sit beside `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`, and
`OPERATIONS.md` as the practical "how do we ship this?" decision record.
The old phase plans are archived under `archive/phase-plans/`.

`inferra-platform` is the behavioral source of truth. `PALOS-PyRest` may be used
as an implementation reference, but adopted features must be adapted to the
current ABC-port, graph-first, layered-fact-store, and feature-flag contracts.

## Executive Recommendation

INFERRA should be treated as a hybrid reasoning platform, not a simple REST
wrapper around a rule engine. The best implementation path is to keep the
Python domain core clean and deterministic, run all slow semantic/inductive
work out of the request path, and invest in proof-grade observability and
repeatable verification.

| Area | Recommendation | Why this is the best fit | Current repo alignment | Remaining action |
| --- | --- | --- | --- | --- |
| Backend API | FastAPI, Pydantic v2, Uvicorn in Docker | Strong async API ergonomics, typed request models, OpenAPI by default | Already implemented | Add production worker/process sizing per deployment target |
| Domain architecture | ABCMeta ports with explicit adapters | Enforces implementation contracts at instantiation and matches project convention | Already implemented | Keep Protocol out of ports |
| Graph runtime | HyperAdjacencyGraph as canonical graph, DependencyMatrix only as compatibility format | Graph-native traversal scales better than dense N x N scans for sparse rule graphs | Implemented as default runtime path; graph package now owns DependencyMatrix, Dependency, and DependencyType | Keep guardrails until legacy node-level graph shims are fully retired |
| Dependency type model | Canonical `src.domain.graph.DependencyType` using IntFlag-style bitmask composition | Preserves existing AND, OR, NOT, KNOWN, MANDATORY combinations without brittle enum coercion | Implemented; `src.domain.nodes.dependency_type` is only a compatibility shim | Keep mixed-mask regression coverage active, especially around ML sort paths |
| Node identity | Use stable node names/IDs as graph keys | Avoids non-portable numeric IDs and makes persistence, RDF, and trace lookup stable | Current graph is name-keyed | Do not reintroduce numeric node_id in new code |
| Async jobs | Celery + Redis broker/result backend | Good fit for induction, RDF sync, ontology post-reasoning, background promotion workflows | Docker compose includes worker and Redis; induction has retry, DLQ, source-hash idempotency, post-reasoning has Redis delta events, and circuit/retry proof exists | Run live candidate-quality and Fuseki-read/post-reasoning drills in local-prod Compose and staging |
| Semantic store | Apache Jena Fuseki for RDF/SPARQL plus rdflib in Python | Separates RDF truth/audit graph from request-time rule execution | Docker compose includes Fuseki | Add dataset backup/restore and namespace governance |
| Persistence | PostgreSQL for durable sessions, rules, audit index; Redis for hot session/cache | PostgreSQL is the durable source; Redis is operationally fast but ephemeral by default | Docker compose includes both | Avoid pickle for untrusted state; prefer JSON/msgpack schemas |
| Observability | OpenTelemetry traces, Prometheus metrics, Grafana dashboards, Loki logs | Hybrid reasoning needs explainability at system and domain levels | Grafana, Prometheus, Loki, Promtail, OTel collector, dashboards, and Prometheus alert rules exist | Tune alert thresholds against staging traffic |
| Frontend | Vite + TypeScript + React for graph-heavy tools, TanStack Query, React Flow, Zod, Playwright | Rule Studio and harness need graph editing, typed API state, and e2e confidence | Current static frontends are useful prototypes | Convert prototypes to typed production apps when UX scope is fixed |
| Load and chaos | k6 load smoke, multi-profile k6 runs, Docker compose service interruption drills | Prevents confidence based only on unit tests | Smoke, production gate, and smoke/load/stress/spike/soak runner artifacts are present | Run in CI/staging with threshold history |
| CI quality gate | GitHub Actions for backend coverage, frontend checks, Docker build | Makes phase plan acceptance repeatable | Added by this readiness package | Add protected-branch enforcement |

## Latest Execution Evidence - 2026-05-13

These results supersede older "previous run" language and should be used with
`IMPLEMENTATION_STATUS.md` as the current implementation baseline.

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend regression | Pass | `pytest -q`: 2450 passed, 69 skipped |
| Backend coverage | Pass | `pytest --cov=src --cov-fail-under=97 -q`: 2441 passed, 72 skipped, 97.01% total coverage |
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
| React + TypeScript + Vite | Strong graph/editor ecosystem, React Flow, mature testing and query tooling | More dependencies than static JS | Best for Rule Studio and AI Harness | Recommended production frontend |
| Vue + TypeScript + Vite | Excellent ergonomics, good state patterns, smaller-feeling app code | Graph editor ecosystem is thinner than React Flow | Good alternative for operational dashboards | Viable, but second choice for graph drawing |
| SvelteKit | Fast, concise, pleasant for custom UI | Smaller enterprise/test ecosystem for complex graph editors | Useful for experimental tools | Not first production choice |

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
| Fuseki only | Standards-based RDF/SPARQL, PROV-O friendly | Not ideal for vector similarity | Good audit and ontology source | Keep as semantic source of truth |
| PostgreSQL + pgvector | One database for relational and vector search | Less RDF-native | Good retrieval adjunct | Add when GraphRAG moves beyond blueprint |
| Qdrant | Strong vector search and filtering | Additional service to operate | Good for AI harness context retrieval | Consider for production GraphRAG |
| Neo4j | Great property graph UX | Different model from RDF and current stack | Could confuse source-of-truth boundaries | Not recommended unless product pivots |

## Remaining Work Matrix

This table separates implementation work that can be finished inside this
repository from work that depends on external operational decisions or LLM
provider readiness.

| Work item | Type | Status after this package | Non-LLM blocker | Recommended next action |
| --- | --- | --- | --- | --- |
| Backend unit, integration, regression coverage | Code verification | Green in latest full coverage run: 2441 passed, 72 skipped, 97.01% coverage | None known | Keep 97% coverage gate in CI |
| Frontend prototype tests | Code verification | Green in current run for both frontends | None known | Keep checks in CI |
| Live Docker smoke | Runtime verification | Green in current run against Redis, Fuseki, Postgres, worker, OTel, Prometheus, Grafana, API health, metrics, and reasoning smoke | Local Docker must be running | Keep `scripts/verify_phase_readiness.ps1` in CI/staging smoke |
| Load smoke | Runtime verification | 20-VU Dockerized k6 smoke passes; 500-VU Dockerized production gate passes in the local compose profile; multi-profile smoke/load/stress/spike/soak runner is available | Staging/CI must preserve equivalent worker, network, and threshold policy | Keep smoke, profile, and production-gate threshold history in CI/staging |
| Redis session handoff | Runtime verification | Cross-store handoff preserves mutated session state and rejects stale saves; HTTP question/answer/reset paths now persist session mutations | Live multi-worker staging repetition still recommended | Keep Redis handoff tests in CI and repeat against staging |
| Chaos smoke | Runtime verification | Compose-scoped reversible drill plus Phase 4 restart-suite wrapper are present, artifact-tested, and passed locally for Redis, Fuseki, and worker restarts | Staging repetition still required | Run `tests/chaos/run_phase4_chaos_suite.ps1` in staging on a scheduled basis |
| Ontology post-reasoning | Runtime verification | Local code and unit tests exist for Fuseki projection, Redis delta events, DLQ, and convergence delta metrics | Live local-prod Compose workflow proof still required | Add the post-reasoning path to the phase readiness smoke before marking Phase 3 complete |
| CI gate | Automation | GitHub workflow includes backend coverage, import-linter, frontend checks, and Docker build | Repository must enable Actions and branch protection | Make CI required before merge |
| Production auth | Security | API key, HS256 JWT, owner scoping, session-owner enforcement, rate limiting, and opt-in CSRF are implemented and tested | OIDC/RBAC/tenant policy still require product decision | Use API key or HS256 JWT for protected environments; defer OIDC to enterprise auth work |
| Secrets management | Security | `.env.example`, `docker-compose.prod.yml`, `secrets/init-secrets.sh`, `secrets/init-secrets.ps1`, and local Docker secret files support a local production rehearsal path | Need target platform: local, cloud, Kubernetes, or managed PaaS | Move real secrets to platform secret manager before production traffic |
| Production frontend rewrite | Product engineering | Prototype frontends exist and test | Need UX scope and API contract freeze | Use React + TypeScript + Vite + React Flow |
| GraphRAG production | Future plan | Blueprint exists, partial semantic foundation exists | Need corpus, ontology governance, vector-store choice, evaluation set | Start as separate Phase 7 project |
| LLM reasoning | Future/optional | Null/fallback flows implemented; real adapter has timeout, retry, circuit-open fallback, half-open recovery proof, cost/metrics/tracing, and optional LLM abduction behind feature flags | Provider/model/key/evaluation policy | Keep disabled until model gate is approved |

## Best-Practice Architecture Rules

| Rule | Keep doing | Avoid | Reason |
| --- | --- | --- | --- |
| Port contracts | ABCMeta ports in `src/ports` | `typing.Protocol` for domain ports | Explicit inheritance and instantiation-time enforcement are valuable here |
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
