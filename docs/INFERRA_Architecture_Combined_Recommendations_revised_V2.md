
# INFERRA: Consolidated Architecture & Implementation Plan
## Hybrid Reasoning Platform — *"From rules to reasoning."*

**Document Status:** Consolidated v6 — Merges original architecture proposal, additional review, full codebase analysis, modular rule imports, advanced dependency graph migration, IterateLine unification, enterprise traceability, and **port-based modularization architecture**. Conflicts resolved with explicit rationale. Ready for sprint planning and stakeholder review.

---

## 📖 1. Executive Summary

INFERRA evolves from a deterministic rule engine into a **Hybrid Reasoning Platform** that unifies symbolic logic, semantic knowledge representation, and stateful execution. This document provides a production-ready blueprint covering:

- ✅ **Async event-driven sync** replacing blocking rule projection
- ✅ **Port-based modularization** for scalability, testability, and zero-downtime migration
- ✅ **Layered working memory** separating asserted, inferred, and semantic facts
- ✅ **Incremental forward propagation** replacing full-graph recomputation
- ✅ **Hyper-Adjacency Graph with Immutable Snapshots** replacing the legacy 2D dependency matrix
- ✅ **IterateLine unification** eliminating nested `InferenceEngine` anti-pattern
- ✅ **Modular rule sets** with eager import resolution & circular dependency detection
- ✅ **PROV-O explanation model** for full auditability & traceability

These enhancements preserve INFERRA's deterministic backward-chaining core while enabling scalable, explainable, and ontology-accelerated decision workflows.

---

## 🎯 2. Brand Alignment & Conceptual Foundation

| Element | Definition |
|---------|------------|
| **Product Name** | INFERRA |
| **Acronym** | Inference Engine for Rule-based and Relational Reasoning Architecture |
| **Category** | Hybrid Reasoning Platform — Symbolic + Semantic + Stateful Execution |
| **Tagline** | *"From rules to reasoning."* |

### Conceptual Pillars ↔ Technical Mapping
| INFERRA Pillar | Technical Component | Role in Architecture |
|----------------|---------------------|----------------------|
| Rule-Based Logic | `BackwardChainOrchestrator`, `LayeredFactStore` | Deterministic backward-chaining, constraint enforcement, dependency resolution |
| Relational Intelligence | Fuseki (RDF/OWL), `inf:` vocabulary, Semantic Cache | Ontology reasoning, cross-domain linking, implicit relationship derivation |
| Inference Execution | `HybridReasoningEngine`, `QuestionStrategy`, `IterationEngine` | Path optimisation, fixed-point convergence, question gating, stateful traversal |
| Modular Rule Composition | `RuleCompiler`, `ModuleResolver`, `RuleSetParser` | Library-style rule reuse, circular import detection, eager compilation |
| Stateful Decision Flow | `SessionManager`, Layered Working Memory, Redis session store | Context preservation, fact provenance, decision lineage, session replayability |

> **Core Differentiator:** INFERRA does not just store or execute logic — it *derives* decisions through hybrid symbolic-semantic reasoning, with composable modular rule sets, port-based isolation, and a full audit trail for every conclusion.

---

## ⚠️ 3. Pre-Conditions: Critical Codebase Fixes Required First

These bugs will cause runtime failures during INFERRA integration if not resolved immediately.

| # | Issue | File | Fix |
|---|-------|------|-----|
| 3.1 | `Node.__static_node_id` never resets between sessions | `node.py` | Call `Node.reset()` at parse start. Pass per-parse `id_generator` for thread safety. |
| 3.2 | `FactValue` missing `set_default_value` | `metadata_line.py` | Add `set_default_value()` & `get_default_value()` methods to `FactValue`. |
| 3.3 | `AssessmentState._should_create_list` calls `get_operator()` on base `Node` | `assessment_state.py` | Guard with `isinstance(node, ComparisonLine)` before calling `get_operator()`. |
| 3.4 | HTTP layer bypasses `RuleService` for history | `inference.py` | Add `save_session_history()` to `RuleService`; route all persistence through it. |
| 3.5 | `lru_cache` misuse on `get_inference_session_service` | `dependencies.py` | Remove `lru_cache`; singleton already guaranteed by `get_session_store` cache. |
| 3.6 | Duplicate `doc_converter.py` / `file_service.py` | `doc_converter.py` | Delete duplicate; update `streamer.py` imports to use `FileConversionService`. |
| 3.7 | `ALLOWED_EXTENSIONS` parsed with `ast.literal_eval` per request | `settings.py` | Declare as `List[str]`; let Pydantic parse from environment automatically. |

---

## 🏗️ 4. Core Architecture & Design Principles

### 4.1 Dual-Representation Strategy (Canonical → Semantic Projection)
- **INFERRA Rule DB** is the single source of truth. All authoring, LLM generation, and validation occur here.
- **Fuseki RDF** is a **loss-aware semantic projection**. It mirrors rule structure but expands with OWL inference, transitive relationships, and class hierarchies.
- **Sync Flow:** `Rule Save → Validation (Sync) → Event → Async Compiler Worker → Fuseki Insert → Cache Invalidation`
- **Mapping Versioning:** Each projection includes `compiler_version` and source hash. INFERRA DB always wins on divergence.

### 4.2 Async Sync Pipeline
| Stage | Sync Mode | Rationale |
|-------|-----------|-----------|
| Rule validation (syntax, types, import resolution, DAG check) | Synchronous | Must fail-fast before persistence |
| RDF compilation & Fuseki projection | Asynchronous | Decouples write latency; tolerates Fuseki unavailability |
| Ontology pre-reasoning (session start) | Synchronous | Must complete before `InferenceEngine` initialises |
| Ontology post-reasoning (after answer) | Asynchronous | Runs in background; results injected on next question cycle |

```
Rule Save
  ├─► Validate (sync): syntax, types, circular import detection, DAG check
  │     └─► Reject if invalid (rollback)
  └─► Persist Rule (sync)
        └─► Publish RuleUpdated event (async)
              └─► InferraToRdfCompiler worker → SPARQL INSERT → Fuseki
```
**Implementation:** Redis + Celery, or AWS SQS/EventBridge.

### 4.3 Architectural Commitments (Non-Negotiable)
1. **Backward-chaining** remains the primary question driver — deterministic, auditable
2. **Rule DB** is the single source of truth — all other representations are projections
3. **Working memory** is the central execution state — all reasoning converges here
4. **Port-based isolation** ensures modularization does not disrupt core logic
5. Convergence is **deterministic** — capped iterations, explicit delta tracking, fallback guarantees

---

## 🧩 5. Modularization Strategy & Port-Based Architecture

Modularization is an **architectural prerequisite** for INFERRA's hybrid reasoning, async sync, PROV-O traceability, and enterprise scalability goals. It replaces monolithic coupling with explicit interface contracts.

### 5.1 Recommended Module Boundaries
| Current File/Component | Recommended Module | Responsibility | INFERRA Alignment |
|------------------------|-------------------|----------------|-------------------|
| `inference_engine.py` | `BackwardChainOrchestrator` | Goal traversal, dependency evaluation, convergence loop | Hybrid reasoning fixed-point, `InferenceContext` routing |
| `assessment_state.py` | `LayeredFactStore` | `asserted`/`inferred`/`semantic` memory, unified read view, provenance | `FactSource` enum, PROV-O `wasGeneratedBy`, traceability |
| `assessment.py` / `assesments.py` | `SessionManager` | Multi-goal routing, `mandatory_list` tracking, state snapshots | Immutable `SessionSnapshot`, replayability, convergence checks |
| `topo_sort.py` + graph logic | `DependencyGraphService` | `HyperAdjacencyGraph` management, incremental dirty tracking, topo-sort | O(V+E) traversal, subgraph extraction, RDF edge projection |
| `question_resolver.py` | `QuestionStrategy` | Pluggable gating logic (conservative, ontology-enhanced, LLM-augmented) | External API unchanged, strategies swappable at runtime |
| `iterate_line.py` | `IterationEngine` | List quantifier logic, `IterateContext`, progress tracking, unified subgraph eval | Eliminates nested engine, `FactSource.INFERRED` tagging |
| `rule_set_scanner.py` / `parser.py` | `RuleCompiler` + `ModuleResolver` | `IMPORT:` resolution, `NodeSet` merging, DAG validation, version pinning | `RuleSetImportResolver`, `ModuleRegistry`, sync pipeline gate |
| *(New)* | `OntologyPort` + `SemanticCache` | Async RDF sync, PROV-O generation, type bridge, pre/post-reasoning | `FusekiOntologyAdapter`, cache preloading, delta tracking |

