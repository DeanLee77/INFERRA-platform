# INFERRA Implementation Status

Status: active source of truth
Last updated: 2026-07-20

This document replaces the old phase-plan stack as the current implementation status. Historical plans are archived under `docs/archive/`; use them for context, not for acceptance decisions.

## Executive Summary
INFERRA is no longer a Phase 1-2 rule-engine prototype. The current codebase is a graph-first, port/adapter FastAPI platform with layered fact storage, Redis/Celery async work, Fuseki semantic projection, observability, production-style Docker Compose, and hybrid reasoning features behind flags.

The feature-flag registry, deployment-profile handling, runtime consumers, and
API/worker snapshot evidence are now aligned. The clean local backend release
gate also meets the unchanged 97% coverage policy. Substantial external release
evidence and policy remain: frontend build inputs, live smoke/load/chaos runs,
staging repetition, complete release artifacts, external secret management,
tenant auth decisions, separate AXIOM and AEGIS release gates, LLM provider
policy, final legacy retirement, and activation of the prepared GitHub branch
protection checks.

The accepted target separates the deterministic kernel into an internal,
independently buildable `inferra-core` Python distribution while retaining this
repository's FastAPI application as the authoritative Platform runtime. P0.1
inventory and behavior freezing completed on 2026-07-17: all 243 production
Python modules are classified, 70 are selected for the initial Core extraction,
29 current boundary imports are recorded, and six golden semantic vectors are
executable. P0.2a established `inferra-core==0.1.0`; the current security
release is `inferra-core==0.1.1`, with the same leaf facade, exact
Platform compatibility re-exports, independent wheel/source builds, and clean
installed-wheel proof. P0.2b adds private executable graph, node, token, parser
and deterministic-validation layers with explicit node-ID context and cache
clock boundaries. The 0.1.1 correction removes all Core third-party runtime
dependencies, replaces string-to-SymPy rule evaluation with a bounded INFERRA
AST/interpreter, makes internal declaration failures reject validation, and
reports graph cycles with a typed error. Platform now hosts Core validation,
but the supported compile/validation facade and Platform rewiring must be
completed before moving fact store, iteration, import resolution, inference,
or provenance. P0.2 therefore remains in progress.

## Verification Snapshot
| Gate | Latest local result |
| --- | --- |
| Functional regression suite | Clean integrated run after Core 0.1.1 security and numeric-precision corrections: 3,471 passed, 70 skipped, 146 warnings in 309.00 seconds |
| Benchmark gate | 22 passed, 3 skipped |
| Phase 5 acceptance | 7 passed with the integration gate enabled |
| Infrastructure release gates | 39 passed, 3 skipped |
| Base Compose config | Valid; API and worker share snapshot hash `789dc53d...b215b` |
| Production overlay config | Valid with required render-time inputs; API and worker share the same snapshot hash |
| Coverage policy | Pass after covering the five new compatibility branches: 20,932/21,579 statements, 97.0017% versus required 97%; no threshold or exclusions changed |
| Import boundaries | Pass: 243 files, 712 dependencies, 2/2 contracts kept |
| Feature-flag evidence | API and worker each captured 28 entries with matching snapshot hash `789dc53d...b215b` |
| Local release-candidate script | Pass with unavailable frontend, live-smoke, load, and chaos inputs explicitly skipped |
| Load gate | Main-branch CI includes Dockerized k6 production profile |
| OpenAPI release contract | Canonical `openapi.json` generated deterministically; local drift check passes |
| Required-check design | Seven independently requireable CI jobs prepared: Core distribution, dependency audit, coverage, import contracts, Docker build, OpenAPI drift, and candidate evidence |
| Core P0.1 inventory controls | Pass: 6 tests; 243 modules classified, 29 known boundary crossings, and the Structlog/SymPy/RDFLib import set frozen |
| Core P0.1 semantic vectors | Pass: 6 tests covering parser, diagnostics, inference, imports, iteration, hashes, and provenance |
| Core P0.2a distribution | Pass: `inferra-core==0.1.0` wheel/source build, 9 package tests, exact-class Platform re-exports, clean external-venv import with no repository `PYTHONPATH`, and zero forbidden modules loaded |
| Core P0.2b dependency layer | Pass: 17 package tests; frozen parser IDs/edges; explicit identity/clock controls; 957 applicable package/Platform tests; installed-wheel parser execution with declared SymPy and zero forbidden modules |
| Core 0.1.1 security correction | Pass: 33 package tests; 221 focused Platform compatibility/security tests; bounded expression parser/interpreter; fail-closed validation; typed cycle failure; zero Core runtime dependencies; 99-package lock; clean installed-artifact adversarial proof; full regression green |

