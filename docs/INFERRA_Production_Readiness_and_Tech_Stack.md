# INFERRA Production Readiness and Technology Stack

Status: implementation advisory and executable readiness plan
Date: 2026-05-06

This document records the recommended production stack for INFERRA and the
non-LLM work that remains after the current phase implementation pass. It is
intended to sit beside the phase plans as the practical "how do we ship this?"
decision record.

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
| Graph runtime | HyperAdjacencyGraph as canonical graph, DependencyMatrix only as compatibility adapter | Graph-native traversal scales better than dense N x N scans for sparse rule graphs | Mostly implemented | Keep guardrails until matrix hot paths are fully gone |
| Dependency type model | IntFlag-style bitmask composition | Preserves existing AND, OR, NOT, KNOWN, MANDATORY combinations without brittle enum coercion | Implemented or planned in bridge code | Add regression cases for mixed masks in ML sort paths |
| Node identity | Use stable node names/IDs as graph keys | Avoids non-portable numeric IDs and makes persistence, RDF, and trace lookup stable | Current graph is name-keyed | Do not reintroduce numeric node_id in new code |
| Async jobs | Celery + Redis broker/result backend | Good fit for induction, RDF sync, background promotion workflows | Docker compose includes worker and Redis | Add retry, DLQ, rate-limit verification drills |
| Semantic store | Apache Jena Fuseki for RDF/SPARQL plus rdflib in Python | Separates RDF truth/audit graph from request-time rule execution | Docker compose includes Fuseki | Add dataset backup/restore and namespace governance |
| Persistence | PostgreSQL for durable sessions, rules, audit index; Redis for hot session/cache | PostgreSQL is the durable source; Redis is operationally fast but ephemeral by default | Docker compose includes both | Avoid pickle for untrusted state; prefer JSON/msgpack schemas |
| Observability | OpenTelemetry traces, Prometheus metrics, Grafana/Tempo or Jaeger dashboards | Hybrid reasoning needs explainability at system and domain levels | OTel collector and metrics exist | Add dashboard definitions and alert thresholds |
| Frontend | Vite + TypeScript + React for graph-heavy tools, TanStack Query, React Flow, Zod, Playwright | Rule Studio and harness need graph editing, typed API state, and e2e confidence | Current static frontends are useful prototypes | Convert prototypes to typed production apps when UX scope is fixed |
| Load and chaos | k6 load smoke, Docker compose service interruption drills | Prevents confidence based only on unit tests | Added by this readiness package | Run in CI/staging with threshold history |
| CI quality gate | GitHub Actions for backend coverage, frontend checks, Docker build | Makes phase plan acceptance repeatable | Added by this readiness package | Add protected-branch enforcement |

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
| DependencyMatrix | Simple dense representation, legacy-compatible | O(N^2) memory, row-scan traversal, awkward subgraphs | Keep only behind bridge/adapters | Retire from hot paths |
| HyperAdjacencyGraph | Sparse adjacency, typed child groups, natural parent lookup | Needs parity tests for every legacy traversal mode | Best runtime graph | Canonical domain graph |
| NetworkX | Rich algorithms, fast prototyping | Adds dependency and object-model mismatch | Useful for offline analysis | Do not put in hot runtime unless justified |
| graphlib.TopologicalSorter | Standard library, deterministic topological sort | No ML child ordering by itself | Good static topo helper | Use for non-ML static ordering |

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
| Backend unit, integration, regression coverage | Code verification | Green in previous full run: 2208 passed, 6 skipped, coverage above 92% | None known | Keep coverage gate in CI |
| Frontend prototype tests | Code verification | Green in previous run for both frontends | None known | Keep checks in CI |
| Live Docker smoke | Runtime verification | Green in previous run against Redis, Fuseki, Postgres, worker, OTel | Local Docker must be running | Use `scripts/verify_phase_readiness.ps1` |
| Load smoke | Runtime verification | k6 script added | k6 must be installed in runner/staging | Run `k6 run tests/load/k6_api_smoke.js` |
| Chaos smoke | Runtime verification | Docker compose drill script added | Requires permission to pause/restart compose services | Run in staging, not developer machines by default |
| CI gate | Automation | GitHub workflow added | Repository must enable Actions and branch protection | Make CI required before merge |
| Production auth | Security | Middleware exists, but product policy is not finalized | Need auth model: internal API key, OIDC, or tenant JWT | Choose auth mode before external users |
| Secrets management | Security | Compose uses dev credentials | Need target platform: local, cloud, Kubernetes, or managed PaaS | Move secrets to platform secret manager |
| Production frontend rewrite | Product engineering | Prototype frontends exist and test | Need UX scope and API contract freeze | Use React + TypeScript + Vite + React Flow |
| GraphRAG production | Future plan | Blueprint exists, partial semantic foundation exists | Need corpus, ontology governance, vector-store choice, evaluation set | Start as separate Phase 7 project |
| LLM reasoning | Future/optional | Null/fallback flows implemented | Provider/model/key/evaluation policy | Keep disabled until model gate is approved |