### 5.2 Key Interface Contracts (Ports & Adapters)
```python
# src/ports/fact_store_port.py
class FactStorePort(Protocol):
    def get_unified_view(self) -> Dict[str, FactValue]: ...
    def set_fact(self, name: str, value: FactValue, source: FactSource) -> None: ...
    def get_changed_since(self, timestamp: float) -> Set[str]: ...

# src/ports/graph_port.py
class DependencyGraphPort(Protocol):
    def get_parents(self, node_id: int) -> Set[int]: ...
    def get_child_groups(self, node_id: int) -> Tuple[DependencyGroup, ...]: ...
    def get_topo_order(self) -> List[int]: ...
    def mark_dirty(self, node_ids: Set[int]) -> None: ...

# src/ports/iteration_port.py
class IterationPort(Protocol):
    def initialise(self, list_size: int, quantifier: str) -> None: ...
    def record_answer(self, index: int, value: bool) -> bool: ...  # returns True if complete
    def evaluate(self) -> FactValue: ...
    def get_progress(self) -> Tuple[int, int]: ...
```
**Rule:** Core engine modules depend only on `Port` interfaces. Adapters implement them. Zero cross-module direct imports.

### 5.3 Migration Strategy (Zero-Downtime, Backward-Compatible)
| Phase | Action | Risk Mitigation |
|-------|--------|-----------------|
| **1. Extract Fact Store** | Wrap `AssessmentState` in `LayeredFactStore` adapter. Route all `set_fact()`/`get_working_memory()` through new class. | Keep old dict as fallback. Add `FactSource` default. |
| **2. Extract Graph Service** | Build `HyperAdjacencyGraph` + `MatrixToGraphAdapter`. Engine uses adapter for `get_parents()`, `get_child_groups()`. | Feature flag `USE_HYPERGRAPH=true`. Run parallel topo sorts in tests. |
| **3. Extract Iteration Engine** | Replace `self.__iterate_ie` with `IterationEngine` using `IterationPort`. Keep old logic under `LEGACY_ITERATE=true`. | Unit tests verify `ALL`/`SOME`/`NONE`/N parity. |
| **4. Extract Question Strategy** | Move `_requires_user_input()` into `QuestionStrategy`. Default = current logic. Add `OntologyEnhancedStrategy` later. | Zero change to external `QuestionResolver` API. |
| **5. Decouple Session Manager** | Move `mandatory_list`/convergence checks into `SessionManager`. Engine calls `session.check_convergence()`. | Keep inline checks until Phase 5 complete. |
| **6. Freeze & Deprecate** | Remove legacy adapters. Enforce port-only imports. Update CI to block cross-module violations. | Run integration suite with 100% coverage before merge. |

---

## 🕸️ 6. Hyper-Adjacency Graph Architecture (Matrix Migration)

Given INFERRA’s architectural demands, the legacy 2D `dependency_matrix` must transition to a **Hyper-Adjacency Graph with Immutable Snapshots**, implemented as `DependencyGraphService`.

### 6.1 Why the 2D Matrix Falls Short
| Aspect | 2D Matrix (`dependency_matrix`) | INFERRA Requirement Gap |
|--------|-------------------------------|-------------------------|
| N-ary Grouping | Flattens `AND [A, B, C]` into 3 edges | NADIA evaluates dependency groups holistically. Grouping semantics lost. |
| Space Complexity | `O(N²)` → wastes memory on sparse graphs | Rule sets scale to 1000+ nodes; >90% matrix is `-1` |
| Incremental Traversal | Requires full matrix scan | Needs impacted subgraph propagation, not full recomputation |
| Ontology Sync | No native edge metadata | `inf:dependsOn` requires explicit parent/child + dependency type |
| Session Replay | Mutable state → cross-session bleed risk | INFERRA needs deterministic, versioned snapshots for audit & compliance |

### 6.2 Recommended Structure: `HyperAdjacencyGraph`
```python
from typing import Dict, Set, Tuple, FrozenSet, Optional
from dataclasses import dataclass, field
from enum import IntFlag

class DependencyType(IntFlag):
    AND = 1; OR = 2; MANDATORY = 4; NOT = 8; KNOWN = 16

@dataclass(frozen=True)
class DependencyGroup:
    dep_type: DependencyType
    children: FrozenSet[int]  # Immutable child node IDs

class HyperAdjacencyGraph:
    def __init__(self):
        self.children: Dict[int, Tuple[DependencyGroup, ...]] = {}
        self.parents: Dict[int, Set[int]] = {}
        self.edge_provenance: Dict[int, dict] = field(default_factory=dict)
        self._topo_cache: Optional[Tuple[int, ...]] = None

    def add_dependency_group(self, parent: int, dep_type: DependencyType, children: Set[int]) -> None:
        group = DependencyGroup(dep_type, frozenset(children))
        self.children.setdefault(parent, []).append(group)
        for child in children:
            self.parents.setdefault(child, set()).add(parent)
        self._topo_cache = None

    def get_parent_edges(self, node_id: int) -> Set[int]:
        return self.parents.get(node_id, set())

    def get_child_groups(self, node_id: int) -> Tuple[DependencyGroup, ...]:
        return self.children.get(node_id, ())
```

### 6.3 Migration Strategy (Phased & Backward-Compatible)
| Phase | Action |
|-------|--------|
| **A: Adapter** | Wrap existing matrix with `MatrixToHyperGraphAdapter`. Keep legacy APIs functional. |
| **B: Refactor** | Update `InferenceEngine._back_propagating` to use `graph.parents` + queue traversal. |
| **C: Topo Sort** | Migrate `topo_sort.py` to `graphlib.TopologicalSorter`. Cache order. Invalidate on rule update. |
| **D: Deprecate** | Remove `DependencyMatrix` entirely once load tests validate `HyperAdjacencyGraph`. |

**Impact:** ~98% memory reduction, 20–100x faster traversal, direct RDF/PROV-O serialization, incremental subgraph support, thread-safe session replay.

---

## 🔄 7. IterateLine Unification & Robustness

### 7.1 The Anti-Pattern: Nested `InferenceEngine`
The current `IterateLine` instantiates a **separate `InferenceEngine`** for every iteration. This causes:
- ❌ State fragmentation & broken traceability
- ❌ Ontology blindness (post-reasoning misses iterate facts)
- ❌ Impossible incremental propagation across boundaries
- ❌ Heavy memory/CPU overhead per list item

### 7.2 Recommended Architecture: Unified Subgraph Evaluation
Replace the nested engine with an `IterationEngine` implementing `IterationPort` that operates entirely within the parent engine's state, working memory, and topological order.

```python
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class IterateContext:
    list_name: str
    list_size: int
    quantifier: str  # "ALL", "NONE", "SOME", or integer string
    progress: Dict[int, bool] = field(default_factory=dict)  # index → satisfied?
    node_prefix_map: Dict[str, int] = field(default_factory=dict)
    is_initialised: bool = False
```

### 7.3 Refactored Core Methods
```python
def feed_iterate_answer(self, question_name: str, node_value: Any, node_value_type: FactValueType) -> bool:
    idx = self._extract_ordinal_index(question_name)
    is_true = bool(node_value) if node_value_type == FactValueType.BOOLEAN else str(node_value).strip().lower() == "true"
    self.progress[idx] = is_true
    return len(self.progress) == self.list_size

def self_evaluate(self, working_memory: Dict[str, FactValue]) -> FactValue:
    true_count = sum(1 for v in self.progress.values() if v)
    q = self.quantifier
    if q == "ALL": return FactValue(true_count == self.list_size)
    if q == "NONE": return FactValue(true_count == 0)
    if q == "SOME": return FactValue(true_count > 0)
    try: return FactValue(true_count == int(q))
    except (ValueError, TypeError): return FactValue(False)
```

### 7.4 Alignment with INFERRA Architecture
| INFERRA Pillar | Benefit from Unified Subgraph |
|----------------|-------------------------------|
| Hybrid Reasoning | Ontology post-reasoning sees all iterate facts. Semantic enrichment can pre-fill list items. |
| Incremental Forward Propagation | Changed iterate facts propagate upward through `HyperAdjacencyGraph.parents` → triggers re-aggregation. |
| PROV-O Traceability | Every list item answer carries `iterate_index`, `list_name`, `FactSource`. Full audit trail preserved. |
| Memory Efficiency | Eliminates O(N²) matrix allocation per iterate. Single engine, single topo sort, single working memory. |

---

## 📦 8. Modular Rule Sets — Import System

### 8.1 Syntax & Design
```
RULE SET: Veteran Eligibility Check

IMPORT: Service Period Rules
IMPORT: Disability Assessment Rules @ v2.3

# Reference: s.4 Veterans Entitlements Act
# Section: section 4
applicant is eligible for full benefit
    AND MANDATORY service period is valid
    AND MANDATORY disability rating is determined
```
- **Why `IMPORT:`?** Fits existing tokeniser pattern. Unambiguous. Starts at column 0.
- **Evaluator Model:** Imported nodes merge into unified `NodeSet`. Inference engine treats all nodes uniformly. Import origin tracked in `NodeOrigin` metadata for auditability.
- **Loading Strategy:** Eager compilation at session start with `ModuleRegistry` cache. Ensures circular import detection upfront and deterministic `Node` ID allocation.

