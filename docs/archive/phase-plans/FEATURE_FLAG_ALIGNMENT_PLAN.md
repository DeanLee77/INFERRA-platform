# INFERRA Feature Flag Alignment and Completion Plan

> **Archived:** 2026-07-16. The locally executable work is complete. Remaining
> external release evidence is governed by `docs/ROADMAP.md` and
> `docs/INFERRA - Assessment & Recommendations.md`.

Status: Changes 1-5 complete for the locally available scope; external release evidence pending
Last updated: 2026-07-16
Primary source of truth: `src/domain/state/feature_flags.py`

Current milestone: Change 5 runtime visibility and release-evidence capture are
implemented. A clean release-candidate run passes every locally available gate,
including the full backend regression suite at 97.016% coverage, Phase 5
acceptance, benchmarks, infrastructure guardrails, import boundaries, rendered
Compose parity, and API/worker flag evidence. Frontend builds and live-stack
smoke, load, and chaos checks remain external release inputs and were explicitly
skipped rather than claimed by the local run.

## 1. Objective

Make INFERRA feature-flag behaviour complete, consistent, testable, and operationally clear without accidentally changing production behaviour.

The finished implementation must provide:

- one canonical definition for every feature flag and typed feature setting;
- matching names, types, and code defaults across runtime code and active documentation;
- explicit separation between conservative code defaults and deployment-profile overrides;
- deterministic environment-variable loading for local, worker, Compose, and production entry points;
- a verified production consumer, or an explicit retirement decision, for every declared flag;
- start-of-session stickiness for every session-affecting flag;
- automated drift detection in tests and CI.

This plan covers 24 Boolean flags and 4 numeric ontology settings, for 28 canonical registry entries in total.

## 2. Current Baseline

The audit found that the canonical values in `FeatureFlags` are internally consistent with the duplicated defaults currently used by production Python classes. The surrounding repository is not fully aligned.

| Area | Current result | Required action |
| --- | --- | --- |
| Runtime registry | 28 entries are returned by `FeatureFlags().snapshot()` | Preserve as the baseline until a deliberate default-change decision is approved |
| Production duplicate defaults | Auth, ontology reasoning, and reasoning-router duplicates match the registry | Add automated comparison coverage so they cannot drift |
| Unit tests | `tests/domain/state/test_feature_flag_matrix.py::test_snapshot_completeness` omits `generate_post_reasoning_ttl` | Fix immediately; this assertion is inconsistent with the runtime snapshot |
| Module documentation | Five registry entries are omitted | Add `GENERATE_POST_REASONING_TTL` and four numeric ontology settings |
| Implementation Guide phase tables | Six registry entries are omitted | Add `ML_OPTIMIZED_DFS`, `GENERATE_POST_REASONING_TTL`, and four numeric ontology settings |
| Implementation Guide defaults block | Only 15 of 28 entries are shown | Replace with the complete canonical inventory or generate it |
| `.env.example` | Contains only 10 registry entries; auth is intentionally enabled for the deployment template | List every entry and clearly distinguish code defaults from profile overrides |
| Base Compose API profile | Deliberately enables several code-default-off capabilities | Document as a deployment profile, not as the canonical defaults |
| Post-reasoning Compose profile | Enables `ASYNC_POST_REASONING` but not `GENERATE_POST_REASONING_TTL` | Decide whether the workflow should be enabled; set both gates consistently and prove the publisher call path |
| Local `.env` behaviour | `FeatureFlags` reads `os.environ` directly and does not load `.env` | Define and test one process-boundary loading policy |
| Active strategic roadmap | Contains a pseudo-`FeatureFlags` class with names that do not exist in runtime code | Replace with canonical names or label it explicitly as conceptual capability terminology |
| Historical documents | Archived plans contain superseded defaults such as `USE_HYPERGRAPH=false` | Keep historical content unchanged, but ensure archive/superseded notices are prominent |
| Runtime wiring | Some registered flags have no confirmed production branch or are only logged | Wire, freeze, or retire each one through an explicit decision record |

## 3. Canonical Inventory

The following values are the no-environment, no-constructor-override code defaults that all active documentation and drift checks must use.

