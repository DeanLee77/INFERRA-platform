# INFERRA Roadmap

Status: active roadmap
Last updated: 2026-07-20

This roadmap consolidates the old phase/future/enhancement documents. Archived plans remain in `docs/archive/`, but this file is the current backlog framing.

## Release Candidate Track

Local milestone completed 2026-07-16: the clean backend release-candidate gate
passed 3,438 tests with 73 skips at 97.016% coverage, captured matching API and
worker flag snapshots, and passed acceptance, benchmark, infrastructure, and
import-boundary checks. A deterministic, committed `openapi.json`, CI drift
gate, retained schema artifact, and aggregate candidate-evidence job are now
implemented locally. GitHub enforcement, frontend, and live-environment gates
remain below.

Core extraction P0.1 completed on 2026-07-17: 243 production modules are
classified, 29 current boundary crossings are frozen, and six parser,
diagnostic, inference, import, iteration, hash, and provenance vectors pass.
P0.2a and P0.2b also completed: the internal `inferra-core==0.1.1`
distribution, leaf contracts, and private executable graph/node/token/parser
and deterministic-validation layers build and pass installed-wheel parser
isolation. The P0 security correction removed string-to-SymPy rule evaluation,
made declaration validation fail closed, made graph cycles typed, removed all
Core third-party runtime dependencies, and added adversarial installed-wheel
proof. The immediate next item is a narrow public compile/validation facade and
Platform rewiring for the completed slice. Fact-store/iteration/import work may
resume only after that integration gate passes.

| Priority | Work | Outcome |
| --- | --- | --- |
| P0 | Complete the internal `inferra-core` extraction; P0.1, P0.2a-P0.2b and the expression/validation/cycle security correction are complete, while the public facade, Platform rewiring, fact-store/iteration/imports, inference/provenance and whole-engine proof remain | Platform and Python embedders reuse one pure, tested engine without moving production authority into every consumer |
| P0 | Keep the completed golden vectors active and test Platform against the installed Core wheel | Package movement cannot silently change parsing, diagnostics, inference, imports, iteration, hashes, or provenance |
| P0 | Implement the package-backed `core` API profile and forbidden-route/OpenAPI gates | The first network contract exposes only approved deterministic and audit capabilities |
| P0 | Add migration baselines, immutable rule revisions, transaction/outbox, and durable ontology audit events | Governed execution has reproducible state and publication intent |
| P0 | Add the minimum tenant/account/case/execution ownership axis, fact source-versus-authority fields, and graph catalogue | Decisions and RDF projections have enforceable ownership, version, and retention identity rather than only session/run names |
| P0 | Publish immutable rule and execution/case audit graphs through the outbox; prove read-only account/case authorization, reconciliation, rebuild, and indefinite-default versioned retention | Fuseki is an early, tested production component without becoming the transaction source of truth |
| P0 | Enforce product semantic profiles server-side | AXIOM cannot be altered by ontology auto-answer/materialization; AEGIS semantic authority cannot be enabled through an arbitrary caller-selected flag |
| P0 | Push the candidate and require the seven named release checks in branch protection | Core distribution, OpenAPI, evidence, and other local gate designs become enforced repository policy |
| P0 | Move production secrets to the selected platform secret manager | No real production secrets live in files, `.env`, or CI logs |
| P0 | Repeat k6 production gate and chaos suite in staging | Local evidence becomes environment evidence |
| P0 | Decide first-release auth posture | API key/JWT-only release or OIDC/RBAC scope is explicit |
| P1 | Tune Prometheus alert thresholds under staging load | Alerts become useful rather than decorative |
| P1 | Complete the release evidence bundle artifact | Local flags, coverage, benchmark, and import evidence pass; add OpenAPI, frontend, load, chaos, and legacy-retirement output |
| P1 | Stabilize, license, document, sign, and publish `inferra-core` after internal compatibility is proven | Public embedders receive a deliberate supported package rather than an unstable pre-release facade |

## Engineering Hardening
| Priority | Work | Outcome |
| --- | --- | --- |
| P0 | Extend the current stdlib-only package guard through every remaining Core layer and add package-direction import-linter contracts | The reusable package remains infrastructure- and product-independent |
| P0 | Keep graph-first guardrails active | `DependencyMatrix` cannot creep back into runtime paths |
| P1 | Complete external Change 5 release evidence | Local Change 5 gates pass; frontend builds and live smoke/load/chaos remain |
| P1 | Add full Redis-secret contract coverage for every Redis client path | Production Redis auth stays reliable as code evolves |
| P0 | Prove the non-decision-affecting rule/decision audit path through PostgreSQL outbox, worker, versioned Fuseki graph, read-only query, reconciliation, and rebuild in live local-prod and staging | The Core release's critical ontology audit path moves from partial code to operational evidence |
| P1 conditional | Prove ontology post-reasoning/materialization in live local-prod and staging before enabling a product profile that permits it | Decision-affecting semantic behavior remains disabled until its stricter authority and failure gates pass |
| P1 | Convert untrusted persisted session state away from pickle-like payloads | Session persistence has a safer long-term security posture |
| P1 | Finish induction promotion workflow proof | Learned rule candidates can be reviewed, promoted, audited, and rolled back |
| P2 | Add backup/restore runbook for Postgres and Fuseki volumes | Operators can recover state deliberately |
| P2 | Add generated architecture/dependency report to CI | Boundary and dependency drift becomes reviewable |