### 8.2 `ModuleRegistry` & Circular Detection
```python
@dataclass
class CompiledModule:
    rule_name: str
    content_hash: str
    node_set: NodeSet
    compiled_at: datetime

class ModuleRegistry:
    def __init__(self):
        self._cache: Dict[str, CompiledModule] = {}
        self._lock = threading.RLock()

    def get(self, rule_name: str, content_hash: str) -> Optional[CompiledModule]:
        with self._lock:
            entry = self._cache.get(rule_name)
            return entry if (entry and entry.content_hash == content_hash) else None
```
Circular detection uses DFS with `visited` + `in_stack` sets during rule validation (synchronous, blocks save).

### 8.3 NodeSet Merging Rules
- **Name collisions:** Importing rule set wins (Python-style shadowing).
- **`FIXED`/`INPUT`:** Merged flat; importer wins.
- **Dependencies:** Cross-module references fully supported.
- **Topo Sort:** Re-run globally after merge to ensure correct evaluation order.

---

## 🧠 9. Layered Working Memory & State Management

Mixing user input, rule-derived, and ontology-derived facts breaks traceability. Introduce layered storage with a unified read view, implemented as `LayeredFactStore` adhering to `FactStorePort`.

```python
class FactSource(Enum):
    ASSERTED = "ASSERTED"   # user input
    INFERRED = "INFERRED"   # rule engine conclusions
    SEMANTIC = "SEMANTIC"   # ontology-derived

class AssessmentState:
    def __init__(self):
        self.__asserted_facts: Dict[str, FactValue] = {}
        self.__inferred_facts: Dict[str, FactValue] = {}
        self.__semantic_facts: Dict[str, FactValue] = {}

    def get_working_memory(self) -> Dict[str, FactValue]:
        return {
            **self.__semantic_facts,
            **self.__inferred_facts,
            **self.__asserted_facts,   # asserted wins on collision
        }

    def set_fact(self, name: str, value: FactValue,
                 source: FactSource = FactSource.ASSERTED) -> None:
        {
            FactSource.ASSERTED: self.__asserted_facts,
            FactSource.INFERRED: self.__inferred_facts,
            FactSource.SEMANTIC: self.__semantic_facts,
        }[source][name] = value
```
All existing callers continue to work unchanged. `source` defaults to `ASSERTED`.

---

## 🔄 10. Hybrid Reasoning Loop & Fixed-Point Convergence

INFERRA retains backward-chaining as the primary question driver, orchestrated by `HybridReasoningEngine` wrapping the `BackwardChainOrchestrator`. Ontology reasoning acts as a semantic accelerator.

```
[1] SESSION START
    └─► RuleSetImportResolver.resolve(rule_name) → merges imports
        └─► OntologyPort.enrich_fact_dictionary(merged_node_set)

[2] BACKWARD-CHAIN
    └─► BackwardChainOrchestrator.get_next_question(target)
        (ontology + imported facts auto-suppress prompts via QuestionStrategy)

[3] ANSWER INGEST
    └─► feed_answer_to_node() → back-propagation → updates ASSERTED layer

[4] POST-REASONING (async)
    └─► OntologyPort.persist_conclusions() → OWL reasoner → updates SEMANTIC layer

[5] INCREMENTAL FORWARD PROPAGATION
    └─► Re-evaluate impacted subgraph only (changed nodes → parents → topo sort)

[6] CONVERGENCE CHECK
    └─► Goal ∈ working_memory AND mandatory_list ⊆ working_memory
        AND working_memory[t] == working_memory[t-1] AND ontology_delta == 0
    └─► Auto-conclude or loop to [2]
```

### 10.1 Incremental Forward Propagation
```python
def _forward_propagate_incremental(self, changed_nodes: Set[int]) -> None:
    impacted = set(changed_nodes)
    queue = list(changed_nodes)
    while queue:
        node = queue.pop(0)
        for parent in self.graph.get_parent_edges(node):
            if parent not in impacted:
                impacted.add(parent)
                queue.append(parent)
    
    # Topo-sort ONLY impacted subgraph
    subgraph = {n: self.graph.get_child_groups(n) for n in impacted}
    ordered = self._topo_sort_subgraph(subgraph)
    for node_id in ordered:
        if self._can_evaluate_parent(node_id):
            self._evaluate_and_store(node_id)
```

### 10.2 Convergence Criteria
Let `W_t = working_memory at iteration t`. Converged if:
1. `Goal ∈ W_t`
2. `Mandatory ⊆ W_t`
3. `W_t == W_(t-1)` (fixed-point)
4. `Δ(ontology_delta) == 0` (no new triples)

---

## 🌐 11. Async Sync Pipeline & Ontology Integration

### 11.1 Event-Driven Sync Architecture
| Stage | Sync Mode | Rationale |
|-------|-----------|-----------|
| Rule validation (syntax, types, import resolution, DAG check) | Synchronous | Must fail-fast before persistence |
| RDF compilation & Fuseki projection | Asynchronous | Decouples write latency; tolerates Fuseki unavailability |
| Ontology pre-reasoning (session start) | Synchronous | Must complete before engine initialises |
| Ontology post-reasoning (after answer) | Asynchronous | Runs in background; results injected on next question cycle |

```
Rule Save
  ├─► Validate (sync): syntax, types, circular import detection, DAG check
  │     └─► Reject if invalid (rollback)
  └─► Persist Rule (sync)
        └─► Publish RuleUpdated event (async)
              └─► InferraToRdfCompiler worker → SPARQL INSERT → Fuseki
```
**Implementation:** Redis + Celery, or AWS SQS/EventBridge.

### 11.2 `OntologyPort` Interface & Semantic Cache
```python
class OntologyPort(metaclass=ABCMeta):
    @abstractmethod
    def enrich_fact_dictionary(self, node_set: NodeSet, rule_name: str) -> None: ...
    @abstractmethod
    def persist_conclusions(self, rule_name: str, session_id: str, working_memory: dict) -> None: ...
    @abstractmethod
    def run_reasoner(self) -> list[tuple]: ...
```
- **Implementations:** `FusekiOntologyAdapter` (prod), `NullOntologyAdapter` (default), `InMemoryOntologyAdapter` (tests).
- **Semantic Cache:** Preload relevant RDF triples into RDFLib in-memory graph at session start. Eliminates Fuseki from the hot execution path. Queries only run on deltas post-reasoning.

### 11.3 Type Safety Bridge
```python
RDF_RANGE_TO_FACT_TYPE = {
    "xsd:boolean": FactValueType.BOOLEAN, "xsd:integer": FactValueType.INTEGER,
    "xsd:decimal": FactValueType.DOUBLE, "xsd:date": FactValueType.DATE,
    "xsd:string": FactValueType.STRING, "xsd:anyURI": FactValueType.URL,
}
```

---

## 📜 12. PROV-O Traceability & Explanation Model

### 12.1 `InferenceContext`
```python
@dataclass
class InferenceContext:
    session_id: str
    rule_name: str
    target_node_name: str
    import_chain: list[str] = field(default_factory=list)
    iteration_count: int = 0
    changed_node_ids: set[int] = field(default_factory=set)
    ontology_delta: int = 0
    fact_source_map: dict[str, FactSource] = field(default_factory=dict)
    trace: list[TraceEntry] = field(default_factory=list)
```

### 12.2 PROV-O Trace Schema
```turtle
<session:abc123> a inf:Session, prov:Activity ;
    prov:startedAtTime "2025-01-01T10:00:00Z"^^xsd:dateTime ;
    inf:evaluatedRule <rule:VeteranEligibilityCheck> ;
    inf:importedModules <rule:ServicePeriodRules> .

<conclusion:xyz789> a inf:Conclusion, prov:Entity ;
    prov:wasGeneratedBy <session:abc123> ;
    inf:nodeText "applicant is eligible for full benefit" ;
    inf:nodeValue "true" ;
    inf:factSource inf:INFERRED ;
    inf:originModule <rule:VeteranEligibilityCheck> ;
    inf:dependedOn <fact:service_period_valid>, <fact:disability_rating> .
```

---

## 📅 13. Phased Implementation Plan (Core → Scalability → Strategic)