| Phase | Environment variable | Snapshot key | Type | Code default |
| --- | --- | --- | --- | --- |
| 1 | `INFERRA_USE_HYPERGRAPH` | `use_hypergraph` | Boolean | `true` |
| 1 | `INFERRA_LEGACY_ITERATE` | `legacy_iterate` | Boolean | `true` |
| 1 | `INFERRA_LAYERED_MEMORY` | `layered_memory` | Boolean | `true` |
| 1 | `INFERRA_ML_OPTIMIZED_DFS` | `ml_optimized_dfs` | Boolean | `false` |
| 2 | `INFERRA_ASYNC_SYNC_ENABLED` | `async_sync_enabled` | Boolean | `false` |
| 2 | `INFERRA_MODULAR_IMPORTS` | `modular_imports` | Boolean | `false` |
| 3 | `INFERRA_HYBRID_ORCHESTRATOR` | `hybrid_orchestrator` | Boolean | `false` |
| 3 | `INFERRA_ASYNC_POST_REASONING` | `async_post_reasoning` | Boolean | `false` |
| 3 | `INFERRA_GENERATE_POST_REASONING_TTL` | `generate_post_reasoning_ttl` | Boolean | `false` |
| 3 | `INFERRA_PROV_O_TRACE` | `prov_o_trace` | Boolean | `false` |
| 3 | `INFERRA_ENRICHED_API` | `enriched_api` | Boolean | `false` |
| 3 | `INFERRA_ONTOLOGY_ADVISORY_ENABLED` | `ontology_advisory_enabled` | Boolean | `false` |
| 3 | `INFERRA_ONTOLOGY_AUTO_ANSWER_ENABLED` | `ontology_auto_answer` | Boolean | `false` |
| 3 | `INFERRA_ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD` | `ontology_auto_answer_confidence_threshold` | Float | `0.85` |
| 3 | `INFERRA_ONTOLOGY_REASONING_ENABLED` | `ontology_reasoning` | Boolean | `false` |
| 3 | `INFERRA_ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD` | `ontology_reasoning_confidence_threshold` | Float | `0.85` |
| 3 | `INFERRA_ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH` | `ontology_reasoning_min_hierarchy_depth` | Integer | `1` |
| 3 | `INFERRA_ONTOLOGY_REASONING_MAX_CLOSURE_DEPTH` | `ontology_reasoning_max_closure_depth` | Integer | `10` |
| 3 | `INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED` | `ontology_question_strategy` | Boolean | `false` |
| 4 | `INFERRA_REDIS_SESSION_STORE` | `redis_session_store` | Boolean | `false` |
| 4 | `INFERRA_LLM_ENHANCEMENTS` | `llm_enhancements` | Boolean | `false` |
| 4 | `INFERRA_STRICT_PORT_CONTRACTS` | `strict_port_contracts` | Boolean | `true` |
| 4 | `INFERRA_OBSERVABILITY_ENABLED` | `observability_enabled` | Boolean | `false` |
| 4 | `INFERRA_AUTH_ENABLED` | `auth_enabled` | Boolean | `false` |
| 5 | `INFERRA_ABDUCTION_ENABLED` | `abduction_enabled` | Boolean | `false` |
| 5 | `INFERRA_INDUCTION_PIPELINE` | `induction_pipeline` | Boolean | `false` |
| 5 | `INFERRA_REASONING_ROUTER` | `reasoning_router` | Boolean | `true` |
| 5 | `INFERRA_CONFIDENCE_THRESHOLDS` | `confidence_thresholds` | Boolean | `true` |

`INFERRA_ONTOLOGY_QUESTION_STRATEGY` remains a compatibility alias for `INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED`; it must not be documented as a separate flag.

## 4. Value Taxonomy and Precedence

Every reference must use the following terminology.

1. **Code default**: The value used by `FeatureFlags()` when neither an explicit constructor argument nor an exported environment variable is present.
2. **Deployment-profile override**: A value supplied by local Compose, a production overlay, a platform environment, or a secrets/configuration service.
3. **Request/session override**: An allowed per-session ontology profile or ontology Boolean override.
4. **Effective session value**: The frozen snapshot stored on `InferenceSession.feature_flags` at session creation.

Resolution precedence must remain:

```text
explicit constructor/session input
    > exported process environment
    > canonical code default
```

