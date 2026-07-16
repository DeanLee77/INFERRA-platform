# INFERRA Documentation Archive

Status: historical archive
Last updated: 2026-07-16

This archive keeps the original phase plans, future proposals, recommendation memos, and one-off operations notes for audit/history. These files are not the current implementation backlog.

Current implementation truth lives in:

- `../IMPLEMENTATION_STATUS.md`
- `../ROADMAP.md`
- `../OPERATIONS.md`
- `../INFERRA_Production_Readiness_and_Tech_Stack.md`
- `../INFERRA_Production_Decision_Register.md`
- `../INFERRA_Legacy_Retirement_Register.md`

## Contents
| Directory | Purpose |
| --- | --- |
| `phase-plans/` | Original Phase 1-5 plans, Phase 1 research, the completed feature-flag alignment plan, and the superseded SNOMED/MBS integration plan. |
| `future-and-enhancements/` | Older future plans and suggested enhancement memos, including GraphRAG, induction/abduction extensions, IterateLine recommendations, and the superseded strategic and ontology vision documents. |
| `architecture-blueprints/` | Historical architecture blueprints, naming note, and FastAPI conversion plan. |
| `operations-notes/` | Standalone Redis/Fuseki notes superseded by `../OPERATIONS.md`, including the legacy root Fuseki note. |
| `status-audits/` | Dated implementation alignment and SNOMED documentation audits superseded by `../IMPLEMENTATION_STATUS.md` or the current SNOMED/MBS integration guide. |

## Policy
If an archived document contains a useful idea, promote it into `../ROADMAP.md` or a new tracked issue. Do not treat unchecked boxes in archived files as active work without reconciling them against code, tests, and the active production registers.
