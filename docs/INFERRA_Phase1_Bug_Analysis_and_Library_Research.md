# INFERRA Phase 1: Bug Detection Gap Analysis and Python Library Research

**Document Status:** Final v1.0  
**Date:** 2026-04-30  
**Scope:** Why Phase 1 bugs escaped detection during implementation; evaluation of Python libraries as potential replacements for INFERRA's custom code.

---

## 1. Why Bugs Weren't Detected During Implementation

Four critical bugs and four important bugs were identified during the Phase 1 audit that were not caught by the existing test suite. This section explains *why* each class of bug escaped detection and what testing gaps need to be closed.

### 1.1 Root Cause: Lack of Integration Tests

The primary reason all eight bugs escaped detection is the **absence of integration tests that exercise the full code path end-to-end**. The existing tests are unit-level and test each component in isolation. They verify that `LayeredFactStore` correctly stores facts, that `InferenceEngine` can chain evaluations, and that `IterateLine` can process answers — but they never verify that these components work correctly *when composed together*.

| Test Gap | Bug That Escaped | Why Unit Tests Missed It |
|----------|-----------------|--------------------------|
| No cross-thread test | Critical #1: Module-level mutable global in `node_id_utils.py` | Tests run in a single thread; `threading.local()` behavior only manifests under concurrent parse sessions |
| No `InferenceEngine` -> `LayeredFactStore` integration test | Critical #2: `_initialize_from_node_set()` bypasses layered store | Engine tests mock the assessment state; store tests verify `set_fact()` in isolation |
| No override-lifecycle test | Critical #3: `invalidate_layer(ASSERTED)` clears ALL overrides | Each layer-invalidation test only uses one layer; no test invalidates ASSERTED while INFERRED overrides exist |
| No legacy iterate -> `AssessmentState` tagging test | Critical #4: Legacy iterate paths don't tag INFERRED | The `_handle_iterate_answer()` path IS tested, but `iterate_feed_answers()` and `iterate_feed_answers_with_json()` are only tested with mocked assessment states |
| No sparse-matrix performance test | Important #5: O(n^2) adapter `_rebuild()` | Tests use 4x4 matrices where O(n^2) is invisible; no test measures iteration count or timing |
| No time-dependent test with injected clock | Important #6: `time.time()` hardcoded | Tests use `time.sleep(0.01)` which is inherently flaky; no test verifies deterministic timestamp behavior |
| No concurrent sync/async test | Important #7: Mixed sync/async lock coverage | The async path (`feed_iterate_answer`) and sync path (`iterate_feed_answers`) are never tested in the same session |
| No structural typing test | Important #8: `FactStorePort` uses ABC | Protocol compliance is a structural check, but the test only verifies inheritance-based compliance |

### 1.2 Specific Bug-by-Bug Analysis

#### Critical #1: Module-Level Mutable Global (`node_id_utils.py:8`)

**Bug:** `_active_ids: Dict[str, str] = {}` was shared across all threads and sessions. Concurrent parse sessions would contaminate each other's collision trackers.

**Why it escaped:** All tests run in pytest's default single-threaded mode. The `test_node_id_utils.py` suite validates determinism within a single thread — it never creates concurrent sessions. The `reset_parse_context()` call at the start of each test masked the cross-session contamination because it cleared the global dict before each test case.

**Fix applied:** Replaced with `threading.local()`-backed `ParseContext` class. Each thread now maintains its own collision tracker.

**Test gap to close:** Add a multi-threaded integration test that parses the same rule set concurrently from two threads and verifies independent ID generation.

---

#### Critical #2: `_initialize_from_node_set()` Bypasses Layered Store (`inference_engine.py:75`)

**Bug:** The method directly mutated `self.__ast.get_working_memory()[key] = value` instead of calling `self.__ast.set_fact(key, value, source=FactSource.ASSERTED)`. This bypassed the layered store's provenance tracking, override detection, and timestamp recording.

**Why it escaped:** `InferenceEngine` tests use `set_node_set()` which calls `_initialize_from_node_set()`, but the test assertions only check `get_working_memory()` (the unified view). Since the direct dict mutation puts the value in the same dict that `get_working_memory()` reads from, the test passes. The bug only manifests when you check `get_fact_sources()` or `peek_in_layer()` — neither was asserted in the engine tests.