## Product and UX
| Priority | Work | Outcome |
| --- | --- | --- |
| P0 conditional | Generate profile-specific TypeScript clients for AXIOM and AEGIS | Both Svelte products consume the authoritative Platform contract without hand-maintained schema drift |
| P0 conditional | Harden each Express BFF with human authentication, CSRF, exact route/method allowlists, and secret isolation | Production browsers never receive Platform credentials or broad proxy authority |
| P0 for AXIOM | Bind every governed run to account/case identity and a non-overridable deterministic execution profile | Semantic shadow analysis cannot mutate or replace the authoritative AXIOM decision |
| P0 for AEGIS | Persist one-or-more rule bindings per workflow node, explicit composition, and typed ontology evidence with denial/fail-closed precedence | Ontology can actively inform AEGIS gates without raw query results directly advancing a workflow |
| P1 | Freeze remaining AXIOM authoring API shapes after the `/api/v1/rules` contract lands in its generated client | Frontend work can move without backend churn |
| P1 | Keep AXIOM as the general Svelte authoring/execution/audit UI and AEGIS as the specialist Svelte governance UI | The existing first-party repositories replace obsolete React/prototype recommendations |
| P2 | Add API/UI confidence override surface | Hybrid reasoning decisions become inspectable and controllable |
| P2 | Add operator-facing release dashboard | Readiness, queues, inference rates, and failures are visible in one place |

## Optional AI and GraphRAG Track
| Priority | Work | Outcome |
| --- | --- | --- |
| P1 | Define LLM provider/model/prompt/eval/budget policy | LLM-backed paths can be enabled safely |
| P1 | Keep deterministic fallback mandatory for LLM paths | External provider failure cannot break deduction |
| P2 | Start GraphRAG as an evaluation harness, not production answer authority | Retrieval quality is measured before it affects decisions |
| P2 | Choose vector store only after corpus/evaluation set exists | Avoids premature infrastructure commitment |

## Post-Release Language and Governance Track
| Priority | Work | Outcome |
| --- | --- | --- |
| P2 | Evaluate `IS A KIND OF` and related class declarations through the syntax RFC process | Useful subclass semantics are added without weakening parser compatibility |
| P2 | Add semantic rule-version diffing and impact analysis | Legislative and policy changes become reviewable before deployment |
| P2 | Prototype ontology-assisted authoring as advisory tooling only | Semantic suggestions improve authoring without making ontology an ungoverned decision authority |
| P1 | Implement longitudinal account discovery with revalidation/re-derivation rather than direct reuse of historical conclusions | Prior cases reduce rediscovery without contaminating current truth |
| P1/P2 | Add governed Relationship Declaration workflows and scoped cross-account traversal | Correlated accounts can share permitted evidence without implicit privacy leakage |
| P1/P2 | Automate configurable retention, legal holds, coordinated purge/tombstone handling, and graph lifecycle proof | Indefinite default retention remains operable and legally governable |
| P3 | Evaluate cross-jurisdiction imports and explicit conflict/precedence rules | Multi-jurisdiction policy composition has deterministic governance semantics |
| P3 | Evaluate a governed rule marketplace only after signing, provenance, licensing, and promotion controls exist | Reusable rule packages cannot bypass release governance |

## Deferred or Explicitly Not Now
- Public `inferra-core` publication before internal API/semantic stability: build the internal artifact now, publish only after licensing, documentation, SBOM/provenance, signing, and pre-release gates.
- Library-only official deployment: embedded Python use is supported separately, but the multi-user authority remains the Platform service.
- Temporal or another durable workflow engine: useful later for enterprise promotion workflows, not needed before first production candidate.
- Neo4j/property graph migration: not aligned with the current RDF/Fuseki audit trail.
- Full OIDC/RBAC: a product/security decision, not an implementation default.
- Live LLM launch: blocked until provider/model/evaluation/budget/fallback policy is approved.
- Removing `DependencyMatrix`: blocked until legacy read/migration and iterate compatibility gates are formally closed.
- Removing legacy `/service/rule/*` endpoints: blocked until Rule Studio and external clients have moved to `/api/v1/rules`.

## Decision Rule
When a future document disagrees with this roadmap, the accepted cross-project
and Core package/runtime architecture documents control unless code/tests and the
production decision register have been updated in the same change.
