# INFERRA Account, Case, Ontology, and Provenance Architecture

Status: accepted cross-project direction; implementation incomplete
Last updated: 2026-07-20
Repositories: `inferra-platform`, `inferra-axiom`, `inferra-aegis`

## 1. Decision

INFERRA uses human-approved rule source as the behavioral source of truth and
PostgreSQL as the durable system of record. Apache Jena Fuseki is a critical
production component for versioned RDF/PROV-O query projections, but it is not
the transaction authority for rules, facts, cases, workflow transitions, or
decisions.

The target model uses a small common identity envelope and product-specific case
aggregates:

```text
Tenant / Workspace (authorization boundary)
  -> KnowledgeSubject / Account (person, organization, agent, or asset)
       -> CaseEnvelope (shared identity, ownership, policy, and audit contract)
            -> AXIOM AssessmentCase
                 -> AssessmentRun
                      -> RuleSetExecution(s)
            -> AEGIS WorkflowCase
                 -> WorkflowRun
                      -> NodeAttempt
                           -> GateEvaluation(s)
```

The current session/run-centric implementation is not equivalent to this target.
`session_id` and `run_id` must not be used as substitutes for durable account and
case identity.

`Tenant/Workspace` is distinct from `KnowledgeSubject/Account`. A single-tenant
deployment may use one fixed tenant, but a person/company/robot remains the
subject rather than becoming the authorization boundary. `Account` remains the
product-facing term where useful; `KnowledgeSubject` avoids confusion with login
or billing accounts in shared contracts.

`CaseEnvelope` is a small cross-product contract, not a shared table containing
nullable AXIOM and AEGIS fields. An AXIOM `AssessmentCase` is a durable legal,
eligibility, entitlement, compliance, or assessment matter. An AEGIS
`WorkflowCase` is a durable mission, incident, action request, or governed
process. Both may contain multiple immutable executions, retries, replays, or
workflow attempts. A materially independent matter/objective creates a new case;
a retry, appeal, new-evidence determination, workflow regeneration, escalation,
or compensating attempt normally remains under the existing product case.

## 2. Sources of truth

| Information | Authoritative source | Derived/query form |
| --- | --- | --- |
| Rule behavior | Human-approved immutable rule-set revision in Platform PostgreSQL | Versioned rule dependency/RDF graph in Fuseki |
| Domain vocabulary/schema | Human-governed, versioned domain ontology | Published immutable ontology graph in Fuseki |
| Account and case identity/ownership | Platform or owning product PostgreSQL under one explicit ownership contract | Authorized graph catalogue and read model |
| AXIOM execution decision | Frozen deterministic Core execution record | Versioned case PROV-O/RDF projection |
| AEGIS workflow transition | AEGIS PostgreSQL event ledger linked to immutable Core decisions | Combined read-only workflow/case provenance projection |
| Fact/provenance record | Append-only PostgreSQL fact and decision records | Versioned case/account graph projection |
| Projection status | PostgreSQL outbox/audit/reconciliation records | Operational status exposed through read-only APIs |

Operational logs and traces diagnose the system. They are not a replacement for
the append-only decision and provenance record.

## 3. RDF graph topology

The phrase "modify the shared reusable domain ontology of a case" means append
instance knowledge to isolated case/account graphs. Automatic case execution
must never silently mutate the global domain ontology or an approved rule graph.

| Graph type | Contents | Mutation/version rule |
| --- | --- | --- |
| Domain ontology graph (TBox) | Human-governed classes, predicates, constraints, and mappings | Immutable published version; changes require governance and a new version |
| Rule graph | Symbolic dependency/RDF representation compiled from one approved rule-set revision | Immutable and content-addressed; never overwritten by case execution |
| Execution graph | Inputs, derived facts, conclusions, query/materialization evidence, and trace from one frozen execution | Immutable append-only projection |
| Case graph version | The case state produced by folding accepted case events through a defined point in time | New immutable version for every governed change or correction |
| Account longitudinal view | Authorized union/catalogue of current and historical case graph versions for one account | Logical view or versioned manifest; not one destructively updated named graph |
| Correlation graph | Explicit governed relationships between accounts/cases and their permitted traversal scope | Append-only relationship lifecycle with activation, expiry, revocation, and audit |

Graph URIs must include stable opaque identifiers and an immutable version or
content hash. A mutable "latest" alias may exist only as a convenience pointer;
it is not an evidence identifier. PostgreSQL must hold the graph catalogue,
hash, projection status, predecessor/supersession links, and owning account/case.

