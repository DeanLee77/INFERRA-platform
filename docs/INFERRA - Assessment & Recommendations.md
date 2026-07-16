# INFERRA - Assessment & Recommendations



> Prepared during the VERIDA re-platforming effort and revalidated on 2026-07-16

> against the latest uncommitted `feature/enhancement` working tree. The committed

> local tree at `e32ddca` is content-identical to `development` at `99f40b2`, but

> the candidate working tree contains substantial additional changes. The initial

> inventory contained 69 tracked

> files differing from `development` and 110 untracked files. After repository

> hygiene, `.coverage.*` is ignored and this assessment is explicitly unignored,

> leaving 52 visible untracked files. Inspection covered

> `models.py`, the

> hexagonal domain/port/adapter layout (118 domain files, 14 ports, 73 adapters),

> the 5-phase feature-flag model, the reasoning and ontology modules, the LLM

> configuration, and the AEGIS / provider_verification / snomed_mbs subsystems.

>

> **Confidence note.** High confidence on the domain model, persistence, release

> tooling, feature flags, authentication, Redis sessions, ontology flows, and

> operational artifacts (read directly from code and tests). Medium confidence on

> scope-coherence and production capacity because staging evidence and deployment

> decisions remain external. A targeted release-risk suite passed 162 tests with 2

> skips, and both import-linter contracts passed. A new full-suite run reached 6%

> without failure before the review timebox expired; the repository's retained

> release evidence reports 3,437 passed, 73 skipped, and 97.016% coverage.



---



## 1. Executive summary



INFERRA is **a genuinely thoughtful reasoning platform whose current working tree

is close to a backend release candidate, but is not yet a reproducible or

operationally approved production release.**



The expertise is real: provenance as a first-class type, flag-gated LLM paths

with deterministic fallback, ontology assist modes, frozen runtime profiles, and

reasoning-first routing are all

signs of a team that understands neuro-symbolic AI and has real-world scar tissue.

The immediate weaknesses are release discipline and unresolved production

decisions: the intended candidate is spread across a dirty working tree, schema

migration is performed at runtime, Redis sessions deserialize pickle, frontend

and OpenAPI release inputs are incomplete, ontology needs live end-to-end proof,

and auth/secret/deployment policy is not signed off. The relational schema, broad

product surface, and multi-service footprint remain important post-release

architecture concerns, but attempting those redesigns before launch would add

more risk than it removes.



The recommendation is therefore two-horizon: **stabilize and prove a narrow,

deterministic first release**, then improve persistence, provenance, module

boundaries, LLM governance, and infrastructure using production evidence.



---



## 2. What to keep (do not touch)



These are INFERRA's strengths. Preserve them through any refactor.



1. **The centralized feature registry and frozen runtime snapshots.** Defaults are

   not simply "Phase 1 ON, Phases 2-5 OFF": some Phase 1 capabilities are off and

   later-phase contract/router flags are on. The strength is the canonical

   28-entry registry, API/worker snapshot hashing, start-of-session stickiness,

   fail-fast invariants, and worker rejection of publisher/worker profile drift.

   Keep this as the release-safety spine.

2. **FactSource as a first-class type** (`ASSERTED / INFERRED / LEARNED /

   HYPOTHETICAL / SEMANTIC`). Provenance typing is designed, not bolted on.

3. **Flag-gated LLM adapters with deterministic fallback.** LLM use is broader

   than goal-mapping and abduction: it also covers conversion, prompting,

   explanation, ontology query, workflow authoring, and evidence summaries. Keep

   the timeout/retry/circuit-breaker, prompt sanitization, bounded candidate, and

   fallback design. Treat `allowed_operations`, per-product `budget`, and

   `evaluation_gate_status` as configuration metadata until runtime enforcement

   is implemented; do not describe them as a complete governance boundary.

4. **Ontology as five assist modes**, not a single on/off switch. This nuance only

   comes from actually operating such a system.

5. **Adapter-free domain and protected port boundaries.** Import Linter currently

   keeps the domain free of adapters and keeps ports free of adapters,

   infrastructure, services, and entrypoints. Some domain files do import the

   infrastructure logging helper, so the domain is not fully infrastructure-free;

   preserve the enforced boundaries and move logging behind a domain-safe facade

   later if full hexagonal purity is desired.

6. **Reasoning-first routing** (deduction before abduction/induction). Keeps the

   symbolic core authoritative and deterministic.



---



## 3. Longer-term architecture recommendations



These are strategic design recommendations, not the first-production-release

sequence. Section 5 identifies the work that should block or explicitly constrain

the initial release.



### A1 - Fix the persistence layer (high impact, high effort)



This is the sharpest disconnect in the system: an excellent domain model stored

on a primitive schema. The good model does not survive contact with the tables.



**Findings**

