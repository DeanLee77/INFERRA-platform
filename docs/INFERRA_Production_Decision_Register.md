# INFERRA Production Decision Register

Status: active production gate
Last updated: 2026-07-15

This register separates implementation readiness from external decisions that must be made before production traffic. A release candidate can pass local code gates while still being blocked by one of these decisions.

## Required Decisions

| Decision | Required before production? | Current hook | Production-ready condition | Status |
| --- | --- | --- | --- | --- |
| Deployment target | Yes | Local Docker Compose is the current production-like environment; `Dockerfile`, `docker-compose.prod.yml`, readiness scripts | Commercial target platform chosen and resource sizing recorded before external production traffic | [~] |
| Secret manager | Yes | `.env.example`, `secrets/init-secrets.*`, local Docker secret files, and `*_FILE` support for app-facing API/JWT/CSRF/Redis/Fuseki/LLM secrets | Real secrets stored in platform secret manager, not files or CI logs | [~] |
| Auth policy | Yes | API key, HS256 JWT, owner scoping, opt-in CSRF, rate limiting | OIDC/RBAC/tenant model accepted or explicitly deferred for first release | [~] |
| LLM provider/model | Optional for deterministic release | `LLM_ENHANCEMENTS=false` fallback, real LLM timeout/retry/circuit breaker, optional `LLMAbductionAdapter` gated by `INFERRA_ABDUCTION_ADAPTER=llm` | Provider, model, prompt version, evaluation set, budget, and incident fallback approved | [~] |
| RDF/ontology governance | Yes when Fuseki is production source | Fuseki adapter, PROV-O traces, compose dataset volume | Namespace, backup/restore, retention, and dataset ownership agreed | [~] |
| Staging acceptance | Yes | k6 production gate, multi-profile k6 runner, chaos suite, Phase 5 acceptance test | Same gates pass in staging with retained artifacts | [~] |
| Release sign-off | Yes | `scripts/verify_release_candidate.ps1`, audit document, phase plans | Core, Data, QA, and Security leads sign evidence packet | [~] |

## Source of Truth

The current `inferra-platform` implementation is the behavioral source of truth. `PALOS-PyRest` is an implementation reference for patterns such as declaration validation, post-reasoning, observability, Docker/k6 profiles, and LLM adapters. Reference ideas must be adapted to current ABC ports, graph-first runtime, feature-flag stickiness, layered fact store, and structlog contract before acceptance.

Current implementation status and roadmap are consolidated in `IMPLEMENTATION_STATUS.md` and `ROADMAP.md`. Historical phase plans are archived under `archive/phase-plans/`.

## Feature-Flag Runtime Decisions

Change 4 of the feature-flag alignment plan records these runtime decisions:

| Area | Decision | Evidence |
| --- | --- | --- |
| Graph and memory | `USE_HYPERGRAPH` and `LAYERED_MEMORY` are required-true production invariants while compatibility constructors remain available to migration tests | API/worker/session fail-fast validation |
| Port contracts | `STRICT_PORT_CONTRACTS` is required true and pending removal; import and port checks run unconditionally in CI | CI architecture gate and retirement report |
| ML ordering | Stored history affects parser topology only when `ML_OPTIMIZED_DFS` is enabled | Session-service enabled/disabled tests |
| Post reasoning | `ASYNC_POST_REASONING` and `GENERATE_POST_REASONING_TTL` are a coupled pair | Startup invariant and publisher tests |
| Orchestration | Stalled sessions use their frozen snapshot to select legacy/hybrid orchestration and real/null reasoning routing | Application orchestration service and route tests |
| Alternate reasoning | Abduction, induction, and confidence thresholds are propagated from the same frozen snapshot; request fields are opt-out only | Router factory and HTTP non-bypass tests |
| API projection | `PROV_O_TRACE` gates trace export; `ENRICHED_API` gates provenance/suggestion/reasoning metadata while preserving schemas | Inference route enabled/disabled tests |

## Release Evidence Packet

A release-candidate evidence packet should include:

- `pytest --cov=src --cov-fail-under=97`
- `pytest tests/integration/test_phase5_acceptance.py -q --run-integration`
- `pytest tests/benchmarks/ -q`
- `lint-imports --config .importlinter`
- `scripts/verify_phase_readiness.ps1` against the target stack
- k6 smoke and production-load output
- chaos-suite output
- `FeatureFlags().legacy_retirement_report()` for the target environment
- this register with every required external decision resolved or explicitly deferred

## Default Launch Position

For the first production candidate, keep LLM enhancements and LLM abduction disabled unless the provider/model gate has explicit sign-off. Deterministic deduction, graph-backed traversal, layered memory, Z3 abduction, and async induction infrastructure can be accepted independently from live LLM use.