**Fix applied:** Changed to `self.__ast.set_fact(key, value, source=FactSource.ASSERTED)`.

**Test gap to close:** Add an integration test that initializes an engine from a node set and then verifies `get_fact_sources()` returns `{FactSource.ASSERTED}` for all initialized facts.

---

#### Critical #3: `invalidate_layer(ASSERTED)` Clears ALL Overrides (`layered_fact_store.py:75-76`)

**Bug:** When invalidating the ASSERTED layer, the original code cleared the entire `_overrides` set, removing override records for keys that still had ASSERTED-over-INFERRED relationships in other entries. Only overrides for keys *in the ASSERTED layer being cleared* should have been removed.

**Why it escaped:** The existing test `test_invalidating_inferred_clears_override_set` only tests the INFERRED invalidation path. No test exists for the ASSERTED invalidation path with active overrides. The `test_invalidate_layer_asserted` test in the contract suite only checks that the ASSERTED layer is cleared — it doesn't verify override state.

**Fix applied:** Changed ASSERTED invalidation to `self._overrides -= cleared` (only removes overrides for keys that were in the cleared ASSERTED layer). Added `_rebuild_overrides()` after INFERRED invalidation to restore remaining ASSERTED-over-INFERRED overrides.

**Test gap to close:** Add a test that sets up ASSERTED overrides on multiple keys, invalidates the ASSERTED layer, and verifies that only the cleared keys' overrides are removed (not all of them).

---

#### Critical #4: Legacy Iterate Paths Don't Tag INFERRED (`iterate_line.py:289-367`)

**Bug:** `iterate_feed_answers()` and `iterate_feed_answers_with_json()` called `parent_ast.set_fact(self._node_name, ...)` without specifying `source=FactSource.INFERRED`, causing iterate conclusions to default to `ASSERTED` provenance. This is incorrect because iterate conclusions are derived by the rule engine, not provided by the user.

**Why it escaped:** The `_handle_iterate_answer()` path in `InferenceEngine` WAS correctly tagging as INFERRED (this was the WS-3 fix). But the legacy direct-call paths (`iterate_feed_answers` and `iterate_feed_answers_with_json`) are called from outside the engine and were never updated. The test suite only exercises iterate via the engine's `_handle_iterate_answer()`, never through the direct legacy paths.

**Fix applied:** Added `source=FactSource.INFERRED` to both `parent_assessment_state.set_fact()` calls in `iterate_feed_answers_with_json()` and `iterate_feed_answers()`.

**Test gap to close:** Add integration tests that call `iterate_feed_answers()` and `iterate_feed_answers_with_json()` directly and verify `FactSource.INFERRED` tagging on the conclusion.

---

### 1.3 Summary: Testing Strategy Recommendations

| Priority | Test Type | Description |
|----------|-----------|-------------|
| **P0** | Integration | `InferenceEngine` -> `LayeredFactStore` full chain: initialize -> feed answer -> verify fact sources and timestamps |
| **P0** | Integration | `IterateLine` legacy paths: call `iterate_feed_answers()` -> verify INFERRED tagging |
| **P1** | Concurrency | Multi-threaded `generate_node_id()` isolation test |
| **P1** | Property-based | Override lifecycle: random set_fact/remove_fact/invalidate_layer sequences must never produce stale overrides |
| **P2** | Performance | Sparse matrix adapter with 500+ node matrix: verify _rebuild() iteration count is O(k) not O(n^2) |
| **P2** | Clock injection | `LayeredFactStore` with deterministic clock: verify `get_changed_since()` is exactly correct |

---

## 2. Python Library Research: Can Existing Libraries Replace INFERRA?

### 2.1 Evaluation Criteria

INFERRA's core requirements that any replacement library must satisfy:

1. **Backward chaining** (goal-directed reasoning) — INFERRA starts from a goal rule and works backward to find supporting facts
2. **Fact provenance** — Each fact must carry its source (ASSERTED / INFERRED / SEMANTIC) for traceability
3. **Dependency graph with typed edges** — AND, OR, MANDATORY dependency types; cycle detection; topological ordering
4. **Iterate/quantifier evaluation** — ALL, NONE, SOME, N quantifiers over list items
5. **Incremental evaluation** — Feed one answer at a time; re-evaluate only affected nodes
6. **Node history tracking** — Track evaluation history per node for sequence path optimization

