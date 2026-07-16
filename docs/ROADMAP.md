# INFERRA Roadmap

Status: active roadmap
Last updated: 2026-07-16

This roadmap consolidates the old phase/future/enhancement documents. Archived plans remain in `docs/archive/`, but this file is the current backlog framing.

## Release Candidate Track

Local milestone completed 2026-07-16: the clean backend release-candidate gate
passed 3,438 tests with 73 skips at 97.016% coverage, captured matching API and
worker flag snapshots, and passed acceptance, benchmark, infrastructure, and
import-boundary checks. A deterministic, committed `openapi.json`, CI drift
gate, retained schema artifact, and aggregate candidate-evidence job are now
implemented locally. GitHub enforcement, frontend, and live-environment gates
remain below.

| Priority | Work | Outcome |
| --- | --- | --- |
| P0 | Push the candidate and require the six named release checks in branch protection | The local OpenAPI/evidence design becomes enforced repository policy |
| P0 | Move production secrets to the selected platform secret manager | No real production secrets live in files, `.env`, or CI logs |
| P0 | Repeat k6 production gate and chaos suite in staging | Local evidence becomes environment evidence |
| P0 | Decide first-release auth posture | API key/JWT-only release or OIDC/RBAC scope is explicit |
| P1 | Tune Prometheus alert thresholds under staging load | Alerts become useful rather than decorative |
| P1 | Complete the release evidence bundle artifact | Local flags, coverage, benchmark, and import evidence pass; add OpenAPI, frontend, load, chaos, and legacy-retirement output |

## Engineering Hardening
| Priority | Work | Outcome |
| --- | --- | --- |
| P0 | Keep graph-first guardrails active | `DependencyMatrix` cannot creep back into runtime paths |
| P1 | Complete external Change 5 release evidence | Local Change 5 gates pass; frontend builds and live smoke/load/chaos remain |
| P1 | Add full Redis-secret contract coverage for every Redis client path | Production Redis auth stays reliable as code evolves |
| P1 | Prove ontology post-reasoning in live local-prod Compose | Phase 3 semantic loop moves from local implementation to runtime evidence |
| P1 | Convert untrusted persisted session state away from pickle-like payloads | Session persistence has a safer long-term security posture |
| P1 | Finish induction promotion workflow proof | Learned rule candidates can be reviewed, promoted, audited, and rolled back |
| P2 | Add backup/restore runbook for Postgres and Fuseki volumes | Operators can recover state deliberately |
| P2 | Add generated architecture/dependency report to CI | Boundary and dependency drift becomes reviewable |

## Product and UX
| Priority | Work | Outcome |
| --- | --- | --- |
| P1 | Freeze remaining Rule Studio API shapes after the `/api/v1/rules` contract lands in frontend | Frontend work can move without backend churn |
| P1 | Convert prototype frontends to typed production React/Vite apps | Graph editing and AI harness workflows become maintainable |
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
| P3 | Evaluate cross-jurisdiction imports and explicit conflict/precedence rules | Multi-jurisdiction policy composition has deterministic governance semantics |
| P3 | Evaluate a governed rule marketplace only after signing, provenance, licensing, and promotion controls exist | Reusable rule packages cannot bypass release governance |

## Deferred or Explicitly Not Now
- Temporal or another durable workflow engine: useful later for enterprise promotion workflows, not needed before first production candidate.
- Neo4j/property graph migration: not aligned with the current RDF/Fuseki audit trail.
- Full OIDC/RBAC: a product/security decision, not an implementation default.
- Live LLM launch: blocked until provider/model/evaluation/budget/fallback policy is approved.
- Removing `DependencyMatrix`: blocked until legacy read/migration and iterate compatibility gates are formally closed.
- Removing legacy `/service/rule/*` endpoints: blocked until Rule Studio and external clients have moved to `/api/v1/rules`.

## Decision Rule
When a future document disagrees with this roadmap, this roadmap wins unless code/tests and the production decision register have been updated in the same change.