## 4. Rule and case versioning

1. A human authors a rule-set draft.
2. Platform validates it with the supported `inferra-core` facade.
3. Human/governance approval creates an immutable rule-set revision containing
   source, content hash, import-tree hash, compiler/parser versions, effective
   range, approver, and approval event.
4. The same transaction records an outbox intent for its versioned rule graph.
5. A worker compiles and publishes the immutable graph, verifies its hash/count,
   and records success or reconciliation state.
6. Starting a case execution freezes account, case, rule/workflow versions,
   feature profile, ontology snapshots, engine build, and input evidence.
7. Completing the execution atomically records its decision, all provenance
   products, and the case-projection outbox intent.
8. A worker publishes a new immutable execution/case graph version. Older graph
   versions remain queryable while retained.

A correction never edits a historical rule, decision, or graph version. It
creates a new event/version with `supersedes`, reason, verified actor, effective
time, and links to the corrected record. Replays create new executions and must
not rewrite precedent.

## 5. Provenance classification is not authority

Every provenance product, including `ASSERTED`, must be recorded for audit.
`FactSource` explains how a fact was produced; it must not by itself decide
whether that fact is trusted or may influence another decision.

Each fact record therefore needs independent fields or governed equivalents for:

- source class: `ASSERTED`, `INFERRED`, `SEMANTIC`, `LEARNED`, or
  `HYPOTHETICAL`;
- verification/evidence status and verified actor/source;
- decision eligibility and permitted products/operations;
- account, case, execution, and subject scope;
- effective/observed/expiry time;
- rule, workflow, ontology, query, model, and engine versions as applicable;
- derivation parents and evidence references;
- confidence where meaningful, without converting confidence into authority;
- supersession/revocation status and retention policy.

### Same-execution and future-case policy

| Source | Use inside the execution that produced it | Use by a later case | Audit treatment |
| --- | --- | --- | --- |
| `ASSERTED` | May be decision evidence only after source, subject, scope, and validity checks | May be offered as a candidate input, but must be revalidated against current scope and validity | Always retained while policy permits |
| `INFERRED` | A deterministic derivation from accepted inputs may drive downstream rules in the same frozen execution | Never copied as present truth; re-run the governing rule/version to produce a new inference | Retain conclusion, derivation, inputs, and versions |
| `SEMANTIC` | AXIOM: never changes deterministic rule truth. AEGIS: usable only through the explicit semantic gate policy in section 7 | Never copied as present truth; repeat the authorized query/reasoning against pinned current inputs | Retain result, query hash, graph snapshots, scope, and derivation |
| `LEARNED` | Advisory only unless a separate human-governed promotion creates a new approved rule or assertion | Not direct decision evidence | Retain model/version, evidence, confidence, and promotion outcome |
| `HYPOTHETICAL` | Simulation/counterfactual only; cannot authorize a live decision or actuation | Not direct decision evidence | Retain scenario, assumptions, and comparison result |

This policy allows longitudinal history to reduce rediscovery without allowing
stale conclusions to become unquestioned truth. A future case may discover and
inspect prior non-asserted products, but must re-derive or re-query them before
use. Promotion creates a new provenance event; it never changes the original
source classification.

## 6. AXIOM authority boundary

AXIOM concludes a rule set from facts accepted into the current deterministic
execution and deterministic facts derived from those inputs. Live Fuseki query
results, ontology materialization, semantic auto-answer, learned facts, and
hypothetical facts must not alter that decision.

This is a server-enforced product execution policy, not a UI convention:

- the AXIOM production API/BFF must select a non-overridable deterministic
  execution profile;
- callers cannot enable semantic auto-answer or ontology-derived fact injection;
- any semantic replay/shadow run has a distinct execution ID and is labelled
  non-authoritative relative to the original AXIOM conclusion;
- semantic differences may be displayed for review but cannot rewrite the
  original decision or its fact-source labels;
- AXIOM may query account/case graphs read-only after Platform authorizes the
  exact graph scope.

An LLM may translate natural language to SPARQL, but Platform must validate a
read-only query form, impose bounded complexity/results, choose the authorized
named graphs server-side, and record model/prompt/query hashes. The LLM never
chooses tenancy or graph authority.

## 7. AEGIS ontology and multi-rule gate policy

AEGIS may actively use ontology outcomes while evaluating a workflow node, but
raw SPARQL results never directly transition a workflow or release an action.

Required flow:

1. A node binds one or more immutable approved rule-set revisions.
2. AEGIS requests an authorized, bounded semantic query against pinned domain,
   account, case, rule, and execution graph versions.
3. The result is normalized into a typed `SEMANTIC` fact containing the query
   hash, graph snapshot identifiers/hashes, observed time, scope, provenance,
   and staleness policy.
4. A new frozen Core rule execution consumes the fact only when that rule
   binding explicitly permits semantic evidence for the relevant condition.
5. AEGIS combines the immutable rule outcomes using the node's versioned gate
   policy and records the complete aggregation trace.
6. The workflow transitions only after the Core decision and AEGIS gate event
   are durably committed and reconciled. Actuation remains separately gated and
   idempotent.

Semantic evidence may deny, block, or escalate by default. It may contribute to
an allow/advance result only when the approved rule binding declares it eligible
and its provenance, graph scope, freshness, and evidence requirements pass. It
does not satisfy a `MANDATORY` asserted-evidence condition by default.

Each multi-rule node must declare a composition policy such as `ALL`, `ANY`,
`N_OF_M`, an ordered policy, or an explicit Boolean expression. The accepted
authoring default is `ALL`, but activation requires explicit human confirmation
and persists the selected policy with the immutable workflow version. Missing
policy is invalid. The accepted effect-combining default is `DENY_OVERRIDES`:
across all composition modes, `DENY` dominates `ALLOW`, and `ERROR`, `STALE`, or
`INDETERMINATE` fails closed to block/escalation unless a separately approved
fallback policy says otherwise. `ANY` cannot bypass a mandatory safety rule.

Historical `SEMANTIC`, `INFERRED`, `LEARNED`, and `HYPOTHETICAL` products remain
visible to AEGIS for audit, similarity, and planning. A new live gate must
re-query/re-derive them; it cannot copy them into authoritative current state.

## 8. Account isolation and governed correlation

Account isolation is the default. A query or inference request cannot expand
scope merely because an RDF edge exists.

A traversable correlation requires a durable Relationship Declaration with at
least:

- source and target account IDs and owning tenant/workspace IDs;
- relationship type and permitted purpose/operations;
- evidence/legal basis and verified declaring/approving actors;
- effective and expiry times, status, version, and revocation path;
- directionality and permitted fact classes/properties;
- an `ASSERTED` relationship fact and explicit `MANDATORY` policy where the
  orchestrator requires it;
- immutable audit and query-access events.

Cross-tenant correlation requires authorization by both sides or another
explicit legal/governance basis. Revocation prevents new traversal without
rewriting historical decisions that legitimately used the relationship.

## 9. Retention and deletion

Graph and provenance retention is indefinite by default but configurable. The
configuration must be a versioned policy, not an unrecorded Fuseki TTL or manual
delete.

Minimum controls:

- policy scope, owner, approver, version, effective range, legal basis, and data
  classes;
- legal hold and regulatory minimums that override ordinary expiry;
- coordinated treatment of PostgreSQL authority, outbox/audit rows, Fuseki
  projections, caches, backups, exports, and replicas;
- preview/dry-run, authorization, idempotency, counts/hashes, and completion or
  failure events for purge operations;
- a tombstone containing non-sensitive identifiers and proof hashes where law
  and policy permit it;
- tested rebuild and restore behavior when only a derived Fuseki projection is
  removed;
- explicit handling for privacy erasure, pseudonymization, and cryptographic
  erasure where retention and erasure duties conflict.

No case graph is silently overwritten or expired. The exact policy scope and
tombstone behavior are governed as follows:

1. The deployment defines the default policy and permitted legal/operational
   bounds; the default is indefinite retention.
2. A tenant may select a versioned policy within those bounds.
3. An account, case, or data class may apply a more specific authorized policy.
4. Regulatory minimums and legal holds prevent premature deletion. Privacy-law
   maximums or erasure duties prevent excessive retention. A conflict blocks the
   purge and requires an auditable governance decision; the system does not
   silently choose either side.
5. An authorized purge retains a non-sensitive tombstone and proof hash when
   policy and law permit it. Where complete erasure is legally required, the
   erasure event retains only what that law permits.

## 10. Minimum persistent model

Before an account/case ontology is described as production-ready, the owning
services need durable equivalents of:

- `tenant_or_workspace` (unless a deliberate single-tenant deployment fixes one
  synthetic boundary);
- `knowledge_subject`/`account` with type, owner, status, and retention policy;
- a small `case_envelope` contract containing product, subject, ownership,
  retention, and immutable external references—not mixed product state;
