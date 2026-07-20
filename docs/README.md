# INFERRA Documentation Index

Status: active index
Last updated: 2026-07-20

The root of `docs/` is now intentionally small. Files here are either active implementation/operations documents or stable references. Historical phase plans, future proposals, old enhancement memos, and one-off operations notes live in `archive/`.

## Active Implementation Docs
- `INFERRA_Cross_Project_Technical_Direction.md` - controlling product ownership, release profiles, security boundaries, database direction, ontology audit logging, and priority order across Platform, AXIOM, and AEGIS.
- `INFERRA_Core_Package_and_Runtime_Architecture.md` - accepted deep design for the internal `inferra-core` Python distribution, the authoritative Platform runtime, generated clients, embedded mode, versioning, extraction, and CI gates.
- `INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md` - controlling account/case hierarchy, RDF graph topology, provenance-versus-authority policy, AXIOM/AEGIS semantic boundaries, retention, correlation, and release sequencing.
- `INFERRA_Core_Extraction_P0_1_Baseline.md` - completed pre-extraction module inventory, boundary debt, source/syntax identity, golden semantic vectors, and executable P0.1 evidence.
- `INFERRA_Core_Extraction_P0_2_Distribution.md` - live P0.2 evidence: P0.2a leaf contracts, P0.2b private graph/node/token/parser/validation, and the Core 0.1.1 evaluator/validation/cycle security correction are complete; public-facade Platform integration is next, then state/import/inference/provenance layers.
- `IMPLEMENTATION_STATUS.md` - current implementation truth, phase status, evidence, architecture rules, and release blockers.
- `ROADMAP.md` - consolidated current roadmap replacing the old phase/future/enhancement backlog stack.
- `OPERATIONS.md` - Docker, local-prod, readiness, load, chaos, and troubleshooting runbook.
- `INFERRA_Production_Readiness_and_Tech_Stack.md` - production stack, readiness matrix, and release gates.
- `INFERRA_Production_Decision_Register.md` - external decisions required before production traffic.
- `INFERRA_Legacy_Retirement_Register.md` - compatibility paths and feature flags that must be retired or frozen.
- `INFERRA_vs_PALOS_PyRest_Comparison_Report.md` - what was learned from `PALOS-PyRest` and what was rejected.
- `../IMPLEMENTATION_GUIDE.md` - broad current development-profile API and
  capability guide; active architecture/release documents override its older
  phase-level maturity wording.
- `../EXPLORER_DEPLOYMENT.md` - development-only direct Fuseki explorer; not a
  production UI or authority boundary.

## Stable References
- `INFERRA_Rule_Syntax_Dictionary.md` - rule syntax reference.
- `inferra_prompt.md` - rule-engineering prompt reference.
- `SNOMED CT AU and MBS related/SNOMED_MBS_INTEGRATION_GUIDE.md` - current SNOMED-CT AU and MBS integration guidance.
- `reference/examples/README.md` - rule examples and domain corpora used for testing and demonstrations.
- `Business docs/` - commercial/product notes.

## Archive
- `archive/README.md` explains the archive structure and supersession policy.
- `archive/phase-plans/` contains the original Phase 1-5 plans.
- `archive/future-and-enhancements/` contains older future proposals and enhancement memos.
- `archive/architecture-blueprints/` contains older architecture blueprints and conversion notes.
- `archive/operations-notes/` contains standalone Redis/Fuseki notes superseded by `OPERATIONS.md`.
- `archive/status-audits/` contains dated implementation audits superseded by `IMPLEMENTATION_STATUS.md`.

The completed feature-flag alignment plan, earlier strategic/ontology visions,
superseded SNOMED planning and audit material, and the legacy root Fuseki note
were archived on 2026-07-16. Their remaining actionable work is represented in
`ROADMAP.md` or the active integration and operations guides.

## Guidance
When docs and code disagree, treat code and tests as the immediate truth, then update the active docs in the same change. Target architecture must be labelled as target work until its implementation gates pass. The runtime session schema is currently `CURRENT_SCHEMA_VERSION = 5`.