### 2.2 Library Evaluation Matrix

| Library | Backward Chaining | Fact Provenance | Typed Dep. Graph | Iterate/Quantifier | Incremental Eval | Node History | Verdict |
|---------|:-:|:-:|:-:|:-:|:-:|:-:|---------|
| **Experta** (pyknow) | No (forward-only, Rete) | No | No | No | No | No | Incompatible |
| **durable-rules** | No (forward-only, Rete) | No | No | No | Partial | No | Incompatible |
| **PyKE** | Yes | No | No | No | No | No | Abandoned (2011, no Py3) |
| **pyDatalog** | Yes (backward) | No | No | No | Partial | No | Missing 3/6 criteria |
| **kanren** (miniKanren) | Yes (relational) | No | No | No | No | No | Missing 4/6 criteria |
| **networkx** | N/A (graph lib) | N/A | Partial (edge attrs) | N/A | N/A | Partial (node attrs) | Graph-only; no reasoning |
| **graphlib** (stdlib) | N/A | N/A | No | N/A | N/A | N/A | Topo-sort only; one function |
| **DataJoint** | No | Partial | No | No | No | No | Data pipeline, not reasoning |
| **Clausal** | Partial | No | No | No | No | No | Research prototype, unmaintained |

### 2.3 Detailed Library Analysis

#### 2.3.1 Experta (formerly pyknow) — Forward-Chaining Only

Experta implements the Rete algorithm, which is a **forward-chaining** pattern-matching engine. INFERRA is fundamentally **backward-chaining** — it starts from a goal and works backward to determine which facts need to be established. These are diametrically opposed reasoning strategies.

- **Cannot replace INFERRA.** Forward-chaining cannot be retrofitted for backward-chaining without rewriting the entire evaluation model.
- **No fact provenance tracking.** Experta's fact base has no concept of ASSERTED vs. INFERRED.
- **No dependency graph.** Rules fire when their conditions match; there is no explicit dependency structure.
- **No iterate/quantifier support.** There is no built-in concept of iterating over a list with quantified evaluation.

#### 2.3.2 PyKE — Backward-Chaining but Abandoned

PyKE is the only Python library that supports both forward and backward chaining. It uses a knowledge engine that compiles rules into Python code for efficient execution.

- **Abandoned since ~2011.** No Python 3 support. Last commit was over a decade ago. Cannot be used in a modern codebase.
- **No fact provenance.** PyKE has no concept of layered fact sources.
- **No typed dependency graph.** Rules are compiled into flat functions; there is no graph structure to traverse.
- **No iterate/quantifier.** Would need to be built on top of PyKE's rule system.

#### 2.3.3 pyDatalog / kanren — Backward Reasoning but Insufficient

pyDatalog implements Datalog-style logic programming with backward reasoning. kanren (miniKanren) is a relational programming language that supports goal-directed search.

Both libraries support backward reasoning, but:
- **No fact provenance.** Facts are simply true or false; there is no tracking of where they came from.
- **No dependency graph.** Relations are defined declaratively; there is no explicit graph structure.
- **No iterate/quantifier.** List iteration with quantified evaluation would need to be implemented from scratch.
- **No node history.** Neither library tracks the evaluation history of individual nodes, which is needed for sequence path optimization.

These libraries solve the logic resolution problem but not the infrastructure problems that INFERRA's custom code addresses.

#### 2.3.4 networkx — Graph Library, Not a Reasoning Engine

networkx is a comprehensive graph library that could replace parts of `HyperAdjacencyGraph`:
- **Graph traversal:** `nx.bfs_tree()` could replace `back_propagate()`
- **Topological sort:** `nx.topological_sort()` could replace Kahn's algorithm
- **Cycle detection:** `nx.is_directed_acyclic_graph()` could replace `CyclicGraphError`

