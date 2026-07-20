# INFERRA Core Extraction P0.1 Baseline

Status: complete
Completed: 2026-07-17
Applies to: the current uncommitted `inferra-platform` working tree on
`feature/enhancement`
Controls: the behavior and dependency baseline for P0.2-P0.4 package extraction

This document is evidence for P0.1 of
[`INFERRA_Core_Package_and_Runtime_Architecture.md`](INFERRA_Core_Package_and_Runtime_Architecture.md).
It does not replace that architecture decision. The machine-readable inventory
is [`evaluation/core_boundary_inventory.json`](evaluation/core_boundary_inventory.json),
and the executable semantic vectors are
[`../tests/evaluation/core_behavior_golden_vectors.json`](../tests/evaluation/core_behavior_golden_vectors.json).

## 1. Outcome

P0.1 is complete. The current implementation has been frozen before any source
module is moved:

- all 243 production Python modules are classified;
- 70 modules are in the initial Core extraction set;
- 123 modules remain Platform runtime concerns;
- 43 modules are product or experimental extensions;
- 7 modules are legacy compatibility code;
- all 29 current imports from the initial Core set into non-Core code are
  recorded and guarded against silent growth;
- the current Structlog, SymPy, and RDFLib third-party import set is recorded
  and guarded against silent growth;
- six executable golden vectors cover parsing, diagnostics, inference, imports,
  iteration, and provenance;
- source, rule syntax, rule inputs, stable node IDs, diagnostics, import sources,
  and semantic provenance outputs are hashed; and
- the pre-extraction domain regression selection passes 769 tests.

P0.1 did not move or rewrite production code. Its purpose is to make the next
movement measurable and reversible.

## 2. Frozen candidate identity

| Field | Frozen value |
| --- | --- |
| Working-tree policy | Latest uncommitted local working tree is the intended future release candidate |
| Branch | `feature/enhancement` |
| HEAD | `49be15db253e2e6d5ced52bab2b770ba0707945e` |
| HEAD `src` Git tree | `627c8e068fb4835f9958396d6aa8af9c0fc57c07` |
| Aggregate working-tree Python-source SHA-256 | `9105df7d7e0875a98e8f1dfae8cbfe738dc26d814ec29e76d84a7a2c8fb2f404` |
| Source state at capture | No uncommitted changes below `src/`; documentation changes remained uncommitted |
| Current Platform distribution | `inferra-platform==2.0.0` |
| Current syntax reference | `INFERRA Rule Syntax Dictionary` version `0.3` |
| Syntax dictionary SHA-256 | `388919ff8f36ac198ab92d04e8279e2b19c948754e86eb649e557bf05cf2c9c7` |
| Existing behavioral selection | 769 passed, 39 warnings in 19.81 seconds |

The aggregate source hash is capture evidence, not a permanent prohibition on
source changes. P0.2 will necessarily change paths and content. The enduring
compatibility gates are the golden outputs and explicit boundary decisions.

## 3. Classification model

| Classification | Count | Meaning |
| --- | ---: | --- |
| `core_initial` | 70 | Move into `inferra_core`, or replace with an equivalent Core-owned module, during the first extraction |
| `platform_runtime` | 123 | Keep in Platform because the code owns transport, persistence, identity, configuration, sessions, jobs, or operations |
| `extension` | 43 | Keep outside Core because the code belongs to AEGIS, LLM, provider verification, SNOMED/MBS, demos, ontology products, or experimental reasoning |
| `platform_compatibility` | 7 | Keep temporarily as a Platform migration/legacy adapter; never expose it through the Core facade |

Classification describes ownership, not current directory naming. In
particular, two deterministic validators currently live in `src/services` but
belong in Core after their runtime concerns are split out. Conversely, the
current `src/domain/models`, `src/domain/exceptions.py`, inference sessions, and
session schema are Platform application/persistence types and must not become
the Core public contract merely because they are under `src/domain`.

AEGIS route and persistence adapters physically hosted in Platform are counted
as Platform runtime modules by this file inventory. Their product ownership
remains `extension` under the cross-project decision, and they remain excluded
from the Core API profile and Core package.

## 4. Initial Core module inventory

