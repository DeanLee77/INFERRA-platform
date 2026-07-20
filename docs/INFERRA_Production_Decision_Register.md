# INFERRA Production Decision Register

Status: active production gate
Last updated: 2026-07-20

This register separates implementation readiness from external decisions that must be made before production traffic. A release candidate can pass local code gates while still being blocked by one of these decisions.

## Required Decisions

| Decision | Required before production? | Current hook | Production-ready condition | Status |
| --- | --- | --- | --- | --- |
| Core packaging form | Yes | Accepted 2026-07-17: a real internal `inferra-core` Python distribution plus the authoritative `inferra-platform` service; not library-only | Independent wheel/sdist, public use-case facade, forbidden-import and installed-wheel tests, golden-vector equivalence, exact artifact hash recorded by Platform | [x] decision / [x] P0.1 / [x] P0.2a-P0.2b and 0.1.1 security correction / [ ] facade integration and remaining extraction/rewiring/proof |
| Rule-source expression execution | Yes | Accepted 2026-07-17: documented `IS CALC` syntax is interpreted only by the bounded INFERRA lexer/private AST/interpreter; no Python, SymPy, or general-purpose source evaluator; declaration failures reject and graph cycles are typed | Adversarial source and resource-limit tests, fail-closed save/activation validation, typed cycle contracts, zero Core runtime dependencies, and clean installed-wheel proof remain mandatory CI/release gates | [x] implemented in Core 0.1.1 / [ ] required-check enforcement after push |
| Public Core package publication | No for Core 1.0 | Internal packaging first; public publication deferred until stability | License, registry name, API reference, changelog, SBOM/provenance, signing, supported-version matrix, and pre-release cycle approved | [x] deferred |
| Embedded-mode support boundary | Yes before documenting embedded use as supported | Direct Python import is intended for offline, edge, desktop, test, and single-process hosts; internal 0.1.1 exposes a small supported leaf facade while its executable parser/graph layer remains private | Host responsibilities for persistence, identity, audit, concurrency, migration and recovery documented; embedded results never presented as Platform-certified by default | [x] direction / [~] partial package implementation |
| Release composition and API profile | Yes | Cross-project direction selects an API-only `core` Platform profile as the first production target; AXIOM and AEGIS are separate release units | Configuration-driven router profile implemented, forbidden routes absent from Core OpenAPI, and every included product named in one compatibility manifest | [~] |
| Account/case execution hierarchy | Yes for governed multi-user decisions | Accepted: Tenant/Workspace is the authorization boundary; KnowledgeSubject/Account is the domain subject; AXIOM `AssessmentCase` and AEGIS `WorkflowCase` share only a small `CaseEnvelope`; both contain multiple immutable executions/attempts; every Core decision carries their opaque frozen references | Database constraints, service commands, OpenAPI/generated clients, graph catalogue, and negative cross-account tests enforce the hierarchy; product-specific profiles/PII are not duplicated into Core | [x] direction/cardinality/ownership / [ ] implementation |
| Provenance storage and future-case authority | Yes before longitudinal reuse | Accepted: every source class, including `ASSERTED`, is append-only audit data; source class is separate from verification and decision eligibility. Assertions are revalidated, inferences re-derived, semantic results re-queried, learned facts governed before promotion, and hypothetical facts remain audit/simulation only | Fact/decision schema records both source and authority dimensions; server policy and tests prevent historical derived products from being copied into current truth | [x] storage/reuse/authority direction / [ ] implementation |
| Deployment target | Yes | Local Docker Compose is the current production-like environment; `Dockerfile`, `docker-compose.prod.yml`, readiness scripts | Commercial target platform chosen and resource sizing recorded before external production traffic | [~] |
| Secret manager | Yes | `.env.example`, `secrets/init-secrets.*`, local Docker secret files, and `*_FILE` support for app-facing API/JWT/CSRF/Redis/Fuseki/LLM secrets | Real secrets stored in platform secret manager, not files or CI logs | [~] |
| Auth policy | Yes | API key, HS256 JWT, owner scoping, opt-in CSRF, rate limiting | OIDC/RBAC/tenant model accepted or explicitly deferred for first release | [~] |
| Browser/BFF identity | Required for any production AXIOM or AEGIS release | Both UIs currently use static Svelte applications behind Express proxies | Authenticated BFF session, exact route/method allowlist, CSRF, no browser credential forwarding, no sibling-repository secret reads, and verified end-user identity propagated to Platform | [~] |
| AEGIS launch posture | No for Core; yes before AEGIS production | AEGIS backend is mounted in the broad development API and uses caller-supplied actor roles plus synthetic runtime paths | AEGIS absent from Core; separately released AEGIS application backend/BFF consumes Core APIs/events and passes verified-actor, persisted-runtime, fail-closed, migration, quality, and recovery gates | [~] |
| AEGIS ontology-assisted multi-rule gates | No for Core; yes before AEGIS production ontology use | Accepted: raw SPARQL never transitions a workflow; a pinned result becomes a typed `SEMANTIC` fact evaluated by one or more approved rule bindings; authoring defaults to `ALL + DENY_OVERRIDES`, activation explicitly confirms composition, and unresolved outcomes fail closed | Persisted multi-rule bindings and composition policy, semantic eligibility per condition, pinned graph/query provenance, stale/error handling, Core/AEGIS reconciliation, and actuation-negative tests pass | [x] authority/default/conflict direction / [ ] implementation |
| Repository licensing and third-party redistribution | Yes before public distribution | Platform and AXIOM have no license file; AEGIS upstream is proprietary; SNOMED guidance records redistribution restrictions | Approved per-repository license, NOTICE/attribution, asset provenance, and third-party redistribution register are present and consistent with the intended open-source/proprietary split | [~] |
| LLM provider/model | Optional for deterministic release | `LLM_ENHANCEMENTS=false` fallback, real LLM timeout/retry/circuit breaker, optional `LLMAbductionAdapter` gated by `INFERRA_ABDUCTION_ADAPTER=llm` | Provider, model, prompt version, evaluation set, budget, and incident fallback approved | [~] |
| RDF/ontology governance | Yes because the Core profile includes audit/provenance projection | Accepted direction: PostgreSQL is authoritative; Fuseki is a critical rebuildable versioned projection; global ontology and approved rule graphs are human-governed; execution appends immutable case graph versions; retention defaults to indefinite with deployment -> tenant -> account/case/data-class policy specificity, legal/regulatory bounds, and a tombstone when law permits | Namespace/graph catalogue, transactional outbox, account/case authorization, reconciliation/rebuild, backup/restore, versioned retention policy, legal hold/purge behavior, and dataset ownership are implemented and tested | [x] architecture/default/hierarchy/tombstone direction / [ ] implementation |
| Staging acceptance | Yes | k6 production gate, multi-profile k6 runner, chaos suite, Phase 5 acceptance test | Same gates pass in staging with retained artifacts | [~] |
| Release sign-off | Yes | `scripts/verify_release_candidate.ps1`, audit document, phase plans | Core, Data, QA, and Security leads sign evidence packet | [~] |