Deployment documentation must never label a Compose or `.env.example` value as the code default unless it equals the canonical inventory.

## 5. Workstream A: Canonical Definition and Introspection

Priority: P0

### Tasks

- [x] Add structured metadata in `src/domain/state/feature_flags.py` for every registry entry: snapshot key, environment name, type, code default, phase, description, aliases, and whether it is session-sticky.
- [x] Keep the public `FeatureFlags(...)` constructor signature and existing snapshot keys backward-compatible.
- [x] Resolve constructor defaults through the structured metadata so the default is declared once.
- [x] Preserve the existing accepted Boolean spellings: `true`, `1`, `yes`, `false`, `0`, and `no`.
- [x] Add explicit validation rules for numeric settings:
  - confidence thresholds must be within `0.0..1.0`;
  - minimum hierarchy depth must be non-negative;
  - maximum closure depth must be greater than or equal to the minimum hierarchy depth.
- [x] Define whether invalid numeric environment values should fail fast or log and fall back. Use the same policy for API and worker processes.
- [x] Add a read-only helper that returns canonical metadata and another that returns the effective snapshot. Neither helper may expose secrets because feature flags are non-secret configuration.
- [x] Ensure the module-level default object is constructed only after process-level environment loading has completed.

Change 3 selected fail-fast validation for malformed, non-finite, out-of-range,
or cross-setting-invalid numeric values in both API and worker processes. The
module-level default object is now lazy, so entry points load the selected
environment before constructing it.

### Acceptance criteria

- Exactly 28 canonical entries are present.
- Every snapshot key maps to one primary `INFERRA_*` environment variable.
- The compatibility alias is tested but is not counted as entry 29.
- `FeatureFlags().snapshot()` remains backward-compatible unless a separately approved migration changes a default.

## 6. Workstream B: Test Repair and Drift Prevention

Priority: P0

### Immediate repairs

- [x] Add `generate_post_reasoning_ttl` to `TestFlagDefaults.test_default_values` in `tests/domain/state/test_feature_flag_matrix.py`.
- [x] Add `generate_post_reasoning_ttl` to the `expected_keys` set in `test_snapshot_completeness`.
- [x] Retain the exact 28-entry snapshot assertion in `tests/domain/state/test_feature_flags.py`.

### Consolidation

- [x] Replace hand-maintained duplicate default lists with parameterized tests generated from the canonical metadata.
- [x] Test all primary environment names and the one supported alias.
- [x] Test constructor-over-environment precedence for Boolean, float, and integer settings.
- [x] Test invalid environment values according to the policy selected in Workstream A.
- [x] Test that session creation snapshots and freezes all 28 entries, not only Phase 1 flags.
- [x] Test that changes to process/global configuration do not alter an existing session.
- [x] Add a source scan or metadata-driven test ensuring every non-retired flag has at least one approved production consumer.
- [x] Add a documentation/configuration drift test that checks:
  - [x] the active feature-flag table contains all 28 entries;
  - [x] `.env.example` contains all primary environment names;
  - [x] every Compose override refers to a known flag;
  - [x] deployment overrides are explicitly classified and are not mistaken for code defaults.

Change 2 also gates the module header, the complete Implementation Guide
defaults block, the README canonical-inventory link, and duplicated auth,
ontology-reasoning, and reasoning-router defaults. Change 3 extends that gate
to `.env.example` and the shared Compose profile.

### Targeted validation

```powershell
python -m pytest tests/domain/state/test_feature_flags.py -q
python -m pytest tests/domain/state/test_feature_flag_matrix.py -q
python -m pytest tests/integration/test_feature_flag_flip.py -q --run-integration
python -m pytest tests/tasks/test_ontology_post_reasoner.py -q
```

## 7. Workstream C: Active Documentation Alignment

Priority: P0

### Tasks

- [x] Complete the module header in `src/domain/state/feature_flags.py` with all 24 Boolean flags and 4 numeric settings.
- [x] Replace the partial phase tables in `IMPLEMENTATION_GUIDE.md` with the canonical 28-entry inventory.
- [x] Replace the partial "defaults shown" block in `IMPLEMENTATION_GUIDE.md` with a generated or mechanically verified block.
- [x] Keep the concise README table, but label it as examples and link to the complete inventory.
- [x] Add a clear table showing the differences between:
  - code defaults;
  - base local Compose overrides;
  - production-overlay overrides;
  - permitted per-session ontology overrides.