- **Implicit rule versioning.** Versioning is "latest file wins" by timestamp

  (`get_latest_file()`), with no explicit version rows and no status lifecycle in

  the schema. For a governance-critical system, first-class rule versioning is not

  optional.

- **Rules stored as `LargeBinary` blobs**, reparsed on load. Execution is fine,

  but rule *structure* cannot be queried without deserializing everything;

  diffing, impact analysis, and "which rules reference fact X?" are painful.

- **Legacy rule `history` is a single JSON column.** INFERRA also has a normalized

  `history_record` table for per-rule/per-node true/false counters, and AEGIS has

  a richer event ledger. Neither replaces normalized, immutable core decision

  provenance linked to rule and ontology versions. The provenance *thinking* is

  excellent in

  the domain but the *storage* is a JSON dump, undermining queryability and audit.



**Recommendations (PostgreSQL-native)**



INFERRA is Python + **PostgreSQL**, so these use Postgres types and features

directly, `uuid` PKs, `text` + `jsonb`, `timestamptz`, native `CHECK`,

partial/GIN indexes, `EXCLUDE` constraints, and triggers, not a lowest-common-

denominator schema.



1. **Introduce explicit version rows** (`rule_set` + `rule_set_version`) with a

   real status lifecycle as a Postgres `enum` or `CHECK`

   (`draft | approved | active | superseded | retired`), a `source_hash`, and an

   effective-date range. Make `source_text` the canonical form. Use a

   `tstzrange` on `(effective_from, effective_to)` and an **`EXCLUDE` constraint**

   so two `active` versions of the same rule set can never overlap in time, a

   guarantee "latest-file-wins" cannot make.

2. **Add a derived, read-only graph projection** (`rule_node` / `rule_edge`),

   rebuilt from parsed text at approval and keyed by the `source_hash` it was

   derived from. The engine still parses text at load; the projection serves

   query/explorer/impact-analysis APIs. Keep it explicitly non-authoritative to

   avoid dual-source-of-truth drift. Index `node_name` and the edge endpoints so

   "which rules reference fact X?" is a single indexed query.

3. **Normalise history/provenance** so decisions link to rule version, semantic

   version, fact sources, and engine build as columns/FK rows, keeping only the

   genuinely variable payload in `jsonb` (queryable via GIN, unlike a `text` blob).

   Enforce **append-only at the DB level** with a `BEFORE UPDATE OR DELETE`

   trigger raising an exception, not by application convention.

4. **Enforce constraints in the schema**: `NOT NULL`, `CHECK` on status/enum

   columns, `UNIQUE` where the domain requires it, and explicit FK

   `ON DELETE` behaviour, `RESTRICT` for governed artefacts (rules, history),

   `CASCADE` only for truly-owned children (files, imports, projection rows).



*(VERIDA already implements this normalisation on SQLite; the shape below is the

PostgreSQL-native equivalent recommended for INFERRA itself.)*



**Recommended rule-related ER design**



The core correction is visible in one diagram: replace the flat

`rule → file(blob) / history(json)` model with explicit versioning, a derived

graph projection, and normalised decision provenance.



```mermaid

erDiagram

    RULE_SET ||--o{ RULE_SET_VERSION : "has versions"

    RULE_SET_VERSION ||--o{ RULE_FILE : "attaches sources"

    RULE_SET_VERSION ||--o{ RULE_IMPORT : "declares imports"

    RULE_SET_VERSION ||--o{ RULE_NODE : "projects (derived)"

    RULE_SET_VERSION ||--o{ RULE_EDGE : "projects (derived)"

    RULE_SET_VERSION ||--o{ RULE_DECISION : "produces"

    RULE_NODE ||--o{ RULE_EDGE : "connects (from)"

    RULE_NODE ||--o{ RULE_EDGE : "connects (to)"



    RULE_SET {

        uuid id PK

        text name "unique business key (UK)"

        text category

        text description

        timestamptz created_at

        text created_by

    }

    RULE_SET_VERSION {

        uuid id PK

        uuid rule_set_id FK

        int version_number "UNIQUE(rule_set_id, version_number)"

        int revision

        text source_text "CANONICAL form"

        text source_hash "sha-256; drives projection + cache keys"

        text import_tree_hash

        text parser_version

        text compiler_version

        text status "enum: draft|approved|active|superseded|retired"

        tstzrange effective_range "EXCLUDE overlap where status=active"

        timestamptz created_at

        text created_by

        text approved_by

        timestamptz approved_at

    }

    RULE_FILE {

        uuid id PK

        uuid rule_version_id FK

        text filename

        bytea content "original upload; not authoritative for logic"

        text content_hash

        text content_type

        int format_version

        timestamptz created_at

        text created_by

    }

    RULE_IMPORT {

        uuid id PK

        uuid rule_version_id FK

        text imported_set_name

        int imported_version

        text content_hash

    }

    RULE_NODE {

        uuid id PK

        uuid rule_version_id FK

        text derived_from_hash "= source_hash; staleness guard"

        text node_name "UNIQUE(rule_version_id, node_name)"

        text node_type

        jsonb payload "GIN-indexed"

    }

    RULE_EDGE {

        uuid id PK

        uuid rule_version_id FK

        text derived_from_hash

        uuid from_node_id FK

        uuid to_node_id FK

        text dependency_type

        jsonb modifiers

    }

    RULE_DECISION {

        uuid id PK

        uuid rule_version_id FK

        text session_id

        text semantic_graph_version

        text engine_build

        jsonb fact_sources "ASSERTED|INFERRED|LEARNED|HYPOTHETICAL|SEMANTIC; GIN"

        jsonb trace "PROV-O shape"

        timestamptz created_at

        text created_by

    }

```