### 🔹 Phase 1: Core Functionality & Fact Store (Weeks 0–2)
*Focus: Stabilize engine, fix critical bugs, establish layered working memory, prepare dependency graph foundation.*
- [ ] Fix §3.1–3.7 (Node ID reset, FactValue defaults, isinstance guards, lru_cache, duplicates, Pydantic settings)
- [ ] Refactor `assessment_state.py` → 3-layer working memory + unified read view (`FactStorePort` adapter)
- [ ] Extract duplicated iterate guards → `_ensure_iterate_context()`
- [ ] Implement `IterateContext` + `feed_iterate_answer()` + progress tracking
- [ ] Create `HyperAdjacencyGraph` + `MatrixToHyperGraphAdapter` (`DependencyGraphPort`)
- [ ] Deploy `RuleValidationService` as synchronous gate before persistence
- [ ] Baseline API: `/sessions`, `/next-question`, `/feed-answer`, `/summary`

### 🔹 Phase 2: Graph Service & Iteration Engine (Weeks 3–4)
*Focus: Incremental propagation, modular imports, caching, graph traversal optimization.*
- [ ] Update `_back_propagating` to use `graph.parents` + queue traversal
- [ ] Migrate `topo_sort.py` to `graphlib.TopologicalSorter` + topo-order cache
- [ ] Event-driven async sync pipeline (`RuleUpdated` → Celery/SQS → `InferraToRdfCompiler`)
- [ ] `RuleSetImportResolver` + `ModuleRegistry` (eager compilation, hash-invalidation)
- [ ] `IMPORT:` / `RULE SET:` token integration + `NodeOrigin` metadata
- [ ] `_forward_propagate_incremental()` using impacted subgraph BFS + `HyperAdjacencyGraph`
- [ ] RDFLib in-memory semantic cache (preloaded at session start)
- [ ] Replace `self.__iterate_ie` with `IterationEngine` using `IterationPort`. Deprecate nested engine.

### 🔹 Phase 3: Hybrid Reasoning & Orchestrator (Weeks 5–6)
*Focus: Hybrid reasoning loop, ontology integration, PROV-O auditability.*
- [ ] Wrap `InferenceEngine` in `BackwardChainOrchestrator` + `SessionManager`
- [ ] Implement ontology pre-reasoning at session start (sync)
- [ ] Trigger async post-reasoning after answer ingestion; inject results into `semantic_facts` layer
- [ ] Formalize fixed-point convergence criteria: `Goal ∈ WM` AND `Mandatory ⊆ WM` AND `Δ(WM) == 0`
- [ ] Generate PROV-O triples per conclusion (`inf:Session`, `inf:Conclusion`, `prov:wasGeneratedBy`)
- [ ] Integrate `fact_source` + `origin_module` into `/summary` & `/trace` responses
- [ ] Extract `QuestionStrategy` from `question_resolver.py`

### 🔹 Phase 4: Frontend, LLM & Enterprise Hardening (Weeks 7–8)
*Focus: UI updates, LLM orchestration, production hardening.*
- [ ] Multi-worker session store (Redis), structured logging, Docker Compose
- [ ] Load testing: concurrent sessions, modular imports, iterate nodes, ontology sync
- [ ] LLM orchestration: NL→goal mapping, question enhancement, explanation generation via RDF context
- [ ] Vite UI: dynamic forms, iterate progress, trace visualization, import graph viewer
- [ ] Remove legacy adapters. Enforce port-only imports. CI boundary checks (`import-linter`).

### 🔄 Cross-Cutting Recommendations
- **Testing Strategy:** Unit (ports, graph, iterate context, layered memory), Property-based (Hypothesis for merge invariance, topo-order stability, convergence determinism), E2E (Vite → FastAPI → Engine → Fuseki → PROV-O)
- **CI/CD & Developer Experience:** Pre-commit hooks (`ruff`, `mypy`, `black`), `import-linter` to enforce port boundaries, GitHub Actions matrix tests, local `docker compose up` dev environment
- **Observability & Monitoring:** OpenTelemetry traces, metrics (questions asked, ontology delta, cache hit rate, iteration count), alerts (convergence cap hit, RDF drift, Fuseki timeout)
- **Rollout & Migration Plan:** Feature flags → Phase 1 stable → Phase 2 async live → Phase 3 hybrid default → Deprecate legacy matrix → Enforce strict port imports

---

## 🌐 14. API Contract & Integration Mapping

### 14.1 Core Endpoints
```yaml
POST /api/v1/inference/sessions
  Body: { rule_name, target_node_name }
  Returns: { session_id, rule_name, resolved_imports: [] }

GET /api/v1/inference/next-question?session_id=
  Returns: { questions: [{ text, value_type, origin_module? }], has_more, iterate_progress?: { answered, total } }

POST /api/v1/inference/feed-answer
  Body: { session_id, question, answer: { type, value } }
  Action: Inject → back-propagate → async post-reason → incremental forward
  Returns: { has_more, goal_rule_name?, goal_rule_value? }

GET /api/v1/inference/summary?session_id=
  Returns: { summary: [{ node_text, node_value, fact_source, origin_module? }] }

GET /api/v1/inference/trace?session_id=
  Returns: PROV-O session trace + working_memory snapshot + import chain

GET /api/v1/rules/{rule_name}/imports
  Returns: { rule_name, imports: [], import_graph: {} }

POST /api/v1/rules/validate
  Body: { rule_name, rule_text }
  Returns: { valid: bool, errors: [], warnings: [] }
```

### 14.2 Module Mapping & Changes
| Existing Module | INFERRA Role | Change Required |
|-----------------|--------------|-----------------|
| `assessment_state.py` | Layered working memory | Extract `LayeredFactStore` + `FactStorePort`; unified read view unchanged |
| `inference_engine.py` | Core backward-chaining | Wrap in `BackwardChainOrchestrator`; extract `HybridReasoningEngine` |
| `iterate_line.py` | List iteration | Replace nested engine with `IterationEngine` + `IterationPort` |
| `topo_sort.py` | Dependency order | Migrate to `DependencyGraphService` + `graphlib.TopologicalSorter` |
| `question_resolver.py` | Question gating | Extract `QuestionStrategy`; keep API intact |
| `rule_set_scanner.py` | Parsing | Add `IMPORT:`/`RULE SET:` handling; fix silent abort |
| `node.py` | Node ID management | Per-parse `id_generator`; `reset()` at parse start |
| `tokenizer_matcher_constant.py` | Tokenisation | Add `IMPORT_MATCHER` |
| `rule_service.py` | Rule persistence | Add `save_session_history()`; validation gate; version support |

---

## ⚠️ 15. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Circular imports | Medium | Critical | DFS detection in resolver; synchronous validation blocks save |
| Module version drift | Medium | High | `ModuleRegistry` invalidation on `RuleUpdated`; sessions pinned to versions |
| Node ID collision | High (current) | Critical | Per-parse `id_generator` (Pre-Condition §3.1) |
| Semantic drift (Fuseki) | Medium | High | Hash comparison; INFERRA DB overwrites on divergence |
| Convergence non-termination | Low | Critical | Iteration cap (default 10); alert on hit |
| Explainability loss | High (without layered memory) | High | `FactSource` enum + PROV-O trace generation |
| Fuseki in hot path | Medium | Medium | Semantic cache preloaded; async post-reasoning |
| Multi-worker session loss | High (if in-memory) | High | Enforce Redis; startup warning |
| Port migration regressions | Medium | High | `import-linter` CI checks, feature flags, exhaustive integration tests |

---

## 🏁 16. Final Assessment

INFERRA is evolving into a genuinely novel platform — one where rules behave like software packages, semantic ontologies enrich inference silently, list iterations produce auditable aggregate conclusions, and every decision carries a full provenance chain traceable to its module, session, and fact origin.

**Three architectural commitments that must not change:**
1. **Backward-chaining** as the primary question driver — deterministic, auditable
2. **Rule DB** as the single source of truth — all other representations are projections
3. **Working memory** as the central execution state — all reasoning converges here

With the additions in this document, INFERRA becomes:
- ✅ **Composable** — rule sets as importable, versioned, reusable modules
- ✅ **Deterministic** — same inputs, same conclusions, always
- ✅ **Auditable** — every conclusion traceable to source, module, and session
- ✅ **Scalable** — incremental propagation, async RDF sync, cached modules, Redis sessions
- ✅ **Explainable** — PROV-O traces, layered fact origins, import chains, iterate progress
- ✅ **Robust** — typed ontology boundary, circular import detection, validated rule saves, hypergraph traversal
- ✅ **Enterprise-ready** — no silent failures, drift detection, versioned modules, port-based isolation

> **INFERRA is not just an inference engine.**  
> It is a platform where rules, relationships, and reasoning converge into provable, auditable, composable, intelligent decisions.