- [x] Replace the pseudo-`FeatureFlags` class in `docs/archive/future-and-enhancements/INFERRA_Strategic_Plan_and_Innovation_Roadmap.md` with canonical flag names, or mark those names as conceptual roadmap capabilities that are not runtime flags.
- [x] Add a superseded notice to `docs/archive/status-audits/GAPS_ANALYSIS_SNOMED_MBS_2026-07-04.md`, or move it under `docs/archive/`, because it states that an implemented environment variable does not exist.
- [x] Do not rewrite historical default values inside `docs/archive/`; preserve them as historical evidence.
- [x] Add this plan as a P1 engineering-hardening item in `docs/ROADMAP.md` when implementation is approved.

### Acceptance criteria

- Searching active documentation for a flag name yields the canonical default or a clearly labelled override.
- No active document presents a non-existent Python attribute as a current `FeatureFlags` field.
- Archived documents remain visibly non-authoritative.

## 8. Workstream D: Environment and Deployment Profiles

Priority: P0

### Environment-loading decision

Choose one policy and apply it to API, worker, tests, and local commands:

1. **Recommended:** load `.env` only at the application/process boundary, before importing the module-level feature flags; keep domain code dependent on `os.environ` rather than on Pydantic or dotenv.
2. Alternatively, define every flag in `src.config.Settings` and inject a constructed `FeatureFlags` instance. This is a larger refactor and must cover Celery workers as well as FastAPI.

Do not make `src/domain/state/feature_flags.py` load files directly; filesystem-aware configuration belongs at the process boundary.

Change 3 selected policy 1. FastAPI and Celery load `.env` at their process
boundaries, exported values take precedence, tests disable implicit loading,
and containers consume the host-interpolated Compose profile with in-container
dotenv loading disabled. The base stack is a feature-rich local profile.

### Tasks

- [x] Document the selected loading policy in README and operations documentation.
- [x] Update the documented bare local command to load `.env` explicitly if policy 1 is selected.
- [x] Expand `.env.example` to list all 28 primary environment variables.
- [x] Place canonical code defaults in one clearly labelled section.
- [x] Place local/staging safety overrides, such as `INFERRA_AUTH_ENABLED=true`, in a separate clearly labelled section.
- [x] Convert Compose flag values to explicit profile substitutions where operator override is intended, for example `${INFERRA_AUTH_ENABLED:-true}`.
- [x] Decide whether the base Compose stack is a feature-rich demonstration profile or a conservative local profile, then document that decision.
- [x] For ontology post-reasoning, enable both
  `INFERRA_ASYNC_POST_REASONING=true` and
  `INFERRA_GENERATE_POST_REASONING_TTL=true`, wire the publisher call path, and
  prove the selected path end to end.
- [x] Verify that API and worker containers receive the same session-relevant flag values when both participate in one workflow.
- [x] Ensure production configuration fails closed for required auth and secret policies without changing the conservative `AUTH_ENABLED=false` library default.

### Acceptance criteria

- The same documented environment produces the same effective snapshot in the API and worker.
- A root `.env` setting has a deterministic, tested effect or is explicitly documented as Compose-interpolation-only.
- Compose contains no half-enabled multi-flag workflow.

## 9. Workstream E: Runtime Wiring and Flag Retirement

Priority: P1 after the P0 alignment work

Every registered Boolean must either select a production behaviour, be frozen as an invariant pending removal, or be removed through a compatibility migration.