Precise points that make this a *governance-grade* rule schema rather than a

storage dump:



- **`rule_set_version` is the pivot.** Every rule artefact (files, imports,

  projection, decisions) hangs off a *version*, never off a bare rule. This is

  what "latest-file-wins" cannot express.

- **`status` + `effective_range` with an `EXCLUDE` constraint** makes overlapping

  active versions structurally impossible:

  `EXCLUDE USING gist (rule_set_id WITH =, effective_range WITH &&) WHERE (status = 'active')`.

- **`source_hash` is the spine of correctness.** It is the canonical fingerprint,

  the `derived_from_hash` on every projection row, and the natural cache key. If a

  projection's `derived_from_hash` ≠ its version's `source_hash`, it is known-stale

  and must be rebuilt, no silent drift.

- **`rule_node` / `rule_edge` are derived and non-authoritative.** The engine parses

  `source_text`; these tables exist only so structure is *queryable* (impact

  analysis, explorer UIs) without deserialising blobs. `rule_edge` references

  `rule_node` by FK so graph traversal is a real join.

- **`rule_decision` normalises provenance.** Version/semantic/engine identifiers are

  columns/FKs (joinable, indexable); only the genuinely variable trace stays in

  `jsonb` (GIN-queryable), replacing the opaque single-column `history` JSON.

- **Append-only** is enforced by a `BEFORE UPDATE OR DELETE` trigger on

  `rule_decision` (and on any history table), not by convention.



### A2 - Contain scope sprawl (medium impact, ongoing discipline)



**Finding.** AEGIS (workflow autonomy, fraud-replay), provider_verification

(Ahpra/ABN/HPOS/Medicare), and snomed_mbs (clinical→RDF) are effectively three

different products in one repository. 118 domain files across that breadth reads

like accretion from real client demands, honest, but architecture eventually pays

for breadth. The phased flags contain the runtime blast radius; they do not

contain maintenance cost.



**Recommendations**

1. **Draw explicit module boundaries** and treat AEGIS / provider_verification /

   snomed_mbs as **optional, independently versioned modules** behind explicit

   configuration and router-inclusion gates,

   with no import path from the core into them. They can remain in one repository

   until independent ownership, security, scaling, data lifecycle, or release

   cadence justifies extraction.

2. **State the core mission narrowly** (a fenced, explainable, deterministic

   decision engine) and classify everything else as an *extension*. This makes it

   defensible to defer or extract a module without destabilising the core.

3. **Guard the boundary in CI** (a dependency-direction lint) so the core cannot

   accidentally take a dependency on a domain extension.

4. **Publish a launch capability matrix** rather than relying on repository

   location or feature flags as evidence of support. For every module, record

   whether it ships, whether its router appears in production OpenAPI, its gate,

   owner, required scopes, data classification, source of truth, SLO/runbook, and

   acceptance evidence.



### A3 - Reconsider the operational footprint (high impact, high effort)



**Finding.** Celery + Redis + Fuseki (JVM), on top of PostgreSQL, is a real

operational footprint: each component must be run, secured, backed up, observed,

and kept consistent. The repository does not contain enough target workload,

tenancy, incident, or cost evidence to conclude that it is over-provisioned.



**Recommendations (PostgreSQL stays; this is not a SQLite argument)**

1. **Evaluate queue consolidation only from measured evidence.** INFERRA already

   depends on Postgres, so Celery + Redis could be replaced by a **Postgres-backed durable

   job queue** using `SELECT ... FOR UPDATE SKIP LOCKED` for lease-based claiming

   (or `LISTEN/NOTIFY` for wake-ups). This can keep job state transactional with

   the data it operates on and may remove the broker.

   It does **not** remove Redis by itself: current Redis responsibilities include

   sessions, ontology deltas, projection metadata, dead-letter records, and task

   results. Consolidate only if all required responsibilities have a deliberate

   replacement and measured benefits exceed migration risk. Keep Celery/Redis for

   the first release.