| Current subsystem | Count | Initial Core disposition |
| --- | ---: | --- |
| `src/domain/fact_values` | 3 | Move value and value-type semantics |
| `src/domain/graph` | 9 | Move graph types, construction, traversal, serialization, propagation, and the history-guided topology strategy; exclude matrix compatibility |
| `src/domain/imports` | 5 | Move deterministic import matching, origins, registry semantics, and resolution after deadline/thread behavior is removed |
| `src/domain/inference` | 8 | Move assessments, engine, question resolution/strategy, and graph-first topological behavior; exclude runtime sessions and extension orchestrators |
| `src/domain/iterate` | 2 | Move deterministic quantifier and iteration behavior |
| `src/domain/nodes` | 14 | Move rule node/value/metadata models; exclude the three matrix-era graph shims |
| `src/domain/rule_parser` | 10 | Move tokenizer-fed parsing and in-memory source reading; move filesystem ownership out |
| `src/domain/session/inference_context.py` | 1 | Split out a Core evaluation/trace context with explicit time and identifiers |
| `src/domain/state` | 4 | Move fact source, layered fact store, and an immutable evaluation profile; exclude the Platform Pydantic session schema |
| `src/domain/tokens` | 5 | Move lexical token behavior |
| `src/domain/trace` | 2 | Move neutral provenance construction; decide RDF serialization placement as a reviewed optional boundary |
| Selected `src/ports` contracts | 5 | Move dependency graph, fact store, history-record, iteration, and question-strategy ABC contracts |
| Deterministic validation modules | 2 | Split and move `declaration_validator.py` and deterministic parts of `rule_validation_service.py` |
| **Total** | **70** | Initial extraction inventory |

The eight selected inference files are `__init__.py`, `assessment.py`,
`assessment_state.py`, `assessments.py`, `inference_engine.py`,
`question_resolver.py`, `question_strategy.py`, and `topo_sort.py`. The current
package initializer is included because it must be replaced with a safe Core
initializer; its runtime session re-export is recorded as debt.

The selected ports are:

- `dependency_graph_port.py`;
- `fact_store_port.py`;
- `history_record_store_port.py`;
- `iteration_port.py`; and
- `question_strategy_port.py`.

The current persistence, session, LLM, provider, induction, abduction, and AEGIS
ports remain outside Core. New public request/result types must be Core-owned;
they must not reuse SQLAlchemy entities, HTTP schemas, or Platform CRUD models.

## 5. Explicit exclusions

### Platform runtime

Platform retains all inbound/outbound adapters, infrastructure, tasks, general
application services, configuration, `main.py`, persistence-oriented domain
models and exceptions, inference session storage/services, `SessionManager`,
and the Pydantic session schema.

The validation exception currently in `src/domain/exceptions.py` is typed to a
Platform validation service, and `ConcurrentModificationError` describes a
durable runtime concern. Core should define new transport-neutral diagnostic
and domain-error types instead of moving this module wholesale.

### Extensions

The initial package excludes:

- `src/domain/aegis`;
- `src/domain/demo`;
- `src/domain/llm`;
- `src/domain/provider_verification`;
- `src/domain/reasoning` in its current hybrid/ontology/abduction/induction
  form;
- `src/domain/snomed_mbs`;
- the corresponding extension ports and `src/tools`; and
- current `BackwardChainOrchestrator` and `SemanticQuestionStrategy` modules
  that couple deterministic inference to optional reasoning.

Backward chaining itself remains Core behavior through `InferenceEngine`. The
current higher-level orchestrator is excluded because it combines convergence,
session management, abduction, induction, and reasoning routing. It can be
decomposed later rather than dragging those extensions into Core.

### Compatibility

The seven compatibility modules are:

- `src/domain/graph/dependency_matrix.py`;
- `src/domain/graph/graph_to_matrix_adapter.py`;
- `src/domain/graph/matrix_to_hyper_adapter.py`;
- `src/domain/inference/legacy_orchestrator.py`;
- `src/domain/nodes/dependency.py`;
- `src/domain/nodes/dependency_matrix.py`; and
- `src/domain/nodes/dependency_type.py`.

They stay in Platform until stored payload and client migration permits their
removal. The Core wheel and facade must not expose them.

## 6. Current boundary debt

The AST inventory records 29 direct internal imports from `core_initial` files
to non-Core classifications.