- Platform-owned `assessment_case` and immutable `assessment_run` records for
  AXIOM;
- AEGIS-owned `workflow_case`, `workflow_run`, `node_attempt`, and
  `gate_evaluation` records;
- every run/evaluation freezes rule/workflow/profile/engine identifiers, outcome,
  and idempotency key;
- immutable `fact_record` and derivation/evidence links with source and authority
  dimensions kept separate;
- `graph_projection` catalogue with graph kind, URI, version/hash, ownership,
  predecessor/supersession, projection status, and retention policy;
- immutable rule-set/workflow bindings and gate aggregation policy;
- `relationship_declaration` with governed lifecycle;
- transactional outbox, reconciliation, access audit, and retention/purge event
  records.

Identifiers and authorization predicates must appear in database constraints,
repository methods, service commands, OpenAPI contracts, generated clients, and
negative cross-account tests. UI filters are not an isolation boundary.

## 11. Release sequencing

### Required for the first Core production release

- reserve and persist the minimum account, case, and execution ownership axis for
  every governed decision exposed by the release profile;
- make rule revisions and rule graphs immutable and content-addressed;
- persist all fact/provenance classes and projection intent transactionally;
- publish versioned rule/execution/case audit graphs through an outbox and prove
  reconciliation/rebuild against Fuseki;
- enforce account/case graph authorization and read-only inspection;
- default retention to indefinite and persist the selected versioned policy;
- disable decision-affecting semantic modes in the Core profile unless their
  product-specific authority contract and staging gates have passed.

### Required before AXIOM production use

- enforce the AXIOM deterministic authority profile server-side;
- support account/case ownership and immutable execution history;
- expose only authorized read-only audit/graph queries;
- clearly separate authoritative execution from semantic shadow analysis.

### Required before AEGIS production use

- persist account, case, workflow, multi-rule bindings, gate policy, facts, and
  transitions in the AEGIS-owned database;
- implement the typed semantic-evidence flow and denial/fail-closed aggregation;
- link every transition to frozen Core and graph identifiers;
- prohibit raw query-to-transition and historical-derived-fact promotion;
- pass cross-account, stale-graph, query-failure, conflict, and actuation tests.

### Post-release architecture work

- automated longitudinal candidate discovery and revalidation/re-derivation;
- governed Relationship Declaration workflows and cross-tenant correlation;
- natural-language SPARQL after LLM governance and tenant-scope tests;
- retention automation, legal holds, privacy erasure, and large-scale graph
  lifecycle operations;
- semantic diff, replay, impact analysis, and account-level longitudinal views.

## 12. Current implementation delta

As inspected on 2026-07-19/20, the three local working trees implement useful
pieces but not this end-to-end contract:

- Platform has rule/session/workflow-run persistence but no production Account
  or Case aggregate and no account/case graph ownership model.
- Rule RDF is generated, but the normal path replaces a stable graph rather than
  publishing an approved immutable rule-version graph atomically.
- Case-run RDF artifacts are session-oriented and generally manually synced;
  only the semantic-pilot path uses an immutable version graph.
- Platform inference profiles can materialize ontology suggestions into
  `ASSERTED` or `INFERRED` layers, so AXIOM's UI-only shadow-run separation is not
  yet a hard server boundary.
- AEGIS workflow nodes currently bind one rule, several runtime paths remain
  synthetic, and live ontology results are not integrated through a typed gate
  policy.
- Read-only SPARQL safeguards exist, but authorization cannot yet enforce the
  intended account/case boundary because that ownership model is absent.

These are implementation gaps, not evidence that the target behavior already
exists.

## 13. Resolved owner decisions

Accepted on 2026-07-20:

1. `Tenant/Workspace` is the authorization boundary;
   `KnowledgeSubject/Account` is the person, company, agent, or asset within it.
2. AXIOM uses `AssessmentCase`; AEGIS uses `WorkflowCase`. They share only the
   small `CaseEnvelope` contract and may each contain multiple immutable
   executions/attempts.
3. New AEGIS multi-rule nodes are authored with `ALL + DENY_OVERRIDES` and
   fail-closed `ERROR/STALE/INDETERMINATE` behavior. Activation requires explicit
   human confirmation of the persisted composition policy.
4. Retention defaults to indefinite and follows the accepted deployment ->
   tenant -> account/case/data-class policy hierarchy, legal/regulatory bounds,
   and conditional tombstone rule in section 9.