2. **Question the Fuseki/JVM dependency on its own merits.** The triple store is a

   real architectural need; the *JVM service* may not be. Evaluate whether an

   embedded or Postgres-hosted RDF option (e.g. an in-process quadstore, or

   RDF-over-Postgres) meets the query/reasoning needs, versus running Fuseki as a

   separate JVM service. Keep Fuseki if SPARQL performance or scale genuinely

   requires it, drop it if it is inherited rather than needed.

3. **If multi-node is genuinely required**, keep the current stack but document

   *why*, so the footprint is a decision rather than an inherited default.

4. **Make cross-store consistency explicit.** PostgreSQL and the triple store do

   not share a transaction; coordinate them via a **transactional-outbox pattern**

   (write the outbox row in the same Postgres transaction as the data, then a

   worker projects to the triple store) and versioned publication, rather than

   best-effort dual writes.



> **Note.** VERIDA's choice of SQLite + an embedded quadstore is a deliberate bet

> for a *different* (single-node, no-JVM) deployment target and is **not** a

> recommendation for INFERRA. For INFERRA, the equivalent win is consolidating

> onto the PostgreSQL it already operates, not swapping databases.



---



## 4. Secondary observations



- **Ontology confidence gating.** The `OntologyReasoner` producing confidence,

  derivation path, and snapshot hash is strong. The enable switch and numeric

  confidence threshold are already separate, and the threshold is configurable.

  Preserve that separation and audit the resolved threshold with each decision.

- **Semantic materialisation.** Idempotent writes keyed by `source_hash`

  and post-write triple-count/content checks are good. The rule projection still

  updates a stable named graph with delete/insert semantics; after launch, consider

  immutable versioned graph creation followed by an atomic current-pointer swap:

  build then swap, never clear then rebuild. A partial or failed replacement must

  never become "current".

- **LLM key storage.** Storing an encrypted provider-key value in the DB

  (`api_key` is the column name) is defensible; keep the **encryption key in the

  environment, not the DB**, and support key rotation (retain previous keys until

  re-encryption completes).

- **Audit as a knowledge graph (opportunity, not a gap).** INFERRA already has a

  PROV-O-shaped trace and a triple store. Projecting decisions into a versioned

  PROV-O audit graph (async via the transactional outbox, **PostgreSQL-

  authoritative**) would yield a SPARQL-queryable, reason-able, legally traceable

  audit trail at moderate cost. Worth considering as a bounded, flag-gated

  capability.



---



## 5. Recommendation assessment

The current working tree should be treated as a candidate under construction,

not as a releasable artifact. Backend correctness evidence is strong: the retained

report records 3,437 passed tests at 97.016% coverage; the focused auth, Redis

session, feature-flag, rule-sync, ontology post-reasoning, and metrics slice passed

162 tests with 2 skips during this review; and both import contracts pass across

243 files and 722 dependencies. The remaining risk is concentrated in candidate

reproducibility, security/data boundaries, operational proof, and unresolved

launch policy.



### Authoritative priority order



This matrix is the authoritative ordering for the recommendations in this

document. Section 3's `A1`-`A3` identifiers name architecture themes; they are not

delivery priority levels.



- **P0:** required for the first production release or for activation of the

  affected capability. Release requires completion or an explicitly named and

  time-bounded risk acceptance where the row permits one.
- **P1:** first hardening release immediately after production, or before enabling

  an optional capability such as live LLM use.
- **P2:** subsequent architecture/governance release after ownership and client

  migration prerequisites are available.
- **P3:** optional, evidence-driven optimization; do not schedule from architectural

  preference alone.