---
*Document generated for INFERRA architecture planning. Aligns with Python backend, Fuseki RDF store, AWS Graph Explorer, LLM orchestration, and Vite frontend stack. Ready for sprint planning, implementation, and stakeholder review.*```markdown
# INFERRA: Consolidated Architecture & Implementation Plan
## Hybrid Reasoning Platform — *"From rules to reasoning."*

**Document Status:** Consolidated v6 — Merges original architecture proposal, additional review, full codebase analysis, modular rule imports, advanced dependency graph migration, IterateLine unification, enterprise traceability, and **port-based modularization architecture**. Conflicts resolved with explicit rationale. Ready for sprint planning and stakeholder review.

---

## 📖 1. Executive Summary

INFERRA evolves from a deterministic rule engine into a **Hybrid Reasoning Platform** that unifies symbolic logic, semantic knowledge representation, and stateful execution. This document provides a production-ready blueprint covering:

- ✅ **Async event-driven sync** replacing blocking rule projection
- ✅ **Port-based modularization** for scalability, testability, and zero-downtime migration
- ✅ **Layered working memory** separating asserted, inferred, and semantic facts
- ✅ **Incremental forward propagation** replacing full-graph recomputation
- ✅ **Hyper-Adjacency Graph with Immutable Snapshots** replacing the legacy 2D dependency matrix
- ✅ **IterateLine unification** eliminating nested `InferenceEngine` anti-pattern
- ✅ **Modular rule sets** with eager import resolution & circular dependency detection
- ✅ **PROV-O explanation model** for full auditability & traceability

These enhancements preserve INFERRA's deterministic backward-chaining core while enabling scalable, explainable, and ontology-accelerated decision workflows.

---

## 🎯 2. Brand Alignment & Conceptual Foundation

| Element | Definition |
|---------|------------|
| **Product Name** | INFERRA |
| **Acronym** | Inference Engine for Rule-based and Relational Reasoning Architecture |
| **Category** | Hybrid Reasoning Platform — Symbolic + Semantic + Stateful Execution |
| **Tagline** | *"From rules to reasoning."* |

### Conceptual Pillars ↔ Technical Mapping
| INFERRA Pillar | Technical Component | Role in Architecture |
|----------------|---------------------|----------------------|
| Rule-Based Logic | `BackwardChainOrchestrator`, `LayeredFactStore` | Deterministic backward-chaining, constraint enforcement, dependency resolution |
| Relational Intelligence | Fuseki (RDF/OWL), `inf:` vocabulary, Semantic Cache | Ontology reasoning, cross-domain linking, implicit relationship derivation |
| Inference Execution | `HybridReasoningEngine`, `QuestionStrategy`, `IterationEngine` | Path optimisation, fixed-point convergence, question gating, stateful traversal |
| Modular Rule Composition | `RuleCompiler`, `ModuleResolver`, `RuleSetParser` | Library-style rule reuse, circular import detection, eager compilation |
| Stateful Decision Flow | `SessionManager`, Layered Working Memory, Redis session store | Context preservation, fact provenance, decision lineage, session replayability |

> **Core Differentiator:** INFERRA does not just store or execute logic — it *derives* decisions through hybrid symbolic-semantic reasoning, with composable modular rule sets, port-based isolation, and a full audit trail for every conclusion.

---

## ⚠️ 3. Pre-Conditions: Critical Codebase Fixes Required First

These bugs will cause runtime failures during INFERRA integration if not resolved immediately.

| # | Issue | File | Fix |
|---|-------|------|-----|
| 3.1 | `Node.__static_node_id` never resets between sessions | `node.py` | Call `Node.reset()` at parse start. Pass per-parse `id_generator` for thread safety. |
| 3.2 | `FactValue` missing `set_default_value` | `metadata_line.py` | Add `set_default_value()` & `get_default_value()` methods to `FactValue`. |
| 3.3 | `AssessmentState._should_create_list` calls `get_operator()` on base `Node` | `assessment_state.py` | Guard with `isinstance(node, ComparisonLine)` before calling `get_operator()`. |
| 3.4 | HTTP layer bypasses `RuleService` for history | `inference.py` | Add `save_session_history()` to `RuleService`; route all persistence through it. |
| 3.5 | `lru_cache` misuse on `get_inference_session_service` | `dependencies.py` | Remove `lru_cache`; singleton already guaranteed by `get_session_store` cache. |
| 3.6 | Duplicate `doc_converter.py` / `file_service.py` | `doc_converter.py` | Delete duplicate; update `streamer.py` imports to use `FileConversionService`. |
| 3.7 | `ALLOWED_EXTENSIONS` parsed with `ast.literal_eval` per request | `settings.py` | Declare as `List[str]`; let Pydantic parse from environment automatically. |

---

## 🏗️ 4. Core Architecture & Design Principles

### 4.1 Dual-Representation Strategy (Canonical → Semantic Projection)
- **INFERRA Rule DB** is the single source of truth. All authoring, LLM generation, and validation occur here.
- **Fuseki RDF** is a **loss-aware semantic projection**. It mirrors rule structure but expands with OWL inference, transitive relationships, and class hierarchies.
- **Sync Flow:** `Rule Save → Validation (Sync) → Event → Async Compiler Worker → Fuseki Insert → Cache Invalidation`
- **Mapping Versioning:** Each projection includes `compiler_version` and source hash. INFERRA DB always wins on divergence.

### 4.2 Async Sync Pipeline
| Stage | Sync Mode | Rationale |
|-------|-----------|-----------|
| Rule validation (syntax, types, import resolution, DAG check) | Synchronous | Must fail-fast before persistence |
| RDF compilation & Fuseki projection | Asynchronous | Decouples write latency; tolerates Fuseki unavailability |
| Ontology pre-reasoning (session start) | Synchronous | Must complete before `InferenceEngine` initialises |
| Ontology post-reasoning (after answer) | Asynchronous | Runs in background; results injected on next question cycle |

```
Rule Save
  ├─► Validate (sync): syntax, types, circular import detection, DAG check
  │     └─► Reject if invalid (rollback)
  └─► Persist Rule (sync)
        └─► Publish RuleUpdated event (async)
              └─► InferraToRdfCompiler worker → SPARQL INSERT → Fuseki
```
**Implementation:** Redis + Celery, or AWS SQS/EventBridge.

### 4.3 Architectural Commitments (Non-Negotiable)
1. **Backward-chaining** remains the primary question driver — deterministic, auditable
2. **Rule DB** is the single source of truth — all other representations are projections
3. **Working memory** is the central execution state — all reasoning converges here
4. **Port-based isolation** ensures modularization does not disrupt core logic
5. Convergence is **deterministic** — capped iterations, explicit delta tracking, fallback guarantees

---

## 🧩 5. Modularization Strategy & Port-Based Architecture

Modularization is an **architectural prerequisite** for INFERRA's hybrid reasoning, async sync, PROV-O traceability, and enterprise scalability goals. It replaces monolithic coupling with explicit interface contracts.

### 5.1 Recommended Module Boundaries
| Current File/Component | Recommended Module | Responsibility | INFERRA Alignment |
|------------------------|-------------------|----------------|-------------------|
| `inference_engine.py` | `BackwardChainOrchestrator` | Goal traversal, dependency evaluation, convergence loop | Hybrid reasoning fixed-point, `InferenceContext` routing |
| `assessment_state.py` | `LayeredFactStore` | `asserted`/`inferred`/`semantic` memory, unified read view, provenance | `FactSource` enum, PROV-O `wasGeneratedBy`, traceability |
| `assessment.py` / `assesments.py` | `SessionManager` | Multi-goal routing, `mandatory_list` tracking, state snapshots | Immutable `SessionSnapshot`, replayability, convergence checks |
| `topo_sort.py` + graph logic | `DependencyGraphService` | `HyperAdjacencyGraph` management, incremental dirty tracking, topo-sort | O(V+E) traversal, subgraph extraction, RDF edge projection |
| `question_resolver.py` | `QuestionStrategy` | Pluggable gating logic (conservative, ontology-enhanced, LLM-augmented) | External API unchanged, strategies swappable at runtime |
| `iterate_line.py` | `IterationEngine` | List quantifier logic, `IterateContext`, progress tracking, unified subgraph eval | Eliminates nested engine, `FactSource.INFERRED` tagging |
| `rule_set_scanner.py` / `parser.py` | `RuleCompiler` + `ModuleResolver` | `IMPORT:` resolution, `NodeSet` merging, DAG validation, version pinning | `RuleSetImportResolver`, `ModuleRegistry`, sync pipeline gate |
| *(New)* | `OntologyPort` + `SemanticCache` | Async RDF sync, PROV-O generation, type bridge, pre/post-reasoning | `FusekiOntologyAdapter`, cache preloading, delta tracking |

### 5.2 Key Interface Contracts (Ports & Adapters)
```python
# src/ports/fact_store_port.py
class FactStorePort(Protocol):
    def get_unified_view(self) -> Dict[str, FactValue]: ...
    def set_fact(self, name: str, value: FactValue, source: FactSource) -> None: ...
    def get_changed_since(self, timestamp: float) -> Set[str]: ...