## Source of Truth

The current `inferra-platform` implementation is the behavioral source of truth
until package extraction is complete. The accepted target package/runtime
boundary is controlled by
`INFERRA_Core_Package_and_Runtime_Architecture.md`; target statements are not
implementation claims. Completed P0.1 evidence is controlled by
`INFERRA_Core_Extraction_P0_1_Baseline.md`; live P0.2 distribution/extraction
evidence is controlled by `INFERRA_Core_Extraction_P0_2_Distribution.md`.
`PALOS-PyRest` is an implementation reference for
patterns such as declaration validation, post-reasoning, observability,
Docker/k6 profiles, and LLM adapters. Reference ideas must be adapted to current
ABC ports, graph-first runtime, feature-flag stickiness, layered fact store, and
structlog contract before acceptance.

Current implementation status and roadmap are consolidated in `IMPLEMENTATION_STATUS.md` and `ROADMAP.md`. Historical phase plans are archived under `archive/phase-plans/`.

Cross-project product ownership, first-release composition, API profiles,
frontend/BFF boundaries, database direction, ontology audit logging, and the
suite-wide priority order are controlled by
`INFERRA_Cross_Project_Technical_Direction.md`.

Account/case identity, graph topology, fact-source versus authority, AXIOM and
AEGIS semantic behavior, correlation, and retention are controlled by
`INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md`.

The package/runtime, SDK, embedded-mode, versioning, extraction, and publication
rules are controlled by `INFERRA_Core_Package_and_Runtime_Architecture.md`.

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

- the internal `inferra-core` wheel and source distribution, SHA-256 hashes,
  dependency/SBOM metadata, installed-wheel test result, forbidden-import result,
  and golden-vector comparison;
- the exact Core version and artifact hash reported by Platform;
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

For the first production candidate, keep LLM enhancements and LLM abduction
disabled unless the provider/model gate has explicit sign-off. The Core profile
publishes non-decision-affecting, account/case-scoped audit/provenance to
versioned Fuseki graphs and defaults retention to indefinite. AXIOM execution is
deterministic and cannot enable semantic auto-answer/materialization. AEGIS and
all decision-affecting ontology profiles remain unavailable until their separate
typed-evidence, authority, failure, and staging gates pass. Deterministic
deduction, graph-backed traversal, layered memory, Z3 abduction, and async
induction infrastructure can be accepted independently from live LLM use.