| Category | Count | Current debt | Required resolution |
| --- | ---: | --- | --- |
| Platform logging | 20 | Candidate parser, graph, node, inference, and token modules import `src.infrastructure.logging_config` | Replace with a dependency-free Core policy or Core-owned neutral events before moving files |
| Matrix compatibility | 6 | Graph/inference/parser/node modules import matrix bridge modules | Put compatibility behind Platform adapters and remove it from Core initializers and normal paths |
| Ontology reasoning extension | 2 | `inference_engine.py` imports `ontology_reasoner` and `semantic_fact_enricher` | Accept supplied semantic facts/types through a narrow Core boundary; keep implementations outside Core |
| Runtime session export | 1 | `src/domain/inference/__init__.py` re-exports `InferenceSession` | Build a deliberate `inferra_core` facade without runtime session exports |
| **Total** | **29** |  |  |

The 20 logger-importing files and all exact import edges are retained in the
machine-readable manifest. The boundary test fails if an edge is added or
removed without an intentional manifest update. Removing debt is expected; the
explicit update makes the reduction reviewable.

No initial Core file currently imports FastAPI, SQLAlchemy, Redis, Celery,
OpenAI, Requests, Pydantic, dotenv, Uvicorn, or PostgreSQL drivers. An executable
guard preserves that fact during extraction.

The complete current third-party import set is also frozen:

| Dependency | Importing Core-candidate files | Disposition |
| --- | ---: | --- |
| Structlog | 10 | Remove or adopt only through a deliberate dependency-free/neutral logging decision; it must not become durable audit authority |
| SymPy | 1 | Review and pin for reproducibility, licensing, Python compatibility, and necessity |
| RDFLib | 1 | Decide whether serialization is a reviewed optional Core extra or a Platform adapter |

Despite its historical name, `MLTopologicalSortStrategy` does not import NumPy;
it currently uses standard-library `heapq`. NumPy is therefore not part of the
candidate Core dependency set.

## 7. Non-import extraction blockers

Static import direction is necessary but not sufficient. The following behavior
must be split or made explicit before affected code enters the package:

| ID | Blocker | Required treatment |
| --- | --- | --- |
| B01 | Direct Platform/structlog logging | Keep durable audit in Platform; use neutral bounded events or a reviewed library logging policy |
| B02 | Ontology types embedded in `InferenceEngine` | Replace implementation imports with supplied facts, values, or a narrow port |
| B03 | `FeatureFlags` reads `os.environ` | Create an immutable Core evaluation profile; parse deployment environment in Platform |
| B04 | Import resolver creates a `ThreadPoolExecutor` | Make resolution deterministic over a supplied loader; Platform owns deadlines and cancellation |
| B05 | Default clocks, timestamps, UUIDs, and process-global parse state | Inject values that affect results and keep convenient runtime defaults outside the authoritative Core call |
| B06 | Rule reader opens filesystem paths | Core accepts text/bytes; Platform owns paths and file access |
| B07 | SymPy expression dependency | Review and pin it for reproducibility, licensing, supported-Python compatibility, and necessity |
| B08 | RDFLib provenance serialization | Keep neutral provenance models in Core; decide whether RDF serialization is a reviewed optional Core extra or Platform adapter |
| B09 | Matrix types reachable through package exports and compatibility methods | Exclude them from the Core facade and normal dependency graph |
| B10 | Validation combines deterministic checks with cache, logging, and ontology review | Move immutable diagnostics and deterministic checks; retain TTL cache and review orchestration outside Core |

These are extraction tasks, not permission to alter semantics. Each split must
continue to pass the frozen vectors.

## 8. Behavioral golden vectors

| Vector | Frozen behavior |
| --- | --- |
| `parser-and-dependency-v1` | Input types, parsed node names, AND edge type `8`, stable node IDs, and source SHA-256 |
| `diagnostics-duplicate-declaration-v1` | Deterministic duplicate-declaration code, message, line, node, severity, waiver ID, and source hash |
| `inference-false-or-short-circuit-v1` | Question order, asserted/inferred fact sources, false OR convergence, failed-AND pruning, working memory, and source hash |
| `imports-transitive-diamond-v1` | DFS resolution order, local/imported origins, depths, de-duplication, and every import-source hash |
| `iteration-quantifiers-v1` | `ALL`, `NOT ALL`, `NONE`, `SOME`, `EXACTLY`, `AT LEAST`, `AT MOST`, and legacy numeric quantifier results and completion timing |
| `provenance-asserted-inferred-v1` | Equivalent Turtle and JSON-LD semantic graphs with 17 triples and digest `1e067e4833dbcb485343cd00327c32e014d421dfbed2cfff59fccdbd9e7fc83b` |