| Order | Recommendation | Priority | Timing | Depends on | Release effect |
| ---: | --- | :---: | --- | --- | --- |
| 1 | R0: Produce one immutable, reproducible candidate | P0 | Before release | None | Blocks the entire release |
| 2 | R1: Freeze product scope, routes, roles, secrets, and security posture | P0 | Before release | Candidate scope identified | Blocks the entire release |
| 3 | R2: Add migrations, minimum Rule constraints, revision identity, backfill, restore proof, and decision freezing | P0 | Before release | Schema and launch surface frozen | Blocks release; narrowly defined exceptions require named owner, expiry, and compensating controls |
| 4 | R2: Remove pickle session deserialization | P0 or P1 | Before release unless a trusted-Redis exception is signed; otherwise first hardening release | Session schema and deployment trust boundary | Blocks release when Redis is not fully trusted; signed exception must expire |
| 5 | R3: Prove the complete production-profile stack in staging | P0 | Before release | R0-R2 complete | Blocks the entire release |
| 6 | R4: Complete ontology observability and reconciliation | P0 conditional | Before ontology-derived facts can affect production decisions | Ontology capability enabled and staging stack available | Blocks ontology activation; not the deterministic-only release if ontology reasoning is off |
| 7 | R5: Close API/client, OpenAPI, frontend, legacy-route, and document gaps | P0 | Before release | R1 launch contract | Blocks release contract/sign-off |
| 8 | Normalize core Rule persistence and append-only decision provenance | P1 | First post-release persistence milestone | Migration baseline, revision identifiers, client compatibility plan | Does not block the narrow first release after R2 controls pass |
| 9 | Expand the minimum outbox into durable replay and reconciliation | P1 | First post-release reliability milestone | Minimal pre-release outbox and operational ownership | Does not block release if async projection is disabled; otherwise the minimal outbox is P0 |
| 10 | Enforce LLM operations, evaluation gates, budgets, model/prompt versions, and durable usage | P1 conditional | Before enabling live LLM capabilities | Provider/model policy and evaluation set | Blocks LLM activation, not deterministic release |
| 11 | Replace any temporarily accepted pickle envelope with a schema-safe session format | P1 | First hardening release | Session schema/migration design | Required by the exception expiry in row 4 |
| 12 | Make core, AEGIS, provider verification, and SNOMED/MBS deployable module boundaries | P2 | Subsequent architecture release | Capability owners, schema ownership, dependency rules | Does not block narrow release if unapproved modules are absent from production routes |
| 13 | Retire legacy iterate, matrix shims, obsolete flags, and `/service/*` | P2 | After client and stored-payload migration | Parity, compatibility, rollback, and client evidence | Does not block release while compatibility paths are controlled |
| 14 | Build the governance-grade PostgreSQL decision audit and PROV-O audit projection | P2 | Governance/audit release | Normalized decisions and durable outbox | Required when contractual/regulatory audit scope demands it |
| 15 | Consolidate Celery, Redis, or Fuseki | P3 | Only after production measurement | Queue, SPARQL, recovery, incident, and cost evidence | Never a first-release blocker |



Priority conflicts are resolved in favor of the earlier row. A conditional row

becomes P0 as soon as its capability is included in the signed launch capability

matrix. Every P0 exception must identify the risk owner, compensating controls,

expiry date, and the P1 item that removes the exception.



### 5.1 Required before the first production release



#### R0 - Produce one immutable, reproducible candidate (release blocker)



1. Commit every intended source file, test, script, reference artefact, and active

   source-of-truth document. **Completed 2026-07-16:** the reviewed source,

   tests, scripts, governed active/archive documents, and approved reference

   examples are included in the immutable local candidate commit. Generated

   coverage databases and release output remain excluded.
2. Keep coverage databases and generated release output out of Git status.

   **Completed:** `.gitignore` now ignores both `artifacts/` and `.coverage.*`;

   the 59 existing coverage databases remain on disk but no longer appear in the

   candidate manifest.
3. Decide whether this assessment is an audit attachment or a maintained project

   document. **Completed using the recommended default:** the file is explicitly

   unignored from `docs/*` and is now treated as governed release documentation.

   It must be reviewed and staged with the candidate.
4. Create the candidate from a clean checkout and attach the commit SHA, dependency

   lock hash, container image digests, feature-flag snapshot hashes, test/coverage

   output, benchmark output, and import-linter report to one evidence bundle.
5. Generate `openapi.json` in CI and fail on drift. Make the dependency audit,

   backend coverage, import contracts, Docker build, OpenAPI drift, and candidate

   evidence jobs required branch-protection checks.



**Candidate inventory refreshed 2026-07-16 after documentation archival**



| Classification | Count | Contents | Required disposition |
| --- | ---: | --- | --- |
| Modified tracked candidate content | 69 | Configuration/documentation/release files, production source files, and existing tests | Review as one integrated feature-alignment and release-hardening change set |
| Tracked deletion represented by an archive move | 1 | Root `fuseki_connection.md`, preserved as `docs/archive/operations-notes/fuseki_connection_root_legacy.md` | Stage the deletion and archived destination together |
| Untracked candidate content | 60 | 5 active/governance documents, 8 archive documents, 16 reference examples, 1 feature-snapshot evidence script, 3 production modules, and 27 tests | Approved for the candidate; inclusion and redistribution of the 16 reference examples was explicitly authorised on 2026-07-16 |
| Generated residue | 59 | `.coverage.*` databases | Completed: ignored by `.coverage.*`; never stage these files |
| Generated release evidence outside status | 5 at review time | Coverage JSON and feature-snapshot JSON under `artifacts/release/` | Retain as CI/release-run artifacts, not source files |



The three new production modules are not optional residue:

- `src/infrastructure/environment.py` is imported by the API and Celery worker.
- `src/ports/aegis_repository_ports.py` is imported by AEGIS domain and persistence

  code.
- `src/services/inference_orchestration_service.py` is imported by the inference

  route.

The new `scripts/capture_feature_flag_evidence.py` is called by the release-

candidate script and tested directly. Omitting any of these four files would make

the candidate incomplete.



**Proposed staging boundary**