## Phase Status
| Area | Current state | Production caveat |
| --- | --- | --- |
| Phase 1 foundation | Complete. FastAPI, validation, layered memory, graph migration scaffolding, correlation/logging, and session schema migration are present. | Keep regression and compatibility tests. |
| Phase 2 async/imports | Complete. Async rule sync, modular imports, port contracts, and Phase 2 feature flags exist. | Keep `layered_memory=true`; do not bypass `FactStorePort`. |
| Phase 2.5 graph bridge | Implemented. `HyperAdjacencyGraph` is canonical; `DependencyMatrix` is compatibility only with deprecation warnings and guardrails. | Do not delete matrix bridges until migration/legacy-read evidence is complete. |
| Phase 3 orchestration/ontology | Partially implemented locally. Orchestrator, convergence, PROV-O, ontology post-reasoning, Redis deltas, semantic-layer injection, rule RDF, and case-run artifact paths exist. | The accepted account/case model, immutable normal-path graph versions, durable transactional projection flow, retention policy, product authority enforcement, and live staging proof do not yet exist. |
| Phase 4 production hardening | Substantial. Auth, rate limiting, session ownership, Redis sessions, observability, monitoring, Docker hardening, k6, chaos scripts, and CI gates exist. | External secret manager, OIDC/RBAC/tenant policy, staging load/chaos, and branch protection remain decisions/gates. |
| Phase 5 hybrid reasoning | Implemented behind flags. Abduction, induction, routing, confidence thresholds, LLM adapter hardening, and acceptance tests exist. | Keep LLM paths disabled unless provider/model/evaluation/budget gates are signed off. Persistent induction promotion workflow still needs production proof. |

## Current Architecture Truth
- A real internal `inferra-core==0.1.1` distribution owns its leaf contracts
  and a private executable graph/node/token/parser/validation layer. Platform
  still ships the compatibility parser/iterate/matrix path and the remaining
  state/import/inference/provenance layers. The internal artifact exists, but
  its supported facade is intentionally partial and it is not publicly
  published or a complete engine package.
- Ports are ABCMeta contracts in `src/ports/`; do not introduce `Protocol` ports.
- Domain code stays adapter-free. Import-linter and guardrail tests enforce this.
- Graph node keys are names/stable IDs. New code must not depend on numeric runtime node IDs.
- `HyperAdjacencyGraph` and `DependencyGraphPort` are the runtime dependency model.
- `DependencyMatrix` exists only for legacy compatibility, persistence bridges, and regression tests.
- `LayeredFactStore` is required for Phase 2+ behavior.
- Production persistence is still rule/session/run-centric. It has no complete
  tenant/account/case aggregate or graph catalogue, and `FactSource` is not yet
  paired consistently with a separate decision-eligibility policy.
- Normal AXIOM UI behavior uses a separate semantic shadow flow, but Platform can
  still accept caller-selected semantic profiles that materialize ontology
  suggestions into decision-active fact layers. The intended AXIOM boundary is
  therefore not server-enforced.
- AEGIS workflow authoring currently binds a single rule per node and several
  runtime paths remain synthetic; the accepted multi-rule semantic gate contract
  is not implemented.
- Redis credentials must go through `src.infrastructure.secrets.redis_url_from_env()` or `redis_client_from_env()`.
- Slow or external work belongs in workers or adapters, not the hot deduction path.

## Accepted Target Architecture

- `inferra-core` is now a real internal Python distribution with private pure
  parsing, graph and validation implementations. Remaining extraction adds
  fact-store, iteration, inference, import resolution, trace/provenance,
  hashing, and structured audit-event creation before a stable facade is
  declared.
- Core must not import FastAPI, SQLAlchemy, Redis, Celery, Fuseki, LLM clients,
  deployment configuration, secrets, AEGIS, AXIOM, or other extensions.
- `inferra-platform` imports the installed Core artifact and remains responsible
  for API profiles, identity/scopes, migrations, authoritative revisions,
  transactions, sessions, audit/outbox persistence, workers, ontology
  projection, and operations.
- Every governed decision will carry authorized tenant scope plus opaque
  account, case, and execution identity. Platform owns AXIOM's governed case
  records; AEGIS owns its product case/workflow lifecycle and links frozen
  references to Core decisions.
- PostgreSQL is authoritative for the graph catalogue and audit/outbox. Fuseki
  holds critical, rebuildable, immutable rule/execution/case RDF projections.
  Retention is indefinite by default and selected through a versioned policy.
- Every fact source, including `ASSERTED`, is audited. Fact source and decision
  eligibility remain separate. Prior non-asserted products are re-derived,
  re-queried, or governed before future-case use.
