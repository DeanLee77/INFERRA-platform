# INFERRA Documentation Index

Status: active index
Last updated: 2026-07-16

The root of `docs/` is now intentionally small. Files here are either active implementation/operations documents or stable references. Historical phase plans, future proposals, old enhancement memos, and one-off operations notes live in `archive/`.

## Active Implementation Docs
- `IMPLEMENTATION_STATUS.md` - current implementation truth, phase status, evidence, architecture rules, and release blockers.
- `ROADMAP.md` - consolidated current roadmap replacing the old phase/future/enhancement backlog stack.
- `OPERATIONS.md` - Docker, local-prod, readiness, load, chaos, and troubleshooting runbook.
- `INFERRA_Production_Readiness_and_Tech_Stack.md` - production stack, readiness matrix, and release gates.
- `INFERRA_Production_Decision_Register.md` - external decisions required before production traffic.
- `INFERRA_Legacy_Retirement_Register.md` - compatibility paths and feature flags that must be retired or frozen.
- `INFERRA_vs_PALOS_PyRest_Comparison_Report.md` - what was learned from `PALOS-PyRest` and what was rejected.

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
When docs and code disagree, treat code and tests as the immediate truth, then update the active docs in the same change. The runtime session schema is currently `CURRENT_SCHEMA_VERSION = 5`.