- Stage the 69 tracked modifications and the root Fuseki-note archive move after
  code review.
- Stage the 5 active/governance documents, 8 governed archive documents,
  evidence script, 3 production modules, and 27 new

  tests.
- Stage the 16 reference examples. Inclusion and redistribution in this
  repository was explicitly authorised on 2026-07-16.
- Do not stage `.coverage.*` or files below `artifacts/`.
- Stage the archived `docs/archive/phase-plans/FEATURE_FLAG_ALIGNMENT_PLAN.md`
  with the documentation-governance change; its disposition is now decided.
- Stage this assessment after documentation review; its governed-document status

  is now decided.

**Local validation refreshed 2026-07-16:**

- The full local release-candidate command was started but reached its ten-minute
  execution ceiling at 6% of the 3,510-test backend suite with no reported test
  failure. This interrupted run is not counted as a new full-suite pass.
- The last completed full candidate result remains 3,437 passed, 73 skipped, and
  97.016% coverage; the subsequent repository changes are documentation archival
  and governance updates.
- Focused feature-flag, environment, evidence, orchestration, and reference-example
  validation passed 338 tests.
- Phase 5 acceptance passed 7 tests; benchmarks passed 22 with 3 skipped;
  infrastructure guardrails passed 39 with 3 skipped.
- Import Linter analysed 243 files and 722 dependencies with both architecture
  contracts kept. `git diff --check` passed.

`git diff --check` reports no whitespace errors for the current candidate.
Documentation archival moves and reference-example approval have been applied.
This inventory defines the boundary of the immutable local candidate commit.



**Exit criterion:** a clean clone of one SHA produces the same images, API schema,

feature snapshot, and release-gate result without using ignored local files.



#### R1 - Freeze the first-release product and security posture (release blocker)



1. Resolve the production decision register: deployment target and resource

   sizing, secret manager, auth model, ontology ownership/retention, staging

   acceptance, and named release sign-off. `[~]` is not a release state.
2. Launch deterministic-first. Keep live LLM enhancements and LLM abduction off

   until provider/model/prompt/evaluation/budget policy is approved and the stored

   `allowed_operations`, `evaluation_gate_status`, and budget are actually enforced

   at the call boundary.
3. Define deployable roles and scopes. The production API-key default is only

   `read,llm:read`, while inference, rule authoring, ontology writes, files, system

   inspection, and AEGIS require other scopes. Publish a least-privilege role

   matrix and run authenticated positive/negative smoke tests for every enabled

   route family.
4. Define the first-release core narrowly: deterministic rule execution, rule

   validation, layered provenance, and only the ontology capabilities required by

   the approved launch use case. Treat AEGIS, provider verification, SNOMED/MBS,

   LLM-assisted authoring, GraphRAG, and experimental reasoning as extensions.
5. Create a launch capability matrix for every module with these required fields:

   `ships_in_first_release`, `production_router_enabled`, configuration/feature

   gate, owner, required scopes, data classification, source of truth,

   SLO/runbook, acceptance evidence, and rollback/disable procedure. Use this

   matrix as a release input rather than inferring support from code presence.
6. Expose only the products approved for launch. AEGIS, legacy `/service/*`,

   provider verification, ontology authoring, and experimental reasoning surfaces

   should be omitted from the production router/OpenAPI document unless they have

   an owner, threat model, scopes, operational runbook, and acceptance evidence.

   Make router inclusion configuration-driven; a disabled product should be absent

   from production OpenAPI, not merely return a flag or authorization error.
7. Keep extensions in the monorepo for the first release, but enforce dependency

   direction so the core cannot import them. Do not split services merely to make

   the repository look smaller; extract only for independent ownership, security,

   scaling, data lifecycle, or release-cadence requirements.
8. Move real API/JWT/CSRF/Redis/Fuseki/LLM/database secrets to the selected platform

   secret manager. Verify rotation, revocation, log redaction, TLS termination,

   network isolation, and non-default credentials in the target environment.



**Exit criterion:** the enabled API surface, roles, secrets, data ownership, and

optional-feature posture are explicit and tested in the production profile.



#### R2 - Establish safe database and session-state operations (release blocker or signed exception)



1. Introduce versioned PostgreSQL migrations (Alembic or an equivalent migration

   runner) and create a baseline for both core and AEGIS databases. Do not depend

   on request/startup-time `create_all()` and ad-hoc `ALTER TABLE` for production

   evolution. Test upgrade from the last deployed schema and rollback/forward-fix.
2. Apply minimum core Rule constraints through those migrations:

   - `rule.name` must be `NOT NULL` and unique under an explicit normalized or

     case-insensitive naming policy, such as a stored normalized key or `citext`.
   - Rule-file `rule_id`, content, source hash, and creation timestamp must be

     `NOT NULL`, with explicit FK deletion behavior. Use `RESTRICT` for governed

     revisions and `CASCADE` only for genuinely owned, non-audit children.
   - Add an index supporting current lookup order, at minimum

     `(rule_id, created_date DESC, file_id DESC)`, plus indexes for source hash and

     externally queried business keys.
   - Use timezone-aware database timestamps and database-side defaults.