- AXIOM's deterministic semantic boundary and AEGIS's typed semantic gate policy
  are enforced server-side, not selected by arbitrary API flags or UI behavior.
- AXIOM and AEGIS use generated service clients. Direct Python embedding is a
  separate offline/single-process mode whose host owns persistence, security,
  audit, concurrency, migration, and recovery.
- Internal package extraction is P0 before Core 1.0. Public registry publication
  is P1 after API stability, licensing, documentation, SBOM/provenance, signing,
  and pre-release validation.

See `INFERRA_Core_Package_and_Runtime_Architecture.md` for the controlling design.

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
| Account/case/execution persistence and graph ownership | Not implemented as an end-to-end production aggregate |
| Immutable normal-path case graph versions and graph catalogue | Not implemented; semantic-pilot versioning is not the general contract |
| Versioned configurable graph retention | Architecture accepted; implementation absent |
| AXIOM server-enforced deterministic authority profile | Not implemented; UI separation alone exists |
| AEGIS multi-rule typed semantic gate | Not implemented; current binding is singular and ontology is not integrated through the accepted contract |
| Z3 abduction | Implemented |
| LLM abduction/enhancements | Implemented but optional; keep gated |
| Induction pipeline | Implemented, production promotion workflow still partial |
| Observability dashboards/metrics/logging | Implemented locally; staging tuning needed |
| Feature-flag runtime visibility | Implemented for API/worker startup, protected system API, release evidence, and cross-process hash checks |
| k6 and chaos gates | Implemented locally; staging repetition needed |
| OpenAPI release artifact | Implemented locally as committed `openapi.json`; CI retention and drift enforcement activate after push |
| Internal `inferra-core` package | P0.1 and P0.2a-P0.2b complete; internal 0.1.1 adds the bounded evaluator, fail-closed validation, typed cycles, zero runtime dependencies, and installed-wheel security proof. Public facade/Platform rewiring, fact-store/iteration/imports, inference/provenance, and whole-engine proof remain. |

## Release Blockers
1. Continue P0.2-P0.4 of the internal `inferra-core` package boundary selected
   in `INFERRA_Core_Package_and_Runtime_Architecture.md`. P0.1 and P0.2a-P0.2b
   plus the 0.1.1 security correction are complete with evidence in
   `INFERRA_Core_Extraction_P0_1_Baseline.md` and
   `INFERRA_Core_Extraction_P0_2_Distribution.md`. First expose a narrow public
   compile/validation facade and rewire the already-extracted Platform path to
   the installed artifact. Only after that vertical slice passes should fact
   store/iteration/import resolution and inference/provenance move. Then prove
   whole-engine equivalence, reproducibility, version, and hash identity.
2. Implement the configuration-driven Core API profile selected in
   `INFERRA_Cross_Project_Technical_Direction.md`, now against the package-backed
   runtime. Treat AXIOM and AEGIS as separate repositories and release units
   rather than missing Platform workspaces. AXIOM currently fails type, unit,
   lint, and formatting gates; AEGIS is excluded from Core and has separate
   security, synthetic-runtime, licensing, lint, and formatting blockers.
3. Implement the minimum tenant/account/case/execution identity, fact
   source-versus-authority schema, immutable graph catalogue/version references,
   and indefinite-default retention-policy identity. Publish the Core audit path
   transactionally to versioned Fuseki projections and prove account/case
   authorization, reconciliation, and rebuild. Enforce the AXIOM deterministic
   profile at the service boundary; keep AEGIS semantic gates unavailable until
   its typed multi-rule contract passes.
4. Push the candidate and make `Python dependency audit`, `Backend tests and
   coverage`, `Import contracts`, `Docker build`, `OpenAPI drift`, and
   `Candidate evidence` required branch-protection checks. Confirm the OpenAPI
   and evidence-summary artifacts are retained by the first workflow run.
5. Run readiness, k6 production gate, and chaos suite in staging, not only local Compose.
6. Move real secrets to the target platform secret manager.
7. Decide first-release auth policy: API key/JWT only, or OIDC/RBAC.
8. Decide LLM launch posture; default should be deterministic release with LLM disabled.
9. Complete/accept the induction promotion workflow if learned rules are part of launch.
10. Complete the release evidence packet. The local backend script and
   feature-flag snapshots pass; frontend and live-environment evidence remain.

## Superseded Documents
The old phase plans, recommendation memos, future blueprints, and one-off operations notes are archived under `docs/archive/`. They are retained for audit/history only. This file, `docs/ROADMAP.md`, `docs/OPERATIONS.md`, `docs/INFERRA_Production_Readiness_and_Tech_Stack.md`, the production decision register, and the legacy retirement register are the current implementation documents.