However:
- **No built-in hyper-edge support.** INFERRA's `DependencyGroup` (one parent -> set of children with shared dep type) would require a custom adapter.
- **No back-propagation with override tracking.** Would need to be built on top of networkx's traversal primitives.
- **No node history for sequence path optimization.** networkx allows arbitrary node attributes, but does not provide built-in history tracking. You would need to implement this yourself using `G.nodes[node]["history"]` — which is essentially what INFERRA already does with `IterateContext.progress`.
- **Adds a heavy dependency** (~2MB) for functionality that INFERRA already implements in ~237 lines of well-tested code.
- **Performance characteristics differ.** networkx is pure Python and not optimized for the small, sparse graphs that INFERRA uses. INFERRA's custom adjacency list is more cache-friendly for its use case.

**Verdict:** Not worth the migration cost. INFERRA's custom `HyperAdjacencyGraph` already provides the exact API needed, with cycle guards, caching, and typed dependency groups. networkx would require significant adapter code and wouldn't improve performance or maintainability.

#### 2.3.5 graphlib.TopologicalSorter (Python stdlib)

`graphlib.TopologicalSorter` (Python 3.9+) provides a built-in topological sort that could replace the BFS variant of INFERRA's Kahn's algorithm. However:
- Only provides `static_order()` — no incremental evaluation, no caching, no cycle-specific error messages
- Does not support DFS topological sort (which `topo_sort.py` also implements)
- INFERRA's Kahn's algorithm includes caching (invalidated on mutation) and returns a `CyclicGraphError` — `graphlib` raises `CycleError` instead

**Verdict:** Could be used for the BFS variant as a minor simplification, but the benefit is negligible. Phase 2 plan already identifies `topo_sort.py` migration to `graphlib.TopologicalSorter` as a potential task.

### 2.4 Conclusions and Recommendations

**No single Python library can replace INFERRA's custom code.** The combination of backward chaining, fact provenance, typed dependency graphs, iterate/quantifier evaluation, and incremental evaluation is unique to INFERRA. Libraries that support some of these features (pyDatalog, kanren) miss the majority, and the most complete backward-chaining library (PyKE) is abandoned.

**Specific recommendations:**

| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| `HyperAdjacencyGraph` | **Keep custom** | 237 lines, well-tested, purpose-built for INFERRA's hyper-edge model. networkx adds a heavy dependency with no functional improvement. |
| `DependencyMatrix` | **Keep custom, migrate consumers to HyperAdjacencyGraph** | Legacy format; `MatrixToHyperGraphAdapter` already provides the migration path. `sparse_items()` avoids O(n^2) iteration. |
| `topo_sort.py` | **Consider `graphlib.TopologicalSorter` for BFS variant in Phase 2** | Minor simplification; only replaces ~30 lines. Not worth the risk in Phase 1. |
| `IterateContext` | **Keep custom** | No library provides iterate/quantifier evaluation with progress tracking. |
| `LayeredFactStore` | **Keep custom** | No library provides fact provenance with layered override tracking. |
| `InferenceEngine` | **Keep custom** | No active Python library supports INFERRA's backward-chaining model with all required features. |

**Why node history for sequence path optimization is not available in existing libraries:**

Node history tracking — recording which nodes were evaluated, in what order, with what results — is a domain-specific optimization that no general-purpose reasoning or graph library provides. INFERRA's `IterateContext.progress` dict is a lightweight implementation that serves this purpose for iterate nodes. For general node evaluation history, the `get_changed_since(timestamp)` method on `LayeredFactStore` provides a timestamp-based change log. Extending this to a full evaluation history (node -> [timestamp, result, source]) would be a Phase 2 enhancement, but it would remain custom code regardless of which graph library is used.

---

## 3. Appendix: Libraries Evaluated

| Library | Version Evaluated | License | Last Updated | Py3 Support |
|---------|------------------|---------|--------------|-------------|
| Experta | 1.9.0 | MIT | 2024 | Yes |
| durable-rules | 2.0.28 | Apache-2.0 | 2022 | Yes |
| PyKE | 0.5 | MIT | 2011 | No (Py2 only) |
| pyDatalog | 1.0.3 | MIT | 2023 | Yes |
| kanren | 0.3.0 | BSD-3 | 2023 | Yes |
| networkx | 3.3 | BSD-3 | 2024 | Yes |
| graphlib | stdlib | PSF | N/A | Yes (3.9+) |
| DataJoint | 0.14.2 | MIT | 2024 | Yes |
| Clausal | 0.1 | MIT | 2019 | Partial |