# src/ports/graph_port.py
class DependencyGraphPort(Protocol):
    def get_parents(self, node_id: int) -> Set[int]: ...
    def get_child_groups(self, node_id: int) -> Tuple[DependencyGroup, ...]: ...
    def get_topo_order(self) -> List[int]: ...
    def mark_dirty(self, node_ids: Set[int]) -> None: ...

# src/ports/iteration_port.py
class IterationPort(Protocol):
    def initialise(self, list_size: int, quantifier: str) -> None: ...
    def record_answer(self, index: int, value: bool) -> bool: ...  # returns True if complete
    def evaluate(self) -> FactValue: ...
    def get_progress(self) -> Tuple[int, int]: ...
```
**Rule:** Core engine modules depend only on `Port` interfaces. Adapters implement them. Zero cross-module direct imports.

### 5.3 Migration Strategy (Zero-Downtime, Backward-Compatible)
| Phase | Action | Risk Mitigation |
|-------|--------|-----------------|
| **1. Extract Fact Store** | Wrap `AssessmentState` in `LayeredFactStore` adapter. Route all `set_fact()`/`get_working_memory()` through new class. | Keep old dict as fallback. Add `FactSource` default. |
| **2. Extract Graph Service** | Build `HyperAdjacencyGraph` + `MatrixToGraphAdapter`. Engine uses adapter for `get_parents()`, `get_child_groups()`. | Feature flag `USE_HYPERGRAPH=true`. Run parallel topo sorts in tests. |
| **3. Extract Iteration Engine** | Replace `self.__iterate_ie` with `IterationEngine` using `IterationPort`. Keep old logic under `LEGACY_ITERATE=true`. | Unit tests verify `ALL`/`SOME`/`NONE`/N parity. |
| **4. Extract Question Strategy** | Move `_requires_user_input()` into `QuestionStrategy`. Default = current logic. Add `OntologyEnhancedStrategy` later. | Zero change to external `QuestionResolver` API. |
| **5. Decouple Session Manager** | Move `mandatory_list`/convergence checks into `SessionManager`. Engine calls `session.check_convergence()`. | Keep inline checks until Phase 5 complete. |
| **6. Freeze & Deprecate** | Remove legacy adapters. Enforce port-only imports. Update CI to block cross-module violations. | Run integration suite with 100% coverage before merge. |

---

## 🕸️ 6. Hyper-Adjacency Graph Architecture (Matrix Migration)

Given INFERRA’s architectural demands, the legacy 2D `dependency_matrix` must transition to a **Hyper-Adjacency Graph with Immutable Snapshots**, implemented as `DependencyGraphService`.

### 6.1 Why the 2D Matrix Falls Short
| Aspect | 2D Matrix (`dependency_matrix`) | INFERRA Requirement Gap |
|--------|-------------------------------|-------------------------|
| N-ary Grouping | Flattens `AND [A, B, C]` into 3 edges | NADIA evaluates dependency groups holistically. Grouping semantics lost. |
| Space Complexity | `O(N²)` → wastes memory on sparse graphs | Rule sets scale to 1000+ nodes; >90% matrix is `-1` |
| Incremental Traversal | Requires full matrix scan | Needs impacted subgraph propagation, not full recomputation |
| Ontology Sync | No native edge metadata | `inf:dependsOn` requires explicit parent/child + dependency type |
| Session Replay | Mutable state → cross-session bleed risk | INFERRA needs deterministic, versioned snapshots for audit & compliance |

### 6.2 Recommended Structure: `HyperAdjacencyGraph`
```python
from typing import Dict, Set, Tuple, FrozenSet, Optional
from dataclasses import dataclass, field
from enum import IntFlag

class DependencyType(IntFlag):
    AND = 1; OR = 2; MANDATORY = 4; NOT = 8; KNOWN = 16

@dataclass(frozen=True)
class DependencyGroup:
    dep_type: DependencyType
    children: FrozenSet[int]  # Immutable child node IDs

class HyperAdjacencyGraph:
    def __init__(self):
        self.children: Dict[int, Tuple[DependencyGroup, ...]] = {}
        self.parents: Dict[int, Set[int]] = {}
        self.edge_provenance: Dict[int, dict] = field(default_factory=dict)
        self._topo_cache: Optional[Tuple[int, ...]] = None

    def add_dependency_group(self, parent: int, dep_type: DependencyType, children: Set[int]) -> None:
        group = DependencyGroup(dep_type, frozenset(children))
        self.children.setdefault(parent, []).append(group)
        for child in children:
            self.parents.setdefault(child, set()).add(parent)
        self._topo_cache = None

    def get_parent_edges(self, node_id: int) -> Set[int]:
        return self.parents.get(node_id, set())

    def get_child_groups(self, node_id: int) -> Tuple[DependencyGroup, ...]:
        return self.children.get(node_id, ())
```

### 6.3 Migration Strategy (Phased & Backward-Compatible)
| Phase | Action |
|-------|--------|
| **A: Adapter** | Wrap existing matrix with `MatrixToHyperGraphAdapter`. Keep legacy APIs functional. |
| **B: Refactor** | Update `InferenceEngine._back_propagating` to use `graph.parents` + queue traversal. |
| **C: Topo Sort** | Migrate `topo_sort.py` to `graphlib.TopologicalSorter`. Cache order. Invalidate on rule update. |
| **D: Deprecate** | Remove `DependencyMatrix` entirely once load tests validate `HyperAdjacencyGraph`. |

**Impact:** ~98% memory reduction, 20–100x faster traversal, direct RDF/PROV-O serialization, incremental subgraph support, thread-safe session replay.

---

## 🔄 7. IterateLine Unification & Robustness

### 7.1 The Anti-Pattern: Nested `InferenceEngine`
The current `IterateLine` instantiates a **separate `InferenceEngine`** for every iteration. This causes:
- ❌ State fragmentation & broken traceability
- ❌ Ontology blindness (post-reasoning misses iterate facts)
- ❌ Impossible incremental propagation across boundaries
- ❌ Heavy memory/CPU overhead per list item

### 7.2 Recommended Architecture: Unified Subgraph Evaluation
Replace the nested engine with an `IterationEngine` implementing `IterationPort` that operates entirely within the parent engine's state, working memory, and topological order.

```python
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class IterateContext:
    list_name: str
    list_size: int
    quantifier: str  # "ALL", "NONE", "SOME", or integer string
    progress: Dict[int, bool] = field(default_factory=dict)  # index → satisfied?
    node_prefix_map: Dict[str, int] = field(default_factory=dict)
    is_initialised: bool = False
```

### 7.3 Refactored Core Methods
```python
def feed_iterate_answer(self, question_name: str, node_value: Any, node_value_type: FactValueType) -> bool:
    idx = self._extract_ordinal_index(question_name)
    is_true = bool(node_value) if node_value_type == FactValueType.BOOLEAN else str(node_value).strip().lower() == "true"
    self.progress[idx] = is_true
    return len(self.progress) == self.list_size

def self_evaluate(self, working_memory: Dict[str, FactValue]) -> FactValue:
    true_count = sum(1 for v in self.progress.values() if v)
    q = self.quantifier
    if q == "ALL": return FactValue(true_count == self.list_size)
    if q == "NONE": return FactValue(true_count == 0)
    if q == "SOME": return FactValue(true_count > 0)
    try: return FactValue(true_count == int(q))
    except (ValueError, TypeError): return FactValue(False)
```

### 7.4 Alignment with INFERRA Architecture
| INFERRA Pillar | Benefit from Unified Subgraph |
|----------------|-------------------------------|
| Hybrid Reasoning | Ontology post-reasoning sees all iterate facts. Semantic enrichment can pre-fill list items. |
| Incremental Forward Propagation | Changed iterate facts propagate upward through `HyperAdjacencyGraph.parents` → triggers re-aggregation. |
| PROV-O Traceability | Every list item answer carries `iterate_index`, `list_name`, `FactSource`. Full audit trail preserved. |
| Memory Efficiency | Eliminates O(N²) matrix allocation per iterate. Single engine, single topo sort, single working memory. |

---

## 📦 8. Modular Rule Sets — Import System

### 8.1 Syntax & Design
```
RULE SET: Veteran Eligibility Check

IMPORT: Service Period Rules
IMPORT: Disability Assessment Rules @ v2.3

# Reference: s.4 Veterans Entitlements Act
# Section: section 4
applicant is eligible for full benefit
    AND MANDATORY service period is valid
    AND MANDATORY disability rating is determined
