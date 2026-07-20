# INFERRA Core Extraction P0.2 Distribution Progress

Status: in progress; P0.2a distribution/leaf slice, P0.2b
graph/node/token/parser/validation slice, and the 0.1.1 security correction are
complete; public facade/Platform integration is the immediate gate before
P0.2c onward
Updated: 2026-07-17
Applies to: the current uncommitted `inferra-platform` working tree on
`feature/enhancement`
Controls: implementation evidence for P0.2 of
[`INFERRA_Core_Package_and_Runtime_Architecture.md`](INFERRA_Core_Package_and_Runtime_Architecture.md)

## 1. Outcome

The internal distribution now exists and contains its second coherent
dependency layer. `packages/inferra-core` is independently buildable as
`inferra-core==0.1.1`, imports as `inferra_core`, has its own build metadata and
package-only tests, and has no third-party runtime dependencies. Version 0.1.0
established the distribution; 0.1.1 is a required security correction. The
root Platform distribution declares the exact Core version and resolves it
from the monorepo path for development through `tool.uv.sources`.

This closes P0.2a and P0.2b. The package now has executable private graph, node,
token, parser and deterministic validation implementations. Platform's
validation service hosts the Core validator and supplies the operational cache
clock. Version 0.1.1 also replaces general-purpose string expression parsing
with a bounded, purpose-built INFERRA AST/interpreter, rejects validation when
the declaration validator fails internally, and reports dependency cycles as
typed errors. Platform still retains its compatibility-heavy parser path;
the legacy dependency matrix and nested iterate inference remain Platform-only.
The next gate is to expose a narrow public compile/validation facade and rewire
the already-extracted Platform path through it. Fact-store/iteration, import
resolution, inference and provenance follow only after that vertical slice is
proved, so P0.2 as a whole remains open.

No public package publication has occurred. Version `0.1.1` is an internal
pre-release facade, not a stable public API.

## 2. Canonical first slice

The following objects are now defined by `inferra_core`; the old Platform paths
are exact-class compatibility re-exports rather than subclasses or duplicate
implementations.

| Core module | Canonical objects | Temporary Platform compatibility paths |
| --- | --- | --- |
| `inferra_core.values` | `FactValue`, `FactValueType`, `FactSource` | `src.domain.fact_values.*`, `src.domain.state.fact_source` |
| `inferra_core.graph` | `DependencyType`, `DependencyGroup` | `src.domain.graph.dependency_type`, `src.domain.graph.dependency_group` |
| `inferra_core.records` | `HistoryRecord` | `src.domain.nodes.record` |
| `inferra_core.ports` | `DependencyGraphPort`, `FactStorePort`, `HistoryRecordStorePort`, `IterationPort`, `QuestionStrategyPort` | the five corresponding `src.ports.*` modules |
| `inferra_core.diagnostics` | `ValidationEntry`, `ValidationError`, `ValidationWarning`, `OntologyReviewQueueItem`, `ValidationResult` | imports re-exported by `src.services.rule_validation_service` |

`HistoryRecord` moved with its port so `HistoryRecordStorePort` has no Platform
domain dependency. Its unused Structlog import was removed. The ontology review
queue item is only an immutable result value in Core: cache policy, logging,
human approval, ontology lookup, and review orchestration remain Platform or
extension responsibilities.

Compatibility tests also resolve the seven legacy pickle global names for the
moved value/result classes to the exact Core classes. This preserves reads of
existing trusted payloads; it does not weaken the separate P0 recommendation to
replace pickle session deserialization with a schema-safe format.

The package top-level facade exports only the version, the objects above, and
the five ports. Consumers must use `from inferra_core import ...`; submodule
layout is not yet a separately supported compatibility contract.

### 2.1 P0.2b private implementation layer

P0.2b deliberately does not expand the supported top-level facade. The
following runnable implementation areas now live below
`inferra_core._internal` and are exercised from the built distribution:

| Area | Extracted behavior | Boundary decision |
| --- | --- | --- |
| Tokens | token model, matcher dictionary and tokenizer | no logging framework or Platform imports |
| Nodes | base and concrete deterministic nodes, metadata, values, `NodeSet`, iterate syntax/progress | Core `NodeSet` rejects legacy matrix views; nested iterate inference stays in Platform until the iteration tranche |
| Graph | dependency model/builder, sparse graph, serialization, incremental propagation and history-aware ordering | graph depends only on Core values/ports; matrix adapters remain Platform compatibility code |
| Parser | reader, scanner, parser, syntax matchers and graph-level node-set merger | parser owns an explicit `NodeIdContext`; no thread-local collision registry or unsafe eager package initializer |
| Validation | declaration and rule validation | Core caching is disabled without an explicit clock; Platform's thin wrapper supplies `time.time` for its process-local cache |
| Expressions | bounded lexer, private AST, parser and interpreter for documented `IS CALC` syntax | rule source is data only; arbitrary calls, Python/SymPy execution, unsupported operators, excessive size/depth/work and invalid results are rejected; relational numeric coercion preserves integer/decimal precision |
| Import leaf | immutable `NodeOrigin` used by node-set merging | full source loading, registry and import resolution remain P0.2c |

Core has no third-party runtime dependency. FastAPI, Pydantic, SymPy,
Structlog, SQLAlchemy, Redis, Celery, RDFLib, HTTP/LLM clients, environment
flags, and product extensions are not Core dependencies.

The private namespace is not a promise that every copied class signature is
stable. Before another dependency layer moves, the next integration gate will
define a narrow compile/validation facade and rewire Platform through it. Until
then, Platform retains its parser and iterate compatibility entry points so
this extraction does not simultaneously change stored payload, matrix or
nested-engine behavior.

## 3. Packaging and runtime integration

- `packages/inferra-core/pyproject.toml` owns distribution metadata and declares
  no runtime dependencies. The root lock no longer contains SymPy or mpmath.
- Platform declares `inferra-core==0.1.1`; `uv.lock` records the local package
  source without turning the Platform wheel into a path-dependent artifact.
- `.github/workflows/ci.yml` has a separate `core-distribution` job. It runs
  package-only tests, builds and clean-installs the wheel, and retains the wheel
  and source distribution. Backend, import-contract, and OpenAPI jobs install
  Core before Platform.
- `Dockerfile` copies and installs the Core distribution before exporting and
  installing Platform runtime dependencies. The local package is excluded from
  the hashed third-party requirements export because it is installed as its own
  artifact.
- `scripts/verify_inferra_core_distribution.py` builds the wheel and source
  distribution, audits archive contents and metadata, creates a clean virtual
  environment outside the repository, clears `PYTHONPATH`, installs only the
  Core wheel, and executes the parser plus an adversarial expression rejection
  check with Python isolated mode.

The build verifier reports artifact SHA-256 values, but local transient hashes
are not release identities. Reproducible-build proof and persistence of the
selected artifact hash with governed executions remain P0.4 work.

## 4. Enforced boundary

Package tests permit only Python standard-library modules and the
`inferra_core` namespace. They also reject calls to general-purpose evaluation
entry points. A separate explicit denylist rejects framework/runtime imports.
A clean installed-wheel process also asserts
that no `src` module and no FastAPI, Pydantic, SQLAlchemy, Redis, Celery, HTTP,
OpenAI, RDFLib, Structlog, or Uvicorn module is loaded while the parser runs.

Core node identity has no thread-local or module-global collision registry.
Each parser owns a `NodeIdContext`, and standalone callers must supply a context
when collision resolution spans multiple IDs. Core validation makes no system
clock call: its LRU/TTL cache remains empty unless the host supplies a clock.
Core also removes the deprecated mutable Node static-ID counter.

The P0.1 inventory guard now treats `inferra_core` as the extracted internal
distribution rather than a third-party dependency. Its recorded direct
Structlog importer set decreased from the original ten files to seven:
`HistoryRecord`, declaration validation and rule validation no longer import
Structlog. The historical P0.1 module/classification counts remain the
pre-extraction baseline.

## 5. Verification evidence

Run the new package gates with:

```powershell
python -m pip install -e "packages/inferra-core[test]"
python -m pytest packages/inferra-core/tests -q
python scripts/verify_inferra_core_distribution.py
python -m pytest tests/infrastructure/test_inferra_core_compatibility.py `
  tests/evaluation/test_core_behavior_golden_vectors.py -q