3. Make every new rule-file row an immutable revision. Add a monotonic revision or

   version number, `source_hash`, content/format type and schema version,

   parser/compiler version, `created_by`, `created_at`, and import-tree hash. Never

   update revision content after creation; corrections create another revision.
4. Align the API with the real semantics. Either implement governed versions now

   or temporarily call the current append-only file resources "revisions". Do not

   present timestamp-selected blobs as approved/active versions. Preserve existing

   file IDs and publish compatibility behavior for current clients.
5. Make core rule creation, revision creation, and publication intent one database

   transaction whenever asynchronous ontology projection is enabled. Insert a

   minimal PostgreSQL outbox row with the rule revision; publish it after commit

   and retain retry/reconciliation status. This closes the current commit-then-

   best-effort-publish gap without requiring the full post-release provenance

   redesign.
6. Define and rehearse the migration/backfill from existing `rule`, `file`, and

   `history` rows. Derive deterministic revision numbers and hashes, detect

   duplicate/case-colliding names, quarantine invalid rows, preserve old IDs or a

   durable ID map, verify counts/hashes, and document rollback or forward-fix.
7. Perform and time a restore drill for both PostgreSQL databases, Redis loss, and

   the Fuseki dataset. Record RPO/RTO, retention, encryption, ownership, and the

   rebuild procedure for derived RDF projections.
8. Remove pickle deserialization from Redis sessions before Redis crosses a trust

   boundary. If the first release temporarily retains it, require isolated Redis,

   ACLs and TLS where applicable, no externally writable keys, signed/encrypted

   envelopes, a documented remote-code-execution risk acceptance, and a dated

   replacement milestone. A version number and `isinstance` check do not make

   `pickle.loads()` safe.
9. Freeze each executed decision to immutable identifiers available today: rule

   file/version ID, rule source hash, import-tree hash, ontology snapshot hash,

   feature snapshot hash, and engine build. This is the minimum audit bridge until

   the normalized post-release schema exists.



**Exit criterion:** schema upgrades, core Rule revision constraints, legacy-data

backfill, outbox publication, and restores are repeatable; session-state

risk is removed or formally accepted, and decisions can be reproduced from frozen

artefact identifiers.



#### R3 - Prove the complete stack in staging (release blocker)



1. Run the aggregate release script without `SkipDockerSmoke`, `SkipLoad`, or

   `SkipChaos`, using the production overlay and retained logs/results.
2. Exercise the real ontology loop: rule save -> Celery publish -> RDF compile ->

   Fuseki update -> projection integrity check -> post-reasoning -> Redis delta ->

   semantic-layer injection -> enriched response/PROV-O trace.
3. Repeat the 500-VU gate with production worker counts, connection pools, auth,

   telemetry, and representative rule/ontology sizes. Include soak tests and

   concurrent writes, not only read/health probes.
4. Demonstrate multi-worker session handoff, optimistic-conflict handling, Celery

   retry/DLQ recovery, Redis restart, Fuseki restart, PostgreSQL restart, worker

   loss, and recovery without silent decision or audit loss.
5. Tune alert thresholds and connect notifications to an owned channel. A dashboard

   or Prometheus rule without tested routing and a responder is not an operational

   control.



**Exit criterion:** the same candidate SHA passes functional, load, chaos,

recovery, and ontology-loop gates in the target-like environment.



#### R4 - Complete ontology observability for launch (release blocker when ontology affects decisions)



INFERRA already logs projection, post-reasoning, semantic-cache, type-bridge, and

delta activity and carries materialization traces into PROV-O artefacts. Close the

remaining gaps before enabling ontology reasoning in production:

1. Define one event contract with `event`, `correlation_id`, OTel `trace_id` and

   `span_id`, `session_id`, `task_id`, `rule_name`, `source_hash`,

   `ontology_snapshot_hash`, `graph_uri`, `operation`, `outcome`, and `duration_ms`.
2. Emit an aggregate `ontology_materialization_evaluated` event from the reasoning

   boundary with counts and bounded outcomes such as `materialized`,

   `below_threshold`, `contradiction`, `no_derivation`, and `stale_snapshot`.
3. Propagate trace context through Celery headers and create spans for queue wait,

   RDF compile, Fuseki query/update, projection verification, delta publication,

   and semantic injection.
4. Wire `inferra_fuseki_sync_total{status}` and

   `inferra_fuseki_sync_duration_seconds` into the actual production sync path;

   they are currently declared and tested but not updated by production code. Add

   low-cardinality metrics/alerts for delta lag, DLQ depth, stale projection age,

   rejected materializations, cache failures, and PostgreSQL/Fuseki divergence.