| Flag | Change 4 result | Recorded disposition |
| --- | --- | --- |
| `use_hypergraph` | API, worker, and session creation reject unsupported `false` | Keep direct construction for migration tests, then remove the environment off ramp after graph-read compatibility closes |
| `layered_memory` | API, worker, and session creation reject unsupported `false` | Keep required `true` until the obsolete switch is removed |
| `legacy_iterate` | Both legacy and `IterationEngine` branches remain tested | Keep the compatibility default until parity is signed off; change/remove it only in a dedicated migration |
| `ml_optimized_dfs` | Session rule parsing passes stored history only when the flag is enabled | Retain as an optional, observable topology strategy |
| `hybrid_orchestrator` | Stalled unresolved sessions invoke the application orchestration service, which selects legacy/hybrid from the frozen snapshot | Retain; terminal determined goals explicitly skip alternate reasoning |
| `generate_post_reasoning_ttl` | Startup enforces equality with `async_post_reasoning`, and the publisher requires both | Retain as a companion gate for this compatibility window; consider consolidation later |
| `prov_o_trace` | Trace export returns unavailable unless the frozen session gate is enabled | Retain as the explicit trace-availability gate |
| `enriched_api` | Provenance sources, semantic suggestions, and reasoning metadata are emitted only when enabled, without changing schemas | Retain as the response-enrichment gate |
| `strict_port_contracts` | Startup requires `true`; CI architecture/port gates are unconditional | Mark retirement pending and remove the runtime environment name in a later compatibility migration |
| `reasoning_router` | A factory selects `ReasoningRouter` versus `NullReasoningRouter` and is called by session orchestration | Retain and construct from the frozen session snapshot |
| `confidence_thresholds` | Router construction receives the frozen value and enabled/disabled pruning remains tested | Retain as an observable reasoning policy |

All 24 Boolean flags now have an approved production consumer or required
runtime invariant. A metadata-driven source check fails if a consumer is
removed without updating the approved consumer mapping and its tests.

### Default-change rule

Do not change a code default merely to match Compose. Any default change requires:

- a decision entry in `docs/INFERRA_Production_Decision_Register.md` or the legacy retirement register;
- a schema/session compatibility assessment;
- updated tests, documentation, and deployment profiles in the same change;
- rollback instructions;
- proof that existing frozen sessions remain valid.

## 10. Workstream F: Runtime Visibility

Priority: P1

### Tasks

- [x] Log a redaction-safe effective flag snapshot once at API and worker startup.
- [x] Include deployment profile name, process role, and a stable snapshot hash in startup logs.
- [x] Add a protected read-only system endpoint or operator CLI that reports:
  - canonical defaults;
  - current process-effective values;
  - source classification where available;
  - legacy-retirement readiness.
- [x] Keep per-session snapshots available through audit/provenance data without allowing mid-session mutation.
- [x] Add API/worker snapshot-hash mismatch detection for workflows that cross process boundaries.

The protected `GET /api/v1/system/feature-flags` endpoint and
`scripts/capture_feature_flag_evidence.py` expose the same canonical report.
New cross-process rule-sync, post-reasoning, and induction messages carry the
publisher hash; workers reject a mismatched effective snapshot while remaining
compatible with already-queued messages that predate the hash field.

## 11. Delivery Sequence

### Change 1: Test and documentation correction

Status: complete (2026-07-14)

- [x] Fix the missing snapshot key.
- [x] Complete the module docstring and Implementation Guide.
- [x] Correct active misleading documents.
- [x] Make no runtime behaviour changes.

### Change 2: Canonical metadata and drift checks

Status: complete (2026-07-14)

- [x] Introduce structured metadata while preserving the public constructor and snapshot.
- [x] Convert default tests and documentation checks to consume the metadata.
- [x] Add CI drift enforcement.

Validation recorded for Change 2:

- 59 metadata and documentation drift checks passed;
- 295 feature-flag, matrix, metadata, and opted-in session integration tests
  passed with 97.98% scoped coverage of `feature_flags.py`;
- 13 ontology post-reasoner tests passed;
- the repository-wide regression run reached 2,903 passes and 73 skips, but
  retains 36 failures outside this change and 89.15% coverage against the 97%
  release threshold;
- the import-boundary gate retains three existing AEGIS domain-to-adapter
  violations. These repository-wide regression and architecture gates remain
  open for Change 5 and were not broadened into Change 2.

### Change 3: Environment/profile consistency

Status: complete (2026-07-14)

- [x] Implement the selected `.env` loading policy.
- [x] Complete `.env.example`.
- [x] Normalize API/worker/Compose profiles.
- [x] Resolve the post-reasoning two-gate inconsistency.

Validation recorded for Change 3:

- 367 focused flag, environment, auth, readiness, Celery, and post-reasoning
  tests passed;
