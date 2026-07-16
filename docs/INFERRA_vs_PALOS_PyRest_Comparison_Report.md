# INFERRA vs PALOS-PyRest Comparison Report

Date: 2026-05-16

Reference project: `C:\Users\user\.pi\projects\PALOS-PyRest`

Current project: `C:\Users\user\.codex\project\inferra-platform`

## Executive Verdict
PALOS-PyRest is useful as an operational reference, especially around Docker hardening, docs organization, examples, generated OpenAPI artifacts, and k6 profiles. It is not the architectural north star for Inferra. Inferra's stricter port/adapter boundaries, graph-first runtime, layered memory, richer reasoning phases, and import-linter guardrails are the more valuable foundation.

The most important modernization path is not "copy PyRest"; it is "keep Inferra's architecture strict and make the production surface less casual."

## Corrected Comparison
| Claim | Verdict | Notes |
| --- | --- | --- |
| PyRest is further along because it has schema v5 while Inferra has schema v2 | Not valid | Inferra's `src/domain/state/session_schema.py` is already `CURRENT_SCHEMA_VERSION = 5`. The old `AGENTS.md` claim was stale and has been corrected. |
| PyRest has a more mature LLM stack | Partly valid | PyRest's LLM layout is a useful reference, but Inferra already has outbound LLM adapters, prompt sanitization, streaming, tracing, and reasoning integration. The next gap is provider policy, model routing evidence, and failure-mode tests, not a wholesale port. |
| PyRest has rate limiting and Inferra has none | Not valid | Inferra now has dedicated token-bucket rate limiting in `src/infrastructure/rate_limiter.py`, with compatibility kept for legacy imports. |
| PyRest has session ownership and Inferra has none | Not valid | Inferra has session ownership checks in the HTTP inference path and auth/session tests. |
| PyRest has Pydantic schemas and Inferra has none | Not valid | Inferra keeps schemas under `src/adapters/inbound/http/schemas/`, which is a cleaner adapter-local convention. |
| PyRest has shared utilities and Inferra has none | Mostly not valid | Inferra uses `src/infrastructure/` and domain-local modules rather than a broad `shared/` bucket. That is preferable if boundaries stay clean. |
| PyRest has load testing and Inferra has none | Not valid | Inferra has `tests/load/`, k6 profiles, Dockerized runners, and now a CI load gate on main. |
| PyRest has examples and Inferra has none | Not valid | Inferra has examples under `docs/reference/examples/`; a top-level index now points to them. |
| PyRest has generated OpenAPI and Inferra has none | Valid gap | Inferra should generate and publish `openapi.json` in CI as a release artifact. |
| PyRest has more adapters | Partly valid | Some PyRest mocks are useful, but Inferra has stronger port contracts and richer outbound adapters. Add mocks only where they improve contract tests. |
| PyRest removed DependencyMatrix while Inferra still has it | Partly valid | Inferra still has compatibility files, but graph-first runtime guardrails are present. The correct target is retirement by measured compatibility removal, not abrupt deletion. |
| PyRest defaults `use_hypergraph` to false while Inferra defaults true | Not a defect | Inferra's graph-first architecture makes `True` the correct modern default. Backward compatibility should be handled by migration paths, not by defaulting to legacy behavior. |

## Improvements Applied From This Review
- Hardened the Docker image with a multi-stage build, non-root runtime user, no cache install, and container healthcheck.
- Hardened Compose services with `init`, `no-new-privileges`, read-only app filesystems, tmpfs for `/tmp`, bounded JSON logs, worker healthcheck, and localhost-bound infrastructure ports.
- Added production Redis password support through Docker secrets.
- Centralized Redis URL/client creation so health checks, Celery, sessions, dead-letter queues, induction, and ontology-delta consumers respect secret-based credentials.
- Added a CI `load-gate` job that runs the Dockerized k6 production profile on main-branch pushes.
- Corrected `AGENTS.md` to reflect schema v5 and the actual phase/runtime status.
- Consolidated implementation docs into `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`, and `OPERATIONS.md`, with historical phase/future plans moved under `archive/`.
- Added this docs index and comparison report so future work starts from current evidence rather than stale claims.
- Added validation `waiver_id`s and `waived_error_ids` so a frontend can support explicit human-review overrides instead of a crude all-or-nothing save path.
- Split rate limiting out of auth middleware into a dedicated token-bucket infrastructure module with per-API-key isolation, reset hooks, disablement, and health-route exemptions.
- Added a modern `/api/v1/rules` persistence surface with snake_case contracts for listing, creating, fetching, versioning, and target-node lookup while keeping legacy `/service/rule/*` routes for compatibility.

## Brutal Recommendations
1. Generate `openapi.json` in CI and fail if it drifts from route/schema changes.
2. Split local Compose and production rehearsal more clearly. Local should be ergonomic; production rehearsal should require auth, Redis auth, non-default DB/Fuseki/Grafana passwords, and explicit secret files.
3. Add a release artifact bundle: OpenAPI spec, benchmark summary, k6 summary, import-linter report, and legacy-retirement report.
4. Stop letting historical phase docs be mistaken for live truth. Keep `docs/README.md`, `AGENTS.md`, and the alignment audit current.
5. Retire `DependencyMatrix` only behind measured compatibility gates. The graph-first direction is right, but deleting bridge code without migration evidence would be reckless.
6. Promote LLM provider policy into explicit config: allowed providers, model defaults, timeout/retry/circuit breaker defaults, redaction, and tracing expectations.
7. Add contract tests for Redis-secret production mode so every future Redis client path must use the shared resolver.
8. Keep `/service/rule/*` as compatibility only, migrate Rule Studio to `/api/v1/rules`, then retire the legacy endpoints behind a published deprecation window.
9. Add real persisted `display_name` and version audit metadata before exposing those fields as durable product commitments.
