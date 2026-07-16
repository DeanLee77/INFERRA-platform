# INFERRA Implementation Status

Status: active source of truth
Last updated: 2026-07-16

This document replaces the old phase-plan stack as the current implementation status. Historical plans are archived under `docs/archive/`; use them for context, not for acceptance decisions.

## Executive Summary
INFERRA is no longer a Phase 1-2 rule-engine prototype. The current codebase is a graph-first, port/adapter FastAPI platform with layered fact storage, Redis/Celery async work, Fuseki semantic projection, observability, production-style Docker Compose, and hybrid reasoning features behind flags.

The feature-flag registry, deployment-profile handling, runtime consumers, and
API/worker snapshot evidence are now aligned. The clean local backend release
gate also meets the unchanged 97% coverage policy. Remaining work is external
release evidence and policy rather than foundational implementation: frontend
build inputs, live smoke/load/chaos runs, staging repetition, complete release
artifacts, external secret management, tenant auth decisions, LLM provider
policy, and final legacy retirement.

## Verification Snapshot
| Gate | Latest local result |
| --- | --- |
| Functional regression suite | Clean integrated run: 3,437 passed, 73 skipped |
| Benchmark gate | 22 passed, 3 skipped |
| Phase 5 acceptance | 7 passed with the integration gate enabled |
| Infrastructure release gates | 39 passed, 3 skipped |
| Base Compose config | Valid; API and worker share snapshot hash `789dc53d...b215b` |
| Production overlay config | Valid with required render-time inputs; API and worker share the same snapshot hash |
| Coverage policy | Pass: 22,206/22,889 statements, 97.016% versus required 97% |
| Import boundaries | Pass: 243 files, 722 dependencies, 2/2 contracts kept |
| Feature-flag evidence | API and worker each captured 28 entries with matching snapshot hash `789dc53d...b215b` |
| Local release-candidate script | Pass with unavailable frontend, live-smoke, load, and chaos inputs explicitly skipped |
| Load gate | Main-branch CI includes Dockerized k6 production profile |

## Phase Status
| Area | Current state | Production caveat |
| --- | --- | --- |
| Phase 1 foundation | Complete. FastAPI, validation, layered memory, graph migration scaffolding, correlation/logging, and session schema migration are present. | Keep regression and compatibility tests. |
| Phase 2 async/imports | Complete. Async rule sync, modular imports, port contracts, and Phase 2 feature flags exist. | Keep `layered_memory=true`; do not bypass `FactStorePort`. |
| Phase 2.5 graph bridge | Implemented. `HyperAdjacencyGraph` is canonical; `DependencyMatrix` is compatibility only with deprecation warnings and guardrails. | Do not delete matrix bridges until migration/legacy-read evidence is complete. |
| Phase 3 orchestration/ontology | Implemented locally. Orchestrator, convergence, PROV-O, ontology post-reasoning, Redis deltas, and semantic-layer injection paths exist. | Needs live local-prod/staging proof for the full ontology workflow, not just unit tests. |
| Phase 4 production hardening | Substantial. Auth, rate limiting, session ownership, Redis sessions, observability, monitoring, Docker hardening, k6, chaos scripts, and CI gates exist. | External secret manager, OIDC/RBAC/tenant policy, staging load/chaos, and branch protection remain decisions/gates. |
| Phase 5 hybrid reasoning | Implemented behind flags. Abduction, induction, routing, confidence thresholds, LLM adapter hardening, and acceptance tests exist. | Keep LLM paths disabled unless provider/model/evaluation/budget gates are signed off. Persistent induction promotion workflow still needs production proof. |

## Current Architecture Truth
- Ports are ABCMeta contracts in `src/ports/`; do not introduce `Protocol` ports.
- Domain code stays adapter-free. Import-linter and guardrail tests enforce this.
- Graph node keys are names/stable IDs. New code must not depend on numeric runtime node IDs.
- `HyperAdjacencyGraph` and `DependencyGraphPort` are the runtime dependency model.
- `DependencyMatrix` exists only for legacy compatibility, persistence bridges, and regression tests.
- `LayeredFactStore` is required for Phase 2+ behavior.
- Redis credentials must go through `src.infrastructure.secrets.redis_url_from_env()` or `redis_client_from_env()`.
- Slow or external work belongs in workers or adapters, not the hot deduction path.

## Active Capability Map
| Capability | Status |
| --- | --- |
| Deterministic deduction | Production candidate after release gates |
| Layered facts and provenance | Implemented |
| Modular rule imports | Implemented |
| Modern rule persistence API | Implemented as `/api/v1/rules`; legacy `/service/rule/*` remains for compatibility |
| Graph-first traversal | Implemented, compatibility shims retained |
| Redis-backed sessions | Implemented |
| API key/JWT auth, rate limiting, session ownership | Implemented |
| CSRF protection | Implemented, opt-in |
| Fuseki semantic projection | Implemented |
| Ontology post-reasoning event loop | Implemented locally, needs live workflow proof |
| Z3 abduction | Implemented |
| LLM abduction/enhancements | Implemented but optional; keep gated |
| Induction pipeline | Implemented, production promotion workflow still partial |
| Observability dashboards/metrics/logging | Implemented locally; staging tuning needed |
| Feature-flag runtime visibility | Implemented for API/worker startup, protected system API, release evidence, and cross-process hash checks |
| k6 and chaos gates | Implemented locally; staging repetition needed |
| OpenAPI release artifact | Still missing |

## Release Blockers
1. Restore/locate the two frontend workspaces referenced by the release script
   and execute their build/test stage.
2. Generate and publish `openapi.json` in CI, with drift detection.
3. Run readiness, k6 production gate, and chaos suite in staging, not only local Compose.
4. Move real secrets to the target platform secret manager.
5. Decide first-release auth policy: API key/JWT only, or OIDC/RBAC.
6. Decide LLM launch posture; default should be deterministic release with LLM disabled.
7. Complete/accept the induction promotion workflow if learned rules are part of launch.
8. Complete the release evidence packet. The local backend script and
   feature-flag snapshots pass; frontend and live-environment evidence remain.

## Superseded Documents
The old phase plans, recommendation memos, future blueprints, and one-off operations notes are archived under `docs/archive/`. They are retained for audit/history only. This file, `docs/ROADMAP.md`, `docs/OPERATIONS.md`, `docs/INFERRA_Production_Readiness_and_Tech_Stack.md`, the production decision register, and the legacy retirement register are the current implementation documents.