- 9 opted-in session flag-flip integration tests passed;
- 310 metadata/environment tests passed with 97.78% combined scoped coverage
  of `feature_flags.py` and `environment.py`;
- the rendered Compose configuration contains the same 28-entry feature-flag
  profile for API and worker and contains no half-enabled post-reasoning gates;
- no canonical code default changed.

### Change 4: Wiring and retirement

Status: complete (2026-07-15)

- [x] Work through the decision table one flag at a time.
- [x] Keep each behaviour change isolated and reversible.
- [x] Update the legacy and production decision registers.
- [x] Prove every Boolean flag has an approved production consumer or runtime invariant.

Validation recorded for Change 4:

- 454 focused state, service, orchestration, reasoning, HTTP-reasoning, and
  task tests passed;
- 16 focused inference response/orchestration gate tests and 9 opted-in
  session-stickiness integration tests passed;
- 131 registry/factory/orchestration tests passed with 97.67% scoped coverage;
- the complete inference-router file now reaches 66 passes and retains 8
  failures from the existing non-flag auth/question-flow/reference-fixture
  baseline;
- import-linter reports the same three pre-existing AEGIS
  domain-to-persistence-adapter violations and no new Change 4 violation;
- no canonical environment name, snapshot key, or code default changed.

### Change 5: Release evidence

Status: complete for the locally available scope; external environment gates pending (2026-07-16)

- [x] Execute the complete functional regression plus architecture, rendered
  Compose, benchmark, Phase 5 acceptance, and infrastructure guardrail gates.
- [x] Attach effective flag snapshots for the tested API and worker process
  environments.
- [x] Update `docs/IMPLEMENTATION_STATUS.md` and `docs/ROADMAP.md` with the
  verified outcome.

Validation recorded for Change 5:

- a clean `scripts/verify_release_candidate.ps1` run completed with the
  unavailable frontend, live-smoke, load, and chaos inputs explicitly skipped;
- the integrated backend suite passed 3,437 tests with 73 skips and reached
  22,206 of 22,889 statements, or 97.016%, with 683 statements missing;
- the unchanged `coverage report --fail-under=97` policy passes;
- import-linter checked 243 files and 722 dependencies; both contracts pass;
- the Phase 5 acceptance suite passed 7 tests, infrastructure release gates
  passed 39 tests with 3 skips, and benchmarks passed 22 tests with 3 skips;
- local and production-overlay Compose renders produced matching API/worker
  snapshot hashes:
  `789dc53dcb8fc3e67ae9b80801628a97ef45967a6443d8315e1d791ff44b215b`;
- the release script now writes
  `artifacts/release/feature-flag-snapshots.json` and fails on API/worker drift;
- live smoke, load, and chaos were not claimed by this local evidence run, and
  the two frontend directories referenced by the script are not present in this
  workspace. Those inputs remain required before declaring the broader release
  evidence packet complete.

## 12. Validation Matrix

| Gate | Validation | Latest result |
| --- | --- | --- |
| Canonical inventory | Metadata contains exactly 28 entries and snapshot contains the same 28 keys | Pass |
| Code defaults | No-environment `FeatureFlags().snapshot()` matches the canonical table | Pass |
| Environment parsing | Primary names, alias, valid values, invalid values, and precedence are covered | Pass |
| Session safety | All session-affecting flags are frozen and survive store round trips | Pass |
| Production wiring | Every retained flag has enabled/disabled branch evidence | Pass |
| Documentation | Active tables and examples contain only canonical names and labelled overrides | Pass |
| Compose | API and worker effective snapshots match the rendered profile | Pass for local and production-overlay renders |
| Post-reasoning | Both required gates and the publisher/worker path pass an end-to-end test | Pass |
| Architecture | `lint-imports --config .importlinter` passes | Pass; 2 of 2 contracts kept |
| Regression | `pytest --cov=src --cov-fail-under=97` passes | Pass: 3,437 passed, 73 skipped; 22,206/22,889 statements (97.016%) |
| Release | `scripts/verify_release_candidate.ps1` completes and captures flag evidence | Pass for locally available gates; frontend, live smoke, load, and chaos explicitly skipped and still pending |

## 13. Completion Criteria