```

Evidence captured during this change:

| Gate | Result |
| --- | --- |
| Package-only facade, dependency boundary, parser, graph, identity, iterate and validation behavior | 17 passed |
| Package plus Platform declaration/rule validation and all six frozen semantic vectors | 118 passed, 1 pre-existing RDFLib warning |
| Applicable Platform graph, node, token, parser and validation suites plus package tests | 957 passed, 83 expected compatibility/deprecation warnings |
| P0.1 inventory controls after the intentional Structlog-manifest update | 6 passed |
| Historical 0.1.0 isolated artifact verification | Wheel and source distribution built; declared dependency wheelhouse installed; parser executed from a clean external venv; zero forbidden modules; repository `PYTHONPATH` not used |
| Historical 0.1.0 dependency lock | `uv lock --check` passed with 101 packages including local `inferra-core==0.1.0` |
| Full Platform regression suite | 3,466 passed, 70 skipped, 146 warnings in 314.92 seconds after P0.2b and the validation host wrapper |
| 0.1.1 package-only suite | 33 passed; covers the public leaf facade, private parser/graph/validation layer, documented expression behavior, adversarial source rejection, limits, typed cycles, version metadata, and dependency/evaluator-call boundaries |
| 0.1.1 focused Platform compatibility/security suite | 221 passed, 12 warnings; covers expression compatibility, fail-closed declaration/rule validation, typed graph contracts, installed Core compatibility, and all six frozen semantic vectors |
| 0.1.1 isolated artifact verification | Wheel/source metadata and contents valid; no runtime requirements; parser executed and adversarial Python expression rejected in a clean external venv; zero forbidden modules including SymPy; repository `PYTHONPATH` not used |
| 0.1.1 local artifact hashes | Wheel `f3a9a47af7d5b8cd1b1d79c32d4bb1f6be867a25cecf312c7e9d062685ee141a`; source distribution `12befb0e32b515530fd2466d36c6bc079de5916184ac9c177629b1d39d670e87` (transient local evidence, not a governed release identity) |
| Current dependency lock | `uv lock --check` resolved 99 packages; local `inferra-core==0.1.1` present; SymPy and mpmath absent |
| Current full Platform regression suite | 3,471 passed, 70 skipped, 146 warnings in 309.00 seconds |
| Current Platform coverage gate | Pass: 20,932/21,579 statements, 97.0017% against the unchanged 97% threshold after adding coverage for all five temporary Platform expression-adapter branches |

The six P0.1 golden vector files were not changed. Parser output, diagnostic
serialization, inference state, import tree/hash, iteration result, and
provenance output therefore remain the accepted pre-extraction values.

## 6. P0.2 status and remaining order

- [x] Create the independent distribution and `inferra_core` namespace.
- [x] Define a deliberately small top-level facade and package-only tests.
- [x] Move the first leaf values, all five Core-owned ABC ports, immutable
  diagnostic values, and the port-required history value.
- [x] Preserve old Platform import paths through exact-object re-exports.
- [x] Build wheel and source artifacts and prove clean installed-wheel isolation.
- [x] Remove environment/global/runtime dependencies from the moved slices.
- [x] Move executable graph, node, token, parser, and deterministic validation
  layers into the private package implementation; keep the supported facade
  deliberately unchanged until the public-facade integration gate.
- [x] Replace string-to-SymPy expression execution with a bounded INFERRA
  parser/interpreter, fail declaration validation closed, type graph-cycle
  failure, remove all Core third-party runtime dependencies, and add
  adversarial source/artifact gates.
- [ ] Declare a narrow public compile/validation facade and rewire Platform's
  completed parser/validation/expression slice to the installed artifact.
- [ ] Move fact-store/iteration and import-resolution layers after splitting
  clocks, threads, filesystem and registry state.
- [ ] Move inference and provenance after separating ontology extensions,
  logging, and runtime sessions.

Complete Platform application-service rewiring, package-direction import-linter
contracts, and testing every Platform path against only the built artifact
remain separate later work. P0.4 still owns whole-engine equivalence,
determinism, reproducible artifacts, benchmarks, and release hashes.

## 7. Next action

Do not move another horizontal dependency layer yet. First declare the smallest
supported compile/validation facade, remove Platform's direct dependence on
`inferra_core._internal` for the completed slice, and prove Platform uses the
installed 0.1.1 artifact with parity and adversarial tests. Then continue P0.2
with fact store, iteration and import resolution: split the immutable semantic
evaluation profile from environment-backed `FeatureFlags`, move
`LayeredFactStore` with an explicit clock, move `IterationEngine` against Core
ports, and make import resolution synchronous over a supplied source loader.
Platform retains environment parsing, executor/deadline policy,
filesystem/registry adapters and legacy iterate orchestration.