## Best-Practice Architecture Rules

| Rule | Keep doing | Avoid | Reason |
| --- | --- | --- | --- |
| Port contracts | ABCMeta ports in `src/ports` | `typing.Protocol` for domain ports | Explicit inheritance and instantiation-time enforcement are valuable here |
| Graph traversal | Use `DependencyGraphPort` or graph strategy objects | Direct matrix scans in new runtime code | Keeps Phase 2.5 migration direction intact |
| ML topological sort | Standalone strategy taking graph + history store | Embedding history ordering into graph core | Keeps the graph deterministic and testable |
| Identity | Stable node names/IDs in graph, RDF, trace, history | New numeric `node_id` lookups | Reduces migration and persistence ambiguity |
| Bitmask dependency type | Preserve composable masks | Flattening to incompatible enum values | Existing rule semantics depend on composition |
| Structured logging | `structlog` with mandatory fields | `print()` or bare logging | Traceability matters for regulated reasoning |
| Slow work | Worker jobs, event/delta handoff, idempotency | Mutating hot session state from workers directly | Protects session consistency |
| External calls | Circuit breakers, fallbacks, metrics | Blocking unbounded provider calls | Keeps deterministic deduction reliable |

## Production Checklist

| Gate | Required evidence | Local command |
| --- | --- | --- |
| Backend correctness | Unit, integration, regression tests pass with coverage | `pytest --cov=src --cov-fail-under=97` |
| Frontend correctness | Both frontend checks and tests pass | `npm.cmd test`; `npm.cmd run check` in each frontend |
| Docker readiness | Compose stack is healthy | `docker compose up -d --build`; `docker compose ps` |
| Live API smoke | Health, metrics, abduction, disabled LLM fallback pass | `powershell -ExecutionPolicy Bypass -File scripts/verify_phase_readiness.ps1 -SkipUnitTests` |
| Load smoke | P95 and failure thresholds pass | `k6 run tests/load/k6_api_smoke.js` or `powershell -ExecutionPolicy Bypass -File tests/load/run_k6_docker.ps1` |
| Chaos smoke | System recovers from controlled service interruption | `powershell -ExecutionPolicy Bypass -File tests/chaos/docker_chaos_smoke.ps1 -Service redis -Action pause` then `-Action unpause` |
| Import boundary | No new runtime DependencyMatrix coupling | `pytest tests/infrastructure/test_guardrails.py` |

## Immediate Technical Recommendations

| Priority | Recommendation | Why |
| --- | --- | --- |
| P0 | Keep `HyperAdjacencyGraph` canonical and keep matrix guardrails active | This protects the largest migration decision already made |
| P0 | Add CI branch protection around the coverage and frontend checks | Prevents the phase plans from becoming aspirational documents |
| P1 | Run load and chaos scripts in a staging compose environment weekly | The biggest non-LLM risk is operational behavior under stress |
| P1 | Convert session serialization to a schema-safe format if any untrusted input can reach it | Pickle-style state is not a production security boundary |
| P1 | Freeze Rule Studio API shapes before rewriting the UI | Avoids churn in the highest-novelty frontend |
| P2 | Add Grafana dashboard JSON for reasoning and queue health | Metrics exist; operators need a curated view |
| P2 | Start GraphRAG as an evaluation harness first, not a production feature | Retrieval quality must be measured before it drives answers |

## References

- FastAPI deployment and Docker guidance: https://fastapi.tiangolo.com/deployment/docker/
- Vite production build guidance: https://vite.dev/guide/build
- OpenTelemetry Python instrumentation: https://opentelemetry.io/docs/languages/python/instrumentation/
- Redis security and ACLs: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
- Celery monitoring guide: https://docs.celeryq.dev/en/stable/userguide/monitoring.html
- k6 thresholds: https://grafana.com/docs/k6/latest/using-k6/thresholds/
- Import Linter contracts: https://import-linter.readthedocs.io/en/stable/