```
- **Why `IMPORT:`?** Fits existing tokeniser pattern. Unambiguous. Starts at column 0.
- **Evaluator Model:** Imported nodes merge into unified `NodeSet`. Inference engine treats all nodes uniformly. Import origin tracked in `NodeOrigin` metadata for auditability.
- **Loading Strategy:** Eager compilation at session start with `ModuleRegistry` cache. Ensures circular import detection upfront and deterministic `Node` ID allocation.

### 8.2 `ModuleRegistry` & Circular Detection
```python
@dataclass
class CompiledModule:
    rule_name: str
    content_hash: str
    node_set: NodeSet
    compiled_at: datetime

class ModuleRegistry:
    def __init__(self):
        self._cache: Dict[str, CompiledModule] = {}
        self._lock = threading.RLock()

    def get(self, rule_name: str, content_hash: str) -> Optional[CompiledModule]:
        with self._lock:
            entry = self._cache.get(rule_name)
            return entry if (entry and entry.content_hash == content_hash) else None
```
Circular detection uses DFS with `visited` + `in_stack` sets during rule validation (synchronous, blocks save).

### 8.3 NodeSet Merging Rules
- **Name collisions:** Importing rule set wins (Python-style shadowing).
- **`FIXED`/`INPUT`:** Merged flat; importer wins.
- **Dependencies:** Cross-module references fully supported.
- **Topo Sort:** Re-run globally after merge to ensure correct evaluation order.

---

## 🧠 9. Layered Working Memory & State Management

Mixing user input, rule-derived, and ontology-derived facts breaks traceability. Introduce layered storage with a unified read view, implemented as `LayeredFactStore` adhering to `FactStorePort`.

```python
class FactSource(Enum):
    ASSERTED = "ASSERTED"   # user input
    INFERRED = "INFERRED"   # rule engine conclusions
    SEMANTIC = "SEMANTIC"   # ontology-derived

class AssessmentState:
    def __init__(self):
        self.__asserted_facts: Dict[str, FactValue] = {}
        self.__inferred_facts: Dict[str, FactValue] = {}
        self.__semantic_facts: Dict[str, FactValue] = {}

    def get_working_memory(self) -> Dict[str, FactValue]:
        return {
            **self.__semantic_facts,
            **self.__inferred_facts,
            **self.__asserted_facts,   # asserted wins on collision
        }

    def set_fact(self, name: str, value: FactValue,
                 source: FactSource = FactSource.ASSERTED) -> None:
        {
            FactSource.ASSERTED: self.__asserted_facts,
            FactSource.INFERRED: self.__inferred_facts,
            FactSource.SEMANTIC: self.__semantic_facts,
        }[source][name] = value
```
All existing callers continue to work unchanged. `source` defaults to `ASSERTED`.

---

## 🔄 10. Hybrid Reasoning Loop & Fixed-Point Convergence

INFERRA retains backward-chaining as the primary question driver, orchestrated by `HybridReasoningEngine` wrapping the `BackwardChainOrchestrator`. Ontology reasoning acts as a semantic accelerator.

```
[1] SESSION START
    └─► RuleSetImportResolver.resolve(rule_name) → merges imports
        └─► OntologyPort.enrich_fact_dictionary(merged_node_set)

[2] BACKWARD-CHAIN
    └─► BackwardChainOrchestrator.get_next_question(target)
        (ontology + imported facts auto-suppress prompts via QuestionStrategy)

[3] ANSWER INGEST
    └─► feed_answer_to_node() → back-propagation → updates ASSERTED layer

[4] POST-REASONING (async)
    └─► OntologyPort.persist_conclusions() → OWL reasoner → updates SEMANTIC layer

[5] INCREMENTAL FORWARD PROPAGATION
    └─► Re-evaluate impacted subgraph only (changed nodes → parents → topo sort)

[6] CONVERGENCE CHECK
    └─► Goal ∈ working_memory AND mandatory_list ⊆ working_memory
        AND working_memory[t] == working_memory[t-1] AND ontology_delta == 0
    └─► Auto-conclude or loop to [2]
```

### 10.1 Incremental Forward Propagation
```python
def _forward_propagate_incremental(self, changed_nodes: Set[int]) -> None:
    impacted = set(changed_nodes)
    queue = list(changed_nodes)
    while queue:
        node = queue.pop(0)
        for parent in self.graph.get_parent_edges(node):
            if parent not in impacted:
                impacted.add(parent)
                queue.append(parent)
    
    # Topo-sort ONLY impacted subgraph
    subgraph = {n: self.graph.get_child_groups(n) for n in impacted}
    ordered = self._topo_sort_subgraph(subgraph)
    for node_id in ordered:
        if self._can_evaluate_parent(node_id):
            self._evaluate_and_store(node_id)
```

### 10.2 Convergence Criteria
Let `W_t = working_memory at iteration t`. Converged if:
1. `Goal ∈ W_t`
2. `Mandatory ⊆ W_t`
3. `W_t == W_(t-1)` (fixed-point)
4. `Δ(ontology_delta) == 0` (no new triples)

---

## 🌐 11. Async Sync Pipeline & Ontology Integration

### 11.1 Event-Driven Sync Architecture
| Stage | Sync Mode | Rationale |
|-------|-----------|-----------|
| Rule validation (syntax, types, import resolution, DAG check) | Synchronous | Must fail-fast before persistence |
| RDF compilation & Fuseki projection | Asynchronous | Decouples write latency; tolerates Fuseki unavailability |
| Ontology pre-reasoning (session start) | Synchronous | Must complete before engine initialises |
| Ontology post-reasoning (after answer) | Asynchronous | Runs in background; results injected on next question cycle |

```
Rule Save
  ├─► Validate (sync): syntax, types, circular import detection, DAG check
  │     └─► Reject if invalid (rollback)
  └─► Persist Rule (sync)
        └─► Publish RuleUpdated event (async)
              └─► InferraToRdfCompiler worker → SPARQL INSERT → Fuseki
```
**Implementation:** Redis + Celery, or AWS SQS/EventBridge.

### 11.2 `OntologyPort` Interface & Semantic Cache
```python
class OntologyPort(metaclass=ABCMeta):
    @abstractmethod
    def enrich_fact_dictionary(self, node_set: NodeSet, rule_name: str) -> None: ...
    @abstractmethod
    def persist_conclusions(self, rule_name: str, session_id: str, working_memory: dict) -> None: ...
    @abstractmethod
    def run_reasoner(self) -> list[tuple]: ...
```
- **Implementations:** `FusekiOntologyAdapter` (prod), `NullOntologyAdapter` (default), `InMemoryOntologyAdapter` (tests).
- **Semantic Cache:** Preload relevant RDF triples into RDFLib in-memory graph at session start. Eliminates Fuseki from the hot execution path. Queries only run on deltas post-reasoning.

### 11.3 Type Safety Bridge
```python
RDF_RANGE_TO_FACT_TYPE = {
    "xsd:boolean": FactValueType.BOOLEAN, "xsd:integer": FactValueType.INTEGER,
    "xsd:decimal": FactValueType.DOUBLE, "xsd:date": FactValueType.DATE,
    "xsd:string": FactValueType.STRING, "xsd:anyURI": FactValueType.URL,
}
```

---

## 📜 12. PROV-O Traceability & Explanation Model

### 12.1 `InferenceContext`
```python
@dataclass
class InferenceContext:
    session_id: str
    rule_name: str
    target_node_name: str
    import_chain: list[str] = field(default_factory=list)
    iteration_count: int = 0
    changed_node_ids: set[int] = field(default_factory=set)
    ontology_delta: int = 0
    fact_source_map: dict[str, FactSource] = field(default_factory=dict)
    trace: list[TraceEntry] = field(default_factory=list)
```

### 12.2 PROV-O Trace Schema
```turtle
<session:abc123> a inf:Session, prov:Activity ;
    prov:startedAtTime "2025-01-01T10:00:00Z"^^xsd:dateTime ;
    inf:evaluatedRule <rule:VeteranEligibilityCheck> ;
    inf:importedModules <rule:ServicePeriodRules> .

<conclusion:xyz789> a inf:Conclusion, prov:Entity ;
    prov:wasGeneratedBy <session:abc123> ;
    inf:nodeText "applicant is eligible for full benefit" ;
    inf:nodeValue "true" ;
    inf:factSource inf:INFERRED ;
    inf:originModule <rule:VeteranEligibilityCheck> ;
    inf:dependedOn <fact:service_period_valid>, <fact:disability_rating> .