- [x] All 28 entries have one canonical metadata definition.
- [x] All duplicated production defaults are mechanically checked against it.
- [x] The stale matrix test is fixed.
- [x] Active documentation includes the complete inventory.
- [x] `.env.example` includes every primary environment name and labels overrides.
- [x] Local, API, and worker environment-loading behaviour is deterministic.
- [x] Base and production Compose profiles are documented and internally consistent.
- [x] Every retained Boolean has a proven production consumer.
- [x] Invariant or obsolete flags have an approved freeze/retirement path.
- [x] No archived default is treated as current acceptance guidance.
- [x] Full functional regression, import-boundary, and rendered Compose parity checks pass.
- [x] Repository coverage reaches 97% and the locally available release-candidate gates pass.
- [ ] Frontend builds and live smoke, load, and chaos gates pass in their owning workspaces/environment.

## 14. Rollback Strategy

- Land documentation/test-only corrections separately from runtime changes.
- Preserve existing environment names and snapshot keys during metadata refactoring.
- Introduce deprecation warnings before removing any flag.
- Keep old and new execution paths available for one compatibility window when changing `legacy_iterate`, orchestration, or routing selection.
- Roll back deployment-profile changes by restoring the previous environment block; do not alter canonical defaults as an operational rollback mechanism.
- Existing frozen sessions must either continue under their captured snapshot or be explicitly invalidated through a versioned session migration.

## 15. Files Expected to Change

| File or area | Planned change |
| --- | --- |
| `src/domain/state/feature_flags.py` | Canonical metadata, complete documentation, validation helpers |
| `tests/domain/state/test_feature_flags.py` | Metadata-driven default and environment tests |
| `tests/domain/state/test_feature_flag_matrix.py` | Repair missing key and remove hand-maintained drift |
| `tests/domain/state/test_feature_flag_metadata.py` | Canonical shape, environment, duplicate-default, and active-document drift checks |
| `tests/integration/test_feature_flag_flip.py` | Full session-sticky coverage |
| `tests/tasks/test_ontology_post_reasoner.py` | Two-gate and end-to-end post-reasoning coverage |
| `src/infrastructure/environment.py` | Deterministic process-boundary dotenv loading |
| `tests/infrastructure/test_environment.py` | Loading precedence, isolation, and entry-point checks |
| `src/main.py`, `src/tasks/celery_app.py`, `src/config.py` | Load and validate configuration once at API/worker startup |
| `src/domain/inference/session_service.py` | Enforce session invariants and select ML history ordering |
| `src/domain/inference/backward_chain_orchestrator.py` | Route stalled inference into abduction/induction once per session |
| `src/adapters/outbound/reasoning/factory.py` | Build the real or null router from one frozen snapshot |
| `src/services/inference_orchestration_service.py` | Compose and run the selected session orchestrator/router |
| `src/adapters/inbound/http/routes/inference.py` | Wire stalled-session orchestration, post-reasoning, trace, and enriched response gates |
| `src/adapters/inbound/http/routes/reasoning.py` | Prevent request fields from bypassing process reasoning gates |
| `tests/services/test_inference_orchestration_service.py` | Application composition and frozen-snapshot coverage |
| `tests/adapters/outbound/reasoning/test_reasoning_factory.py` | Real/null router and flag-propagation coverage |
| `IMPLEMENTATION_GUIDE.md` | Complete inventory and value taxonomy |
| `README.md` | Link to canonical inventory and document loading policy |
| `.env.example` | Complete flag list plus labelled profile overrides |
| `docker-compose.yml` | Explicit, internally consistent local profile |
| `docker-compose.prod.yml` | Explicit production-profile differences |
| `docs/archive/future-and-enhancements/INFERRA_Strategic_Plan_and_Innovation_Roadmap.md` | Remove or relabel non-canonical flag names |
| `docs/INFERRA_Legacy_Retirement_Register.md` | Record freeze/retirement decisions and gates |
| `docs/INFERRA_Production_Decision_Register.md` | Record approved default or deployment-policy changes |
| `docs/ROADMAP.md` | Track approved implementation work |
| `.github/workflows/ci.yml` | Add an explicit canonical metadata and documentation drift gate |
| CI/scripts | Add effective-profile checks in later deployment work |