5. Never log raw SPARQL, TTL, prompts, clinical/provider fact values, or full

   derivation paths. Log hashes, bounded counts, approved identifiers, and

   redacted errors; keep high-cardinality identifiers out of Prometheus labels.
6. Add contract tests for required fields, redaction, context propagation, metric

   increments on success/failure/retry, and reconciliation alarms.



**Exit criterion:** an operator can trace one semantic decision end-to-end, detect

staleness or loss, and diagnose failure without exposing protected fact content.



#### R5 - Close API/client and release-document gaps (release blocker)



1. Decide whether the first release is API-only. The release script references two

   frontend workspaces that are absent from the current tree; either restore and

   test them or remove them from the first-release contract explicitly.
2. Freeze `/api/v1` request/response shapes against the generated OpenAPI artefact.

   Publish a migration/deprecation policy for legacy `/service/*` endpoints.
3. Reconcile this assessment, `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`,

   `OPERATIONS.md`, production readiness, and the decision/retirement registers.

   Status numbers and launch claims should be generated from the evidence bundle

   where possible, rather than copied into several documents.



### 5.2 Recommended after the first production release



1. **Normalize core rule persistence and provenance.** Implement `rule_set` and

   explicit immutable `rule_set_version` rows, lifecycle/effective-range

   constraints, canonical source text and hash, derived node/edge projections,

   and append-only decision provenance. AEGIS workflow versioning is a useful

   internal pattern, but core rules still use latest-file-wins semantics.
2. **Expand the minimum transactional outbox into durable reconciliation.** Keep

   publication

   intent with the PostgreSQL transaction, project asynchronously to Fuseki, and

   retain replayable history, leases, attempts, terminal status, operator replay,

   and reconciliation. Redis metadata/DLQ improves operability but is not a

   transactional bridge from the authoritative rule write.
3. **Replace pickle with a schema-safe session representation.** Use a versioned

   JSON/MessagePack schema composed of primitives and explicit domain

   reconstruction, with migration and compatibility tests.
4. **Make LLM governance enforceable before enabling it.** Enforce product,

   operation, evaluation-gate, per-tenant/request/token/cost budget, prompt/model

   version, and incident-disable policy at one gateway; persist usage and decisions

   durably instead of relying on a process-local cost singleton.
5. **Turn product boundaries into deployable boundaries.** Give core INFERRA,

   AEGIS, provider verification, and SNOMED/MBS explicit packages, ownership,

   configuration/router inclusion, API/version policy, and dependency-direction

   checks. Avoid sharing persistence models and tables across product boundaries;

   each extension must own its schema, migrations, retention, and repository

   interfaces even while it remains in the monorepo. Extract a service only when

   independent scaling, security, ownership,

   or release cadence justifies it.
6. **Evaluate service consolidation from measured operations.** Keep Celery,

   Redis, PostgreSQL, and Fuseki for the first release. After collecting queue

   depth, throughput, latency, incident, recovery, SPARQL, and cost data, decide

   whether a PostgreSQL job queue or alternate RDF deployment reduces total risk.

   Replacing the Celery broker alone will not remove Redis because it also carries

   sessions, deltas, metadata, DLQ records, and task results.
7. **Retire compatibility deliberately.** Remove legacy iterate, matrix shims,

   obsolete feature switches, and `/service/*` only after client migration,

   stored-payload read evidence, parity tests, and rollback plans are complete.
8. **Build governance-grade semantic audit.** Persist an append-only PostgreSQL

   decision record containing rule/ontology/engine versions, confidence gates,

   fact-source transitions, and trace IDs; asynchronously project it to a versioned

   PROV-O audit graph. Operational logs diagnose health; the audit record explains

   why a decision occurred.



## 6. Overall



The people behind INFERRA understand neuro-symbolic AI properly. The graph-first

runtime, layered provenance, ontology assist modes, deterministic-first routing,

frozen feature profiles, failure handling, and broad automated test suite are all

evidence of

real expertise. The latest backend working tree is technically substantial, but a

dirty and partly ignored working directory is not a release candidate, and local

test evidence is not production evidence. The first release should be intentionally

narrow: deterministic reasoning, only approved API modules, LLM disabled unless

separately signed off, explicit auth scopes, managed secrets, versioned database

migrations, recoverable data stores, and a fully observed ontology path.



The highest-leverage move before launch is **freeze, reduce, prove, and sign**:

produce one reproducible SHA, reduce the exposed surface, prove the real stack in

staging, and close the production decision register. After launch, re-pour the

platform's strong domain judgment onto explicit rule versioning, normalized and

append-only provenance, safe session schemas, enforceable LLM governance, durable

cross-store publication, and clearer product boundaries. Do not rewrite the core

or replace Celery/Redis/Fuseki on speculation; change them only from measured

production evidence.