```

---

## 📅 13. Phased Implementation Plan (Core → Scalability → Strategic)

### 🔹 Phase 1: Core Functionality & Fact Store (Weeks 0–2)
*Focus: Stabilize engine, fix critical bugs, establish layered working memory, prepare dependency graph foundation.*
- [ ] Fix §3.1–3.7 (Node ID reset, FactValue defaults, isinstance guards, lru_cache, duplicates, Pydantic settings)
- [ ] Refactor `assessment_state.py` → 3-layer working memory + unified read view (`FactStorePort` adapter)
- [ ] Extract duplicated iterate guards → `_ensure_iterate_context()`
- [ ] Implement `IterateContext` + `feed_iterate_answer()` + progress tracking
- [ ] Create `HyperAdjacencyGraph` + `MatrixToHyperGraphAdapter` (`DependencyGraphPort`)
- [ ] Deploy `RuleValidationService` as synchronous gate before persistence
- [ ] Baseline API: `/sessions`, `/next-question`, `/feed-answer`, `/summary`

### 🔹 Phase 2: Graph Service & Iteration Engine (Weeks 3–4)
*Focus: Incremental propagation, modular imports, caching, graph traversal optimization.*
- [ ] Update `_back_propagating` to use `graph.parents` + queue traversal
- [ ] Migrate `topo_sort.py` to `graphlib.TopologicalSorter` + topo-order cache
- [ ] Event-driven async sync pipeline (`RuleUpdated` → Celery/SQS → `InferraToRdfCompiler`)
- [ ] `RuleSetImportResolver` + `ModuleRegistry` (eager compilation, hash-invalidation)
- [ ] `IMPORT:` / `RULE SET:` token integration + `NodeOrigin` metadata
- [ ] `_forward_propagate_incremental()` using impacted subgraph BFS + `HyperAdjacencyGraph`
- [ ] RDFLib in-memory semantic cache (preloaded at session start)
- [ ] Replace `self.__iterate_ie` with `IterationEngine` using `IterationPort`. Deprecate nested engine.

### 🔹 Phase 3: Hybrid Reasoning & Orchestrator (Weeks 5–6)
*Focus: Hybrid reasoning loop, ontology integration, PROV-O auditability.*
- [ ] Wrap `InferenceEngine` in `BackwardChainOrchestrator` + `SessionManager`
- [ ] Implement ontology pre-reasoning at session start (sync)
- [ ] Trigger async post-reasoning after answer ingestion; inject results into `semantic_facts` layer
- [ ] Formalize fixed-point convergence criteria: `Goal ∈ WM` AND `Mandatory ⊆ WM` AND `Δ(WM) == 0`
- [ ] Generate PROV-O triples per conclusion (`inf:Session`, `inf:Conclusion`, `prov:wasGeneratedBy`)
- [ ] Integrate `fact_source` + `origin_module` into `/summary` & `/trace` responses
- [ ] Extract `QuestionStrategy` from `question_resolver.py`

### 🔹 Phase 4: Frontend, LLM & Enterprise Hardening (Weeks 7–8)
*Focus: UI updates, LLM orchestration, production hardening.*
- [ ] Multi-worker session store (Redis), structured logging, Docker Compose
- [ ] Load testing: concurrent sessions, modular imports, iterate nodes, ontology sync
- [ ] LLM orchestration: NL→goal mapping, question enhancement, explanation generation via RDF context
- [ ] Vite UI: dynamic forms, iterate progress, trace visualization, import graph viewer
- [ ] Remove legacy adapters. Enforce port-only imports. CI boundary checks (`import-linter`).

### 🔄 Cross-Cutting Recommendations
- **Testing Strategy:** Unit (ports, graph, iterate context, layered memory), Property-based (Hypothesis for merge invariance, topo-order stability, convergence determinism), E2E (Vite → FastAPI → Engine → Fuseki → PROV-O)
- **CI/CD & Developer Experience:** Pre-commit hooks (`ruff`, `mypy`, `black`), `import-linter` to enforce port boundaries, GitHub Actions matrix tests, local `docker compose up` dev environment
- **Observability & Monitoring:** OpenTelemetry traces, metrics (questions asked, ontology delta, cache hit rate, iteration count), alerts (convergence cap hit, RDF drift, Fuseki timeout)
- **Rollout & Migration Plan:** Feature flags → Phase 1 stable → Phase 2 async live → Phase 3 hybrid default → Deprecate legacy matrix → Enforce strict port imports

---

## 🌐 14. API Contract & Integration Mapping

### 14.1 Core Endpoints
```yaml
POST /api/v1/inference/sessions
  Body: { rule_name, target_node_name }
  Returns: { session_id, rule_name, resolved_imports: [] }

GET /api/v1/inference/next-question?session_id=
  Returns: { questions: [{ text, value_type, origin_module? }], has_more, iterate_progress?: { answered, total } }

POST /api/v1/inference/feed-answer
  Body: { session_id, question, answer: { type, value } }
  Action: Inject → back-propagate → async post-reason → incremental forward
  Returns: { has_more, goal_rule_name?, goal_rule_value? }

GET /api/v1/inference/summary?session_id=
  Returns: { summary: [{ node_text, node_value, fact_source, origin_module? }] }

GET /api/v1/inference/trace?session_id=
  Returns: PROV-O session trace + working_memory snapshot + import chain

GET /api/v1/rules/{rule_name}/imports
  Returns: { rule_name, imports: [], import_graph: {} }

POST /api/v1/rules/validate
  Body: { rule_name, rule_text }
  Returns: { valid: bool, errors: [], warnings: [] }
```

### 14.2 Module Mapping & Changes
| Existing Module | INFERRA Role | Change Required |
|-----------------|--------------|-----------------|
| `assessment_state.py` | Layered working memory | Extract `LayeredFactStore` + `FactStorePort`; unified read view unchanged |
| `inference_engine.py` | Core backward-chaining | Wrap in `BackwardChainOrchestrator`; extract `HybridReasoningEngine` |
| `iterate_line.py` | List iteration | Replace nested engine with `IterationEngine` + `IterationPort` |
| `topo_sort.py` | Dependency order | Migrate to `DependencyGraphService` + `graphlib.TopologicalSorter` |
| `question_resolver.py` | Question gating | Extract `QuestionStrategy`; keep API intact |
| `rule_set_scanner.py` | Parsing | Add `IMPORT:`/`RULE SET:` handling; fix silent abort |
| `node.py` | Node ID management | Per-parse `id_generator`; `reset()` at parse start |
| `tokenizer_matcher_constant.py` | Tokenisation | Add `IMPORT_MATCHER` |
| `rule_service.py` | Rule persistence | Add `save_session_history()`; validation gate; version support |

---

## ⚠️ 15. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Circular imports | Medium | Critical | DFS detection in resolver; synchronous validation blocks save |
| Module version drift | Medium | High | `ModuleRegistry` invalidation on `RuleUpdated`; sessions pinned to versions |
| Node ID collision | High (current) | Critical | Per-parse `id_generator` (Pre-Condition §3.1) |
| Semantic drift (Fuseki) | Medium | High | Hash comparison; INFERRA DB overwrites on divergence |
| Convergence non-termination | Low | Critical | Iteration cap (default 10); alert on hit |
| Explainability loss | High (without layered memory) | High | `FactSource` enum + PROV-O trace generation |
| Fuseki in hot path | Medium | Medium | Semantic cache preloaded; async post-reasoning |
| Multi-worker session loss | High (if in-memory) | High | Enforce Redis; startup warning |
| Port migration regressions | Medium | High | `import-linter` CI checks, feature flags, exhaustive integration tests |

---

## 🏁 16. Final Assessment

INFERRA is evolving into a genuinely novel platform — one where rules behave like software packages, semantic ontologies enrich inference silently, list iterations produce auditable aggregate conclusions, and every decision carries a full provenance chain traceable to its module, session, and fact origin.

**Three architectural commitments that must not change:**
1. **Backward-chaining** as the primary question driver — deterministic, auditable
2. **Rule DB** as the single source of truth — all other representations are projections
3. **Working memory** as the central execution state — all reasoning converges here

With the additions in this document, INFERRA becomes:
- ✅ **Composable** — rule sets as importable, versioned, reusable modules
- ✅ **Deterministic** — same inputs, same conclusions, always
- ✅ **Auditable** — every conclusion traceable to source, module, and session
- ✅ **Scalable** — incremental propagation, async RDF sync, cached modules, Redis sessions
- ✅ **Explainable** — PROV-O traces, layered fact origins, import chains, iterate progress
- ✅ **Robust** — typed ontology boundary, circular import detection, validated rule saves, hypergraph traversal
- ✅ **Enterprise-ready** — no silent failures, drift detection, versioned modules, port-based isolation

> **INFERRA is not just an inference engine.**  
> It is a platform where rules, relationships, and reasoning converge into provable, auditable, composable, intelligent decisions.

---
*Document generated for INFERRA architecture planning. Aligns with Python backend, Fuseki RDF store, AWS Graph Explorer, LLM orchestration, and Vite frontend stack. Ready for sprint planning, implementation, and stakeholder review.*