Golden output changes require one of two dispositions:

1. restore compatibility if the change was accidental; or
2. approve and document an intentional semantic change, version the affected
   syntax/result contract, add migration/replay guidance, and update the vector.

Timing, log text, memory addresses, and serialization ordering are deliberately
excluded. Semantic RDF triples are canonicalized before hashing.

## 9. Executable controls

Run the P0.1 controls with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/infrastructure/test_core_boundary_inventory.py `
  tests/evaluation/test_core_behavior_golden_vectors.py
```

The inventory tests enforce:

- complete classification of every production Python module;
- no silent change to the 29 known boundary imports;
- no Core import of framework/data-service dependencies;
- no silent change to the reviewed third-party import set;
- unique actionable blocker records; and
- syntax dictionary version/hash identity.

The broader pre-extraction selection is:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/domain/rule_parser `
  tests/domain/inference `
  tests/contracts/test_iteration_port.py `
  tests/domain/imports `
  tests/domain/trace `
  tests/domain/state/test_layered_fact_store.py
```

Captured result: 769 passed with 39 deprecation warnings. The warnings mainly
identify matrix/node-ID compatibility behavior that must remain in Platform
during migration.

## 10. P0.1 exit criteria

- [x] Define the Core capability and module inventory.
- [x] Classify every production Python module.
- [x] Identify direct imports from the initial Core set into runtime,
  compatibility, or extensions.
- [x] Record implicit environment, time, thread, filesystem, dependency, and
  concern-mixing blockers.
- [x] Capture parsing, validation diagnostic, inference, iteration, import, hash,
  and provenance vectors.
- [x] Freeze current Platform/source/syntax identities.
- [x] Prove the inventory and golden-vector tests pass on the pre-extraction
  implementation.

## 11. Handoff to P0.2

Progress update, 2026-07-17: recommended steps 1-5 and the first part of step 6
are complete. The package, facade, compatibility re-exports, private
graph/node/token/parser/validation layer, wheel/source builds, and clean
installed-wheel parser proof are recorded in
[`INFERRA_Core_Extraction_P0_2_Distribution.md`](INFERRA_Core_Extraction_P0_2_Distribution.md).
P0.2 remains in progress because the deeper dependency layers in step 6 have not
all moved.

Post-baseline security update, 2026-07-17: the Structlog/SymPy/RDFLib counts in
this file remain the deliberately frozen pre-extraction evidence and must not be
rewritten. Current Core 0.1.1 has removed SymPy and all other third-party runtime
dependencies, uses the bounded INFERRA expression interpreter, fails validation
closed, and raises typed cycle errors. The immediate next gate has also changed:
declare the public compile/validation facade and rewire the already-extracted
Platform slice before moving another dependency layer. Current evidence and
ordering are controlled by
[`INFERRA_Core_Extraction_P0_2_Distribution.md`](INFERRA_Core_Extraction_P0_2_Distribution.md).

The next task is to establish the internal distribution. Do not combine this
with API profiling, persistence redesign, or semantic changes.

Recommended P0.2 order:

1. Create `packages/inferra-core` with independent build metadata and the
   `inferra_core` namespace.
2. Add a deliberately small public facade and package-only test configuration.
3. Move the first leaf slice: fact/value types, fact source, dependency
   type/group, selected ABC ports, and immutable diagnostic value types.
4. Make Platform import that slice through temporary compatibility adapters.
5. Build and install the wheel in a clean environment; prove no repository-root
   `PYTHONPATH` leakage and no forbidden imports.
6. Continue by dependency layer through graph/nodes/tokens/parser, fact
   store/iteration/imports, and finally inference/provenance.
7. At every step run the six golden vectors and the applicable existing domain
   suite. Do not update a vector merely to make a move pass.

After the public compile/validation facade and installed-artifact Platform
integration gate passes, the next P0.2 dependency slice is fact
store/iteration/import resolution. It must split the semantic evaluation
profile from environment configuration, keep explicit clocks, and replace
import resolver thread/deadline/filesystem/registry policy with caller-supplied
sources and Platform adapters. Ontology and remaining runtime splits should be
made when their owning inference/provenance modules enter the package, not as
one large preliminary rewrite.
