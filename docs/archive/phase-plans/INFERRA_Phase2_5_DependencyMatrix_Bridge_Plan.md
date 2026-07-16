# INFERRA Phase 2.5 Bridge Plan
## DependencyMatrix Runtime Retirement & Graph-First Migration

**Document Status:** Bridge Plan v2.7 - Phase 2.5 graph bridge implementation complete; inference, topology, iterate, import merge, rule-file persistence, deprecation boundaries, and 1k/5k/10k sparse benchmarks are graph-first and verified. The 500-VU k6 production gate is now closed under Phase 4 local-compose validation, not Phase 2.5 bridge scope.
**Placement:** Must be referenced from `INFERRA_Phase2_Implementation_Plan.md` as the formal handoff between Phase 2 and Phase 3.
**Timing:** Phase 2 is stable and complete; Phase 2.5 can begin immediately.
**Goal:** Convert INFERRA from a hybrid matrix/graph runtime to a graph-first runtime without breaking legacy rule/session compatibility.

## Implementation Status Audit - 2026-05-11

**Reconciled status:** Bridge implementation is complete for Phase 2.5. Current code is graph-first on inference, topology, iterate, import merge, and rule-file persistence paths, and the full sparse benchmark acceptance item now has committed evidence.

**Reconciled against:** current codebase, `AGENTS.md`, and `pytest --cov=src --cov-report=term-missing:skip-covered --cov-fail-under=97 -q`.

**What is implemented in code:** `FactStorePort` uses ABCMeta; `DependencyType` is an `IntFlag`; `HyperAdjacencyGraph` has `_edge_types`, a per-parent `_outgoing` index, `NodeRecord`, and runtime name/id maps; `GraphDependencyBuilder`, `GraphToMatrixAdapter`, graph serialization, and `MLTopologicalSortStrategy` exist; `TopologicalSort` is now a deprecated compatibility facade whose public BFS, DFS, and DFS-with-HistoryRecord entry points translate legacy matrix inputs into `DependencyGraphPort`, delegate traversal to `MLTopologicalSortStrategy`, and avoid runtime `node_id` calls; private dense-matrix helper algorithms have been removed from `topo_sort.py`; `MLTopologicalSortStrategy.sort_depth_first()` is iterative and handles deep 10k-style sparse DAGs without recursion-limit failures; `IterateLine` now creates iterate-local cloned subgraphs from canonical graph child names instead of manual `node_id_dictionary` state; `RuleSetScanner` now establishes the canonical graph directly; `RuleSetParser.create_dependency_matrix()` is a deprecated compatibility view over `create_dependency_graph()`; `NodeSet` exposes a canonical graph, converts legacy matrix payloads into graph state when runtime IDs are available, derives deprecated matrix views on demand, and no longer imports/stores `DependencyMatrix` as runtime state; `DependencyMatrix`, the node-level matrix shim, `NodeSet.get/set_dependency_matrix()`, and `RuleSetParser.create_dependency_matrix()` emit `DeprecationWarning`, while sanctioned graph/matrix adapters suppress internal bridge warnings; `NodeSetMerger` merges graph edges with write-time bitmask OR, qualifies imported nodes with canonical module names, preserves local raw-node overrides, rekeys imported graph edges, and guards runtime ID collisions; new and updated rule files persist an envelope containing raw rule text, graph edge-list JSON, schema metadata, and `source_hash` while legacy raw blobs still decode normally; `DynamicVectorisedDependencyMatrix` is absent from production imports; production guardrails exist for new matrix/node-id usage.

**What remains open:** No Phase 2.5 graph bridge blockers remain. Live Docker/Redis/Fuseki/Celery validation passes in the local compose environment, the 20-VU k6 smoke passes, and the strict 500-VU k6 production gate now passes under Phase 4 local-compose load criteria.

**Coverage gate:** Closed. `pytest --cov=src --cov-fail-under=97 -q` passes with 2356 passed, 65 skipped, and 97.01% total line coverage.

**Live validation evidence:** `docker compose up -d --build`, `docker compose ps`, `/api/v1/health`, internal Fuseki ping, Redis `PING`, Celery `inspect ping`, PostgreSQL readiness, `scripts/verify_phase_readiness.ps1 -SkipUnitTests -SkipFrontend`, Dockerized k6 at 20 VUs, and Dockerized k6 at 500 VUs all passed in the local compose environment.

**Completion rule:** Phase 2.5 is complete as of the 2026-05-11 sparse benchmark refresh. The 500-VU k6 result is recorded under Phase 4 readiness rather than graph bridge implementation.

---

## 1. Why Phase 2.5 Exists

Phase 2 introduced `HyperAdjacencyGraph`, `DependencyGraphPort`, `MatrixToHyperGraphAdapter`, `IncrementalPropagator`, `IterationPort`/`IterationEngine`, `RuleSetImportResolver`, `ModuleRegistry`, `SemanticCache`, `RDF_RANGE_TO_FACT_TYPE` bridge, and `NodeSetMerger`. However, the codebase still has substantial legacy `DependencyMatrix` coupling:

- `InferenceEngine` hot paths now use `DependencyGraphPort`; no direct `get_dependency_matrix()` calls remain.
- `topo_sort.py` is a deprecated compatibility facade only. Public BFS, DFS, and DFS-with-HistoryRecord entry points adapt matrix inputs into a graph and use canonical name-keyed traversal through `MLTopologicalSortStrategy`; private dense-matrix helper algorithms have been removed.
- `rule_set_scanner.py` now installs `create_dependency_graph()` directly on `NodeSet`.
- Legacy rule/session serialization still has matrix-compatible views available through `GraphToMatrixAdapter`.
- `IterateLine` now uses graph child-name traversal to clone iterate-local subgraphs; runtime `node_id_dictionary` construction has been removed from the iterate path.
- `NodeSet` stores both `node_id_dictionary: Dict[int, str]` and `stable_node_id_dictionary: Dict[str, str]`.
- `DynamicVectorisedDependencyMatrix` has been deleted.
- `FactStorePort` uses `ABCMeta`.
- Some tests still cover matrix APIs directly as compatibility boundaries.
- **`NodeSetMerger.merge()`** now merges `NodeSet` instances by copying graph edges into the merged graph and relying on write-time bitmask OR.
- **`NodeSet.add_node()` / `remove_node_by_name()`** are graph-backed compatibility methods; runtime `node_id` assignment is secondary and collision-guarded while `NodeRecord` storage keeps stable identity primary.
- **`NodeOrigin`** is formalized into `NodeRecord` storage on the graph during merge.
- **`NodeSet._merge_dependency_matrix()`** has been removed; bitmask OR lives in graph write-time merge (`add_dependency_group` with bitmask OR on `_edge_types`).

Deleting `DependencyMatrix` inside Phase 2 would create avoidable risk. Phase 2.5 provides a focused bridge: keep legacy read compatibility, but remove dense matrix usage from runtime traversal and propagation.

---

## 2. Design Decisions

### 2.1 Canonical Runtime Model

`HyperAdjacencyGraph` becomes the **canonical runtime dependency model** and the **write target** (not just a read-only view).

`DependencyMatrix` becomes a legacy compatibility format only:
- Allowed: migration adapter, legacy session/rule loading, parity tests.
- Not allowed: new propagation, new question selection, new import logic, new orchestration, new topology code.

`DynamicVectorisedDependencyMatrix` is **deleted entirely** — the graph replaces it.

### 2.2 Bitmask Composition

Bitmask composition is preserved as INFERRA's dependency model. `DependencyType` is migrated from `IntEnum` to `IntFlag`, enabling native `|`, `&`, and `in` operations.

**Write-time merge:** When `add_dependency_group("P", AND, {"A"})` is called and child "A" already exists in another group for parent "P", the graph ORs the bitmasks into the existing group and updates the `_edge_types` reverse index. This maintains the matrix's single-source-of-truth per (parent, child) edge.

**Port contract:** `DependencyGraphPort` keeps `dep_type` as raw `int` — no domain enum coupling, preserving bitmask compatibility.

### 2.3 Port Architecture

**Ports use ABCMeta by default.** Use `typing.Protocol` only for lightweight structural typing where runtime enforcement, default implementations, and explicit inheritance are not needed.

`DependencyGraphPort` stays ABCMeta and gains **default method implementations** for the matrix-compatible query API. This means any new adapter only needs to implement ~9 abstract methods and automatically gets the full matrix-compatible API.

**Specifically for this bridge:** `FactStorePort` (currently `Protocol`) is converted to `ABCMeta`.

### 2.4 Node Identity

**`node_id` (plain integer) is deprecated** in a 3-phase sequence:
- **Phase 2 (additive):** `NodeSet` gains `get_stable_node_id_dictionary()` + `get_node_by_stable_node_id()`. New graph runtime code uses canonical node-name keys while `stable_id` remains available for persistence/session lookup. `get_node_id()` becomes a deprecated alias.
- **Phase 2.5 (migrate consumers):** Engine, iterate, and topo_sort migrate from `node_id` to canonical node-name keys. `node_id` still works via `HyperAdjacencyGraph._name_to_id` mapping for GUI/adapter compatibility.
- **Phase 3+ (remove):** `node_id` field removed from `Node`; `get_node_id_dictionary()` removed from `NodeSet`; `DependencyMatrix` deleted.

**`stable_id` generation inputs** (no `line_number`):
1. `module_path` — source module/rule path
2. `rule_name` — line type (e.g. "VALUE_CONCLUSION")
3. `variable_name` — the node's variable name
4. `normalized_text` — stripped/lowered node text
5. `parent_module_path` — parent rule/module path (empty for root nodes)
6. `import_namespace` — versioned package (e.g. `common_rules@2.1.0`); empty string for local nodes

**Node key preference:** New graph-native runtime code uses canonical node-name keys. Local nodes use the raw node name; imported nodes use a qualified key such as `common_rules@2.1.0::eligibility`. `stable_id` remains a compatibility/persistence lookup value, and legacy matrix code keeps `node_id` (integer) only for row/col adapter boundaries.

### 2.5 HistoryRecord

The graph does **not** own `HistoryRecord`. ML-optimized sort is handled by a standalone `MLTopologicalSortStrategy` that takes `DependencyGraphPort` + `Dict[str, HistoryRecord]`. This keeps the graph purely structural.

### 2.6 Subgraph Extraction

`subgraph(node_names: Set[str]) -> DependencyGraphPort` preserves all edge dependency types unchanged — no type_mask filter. Filtering belongs to traversal strategies, not subgraph creation. Bitmask composition is always preserved.

### 2.7 Graph Serialization

Edge list format for persistence:
```json
[
  {"parent": "applicant_is_eligible", "child": "has_service_period", "dep_type": 72},
  {"parent": "applicant_is_eligible", "child": "has_disability", "dep_type": 8}
]
```
Simple, human-readable, easy to diff. Reconstruct `HyperAdjacencyGraph` at load time. Store alongside existing matrix during transition.

### 2.8 NodeSet Graph Source

**Graph as source of truth.** Matrix views are derived on demand via `GraphToMatrixAdapter` (the reverse of Phase 1's `MatrixToHyperGraphAdapter`). `NodeSet` no longer imports or stores `DependencyMatrix` as runtime state after graph conversion; `set_dependency_matrix()` only accepts legacy payloads, adapts them into the canonical graph when runtime IDs are available, and discards the payload.

### 2.9 Thread Safety

Not needed for Phase 2.5 — sessions are single-threaded. Add an architectural note that Phase 5+ async session pools will need per-session graph isolation or copy-on-write.

### 2.10 Import Namespace

Import namespace uses versioned package format: `common_rules@2.1.0`. Local (non-imported) nodes use `import_namespace=""`. The `RuleSetImportResolver` resolves versioned package names to specific rule texts. `NodeOrigin.module` carries the full versioned name (e.g. `"common_rules@2.1.0"`). `stable_id` generation includes `import_namespace` so the same variable imported from different versions gets different stable_ids.

### 2.11 `NodeSetMerger` Graph Migration

Phase 2's `NodeSetMerger.merge()` (Task #19) operates on `NodeSet` instances and merges dependency relationships via `_merge_dependency_matrix()` — a dense 2D matrix operation with bitmask OR on overlapping cells. Phase 2.5 migrates the merger to graph-native merge:

**Current (Phase 2):**
- Merger receives `List[NodeSet]` + local `NodeSet`.
- Nodes are merged by name (local-wins on collision).
- Dependency matrices are merged via `_merge_dependency_matrix()` which expands dense matrices and ORs overlapping cells.
- `NodeOrigin` is attached as `_origin` dynamic attribute on nodes.
- Node ordering is preserved from `get_sorted_node_list()`.

**Target (Phase 2.5):**
- Merger receives `List[HyperAdjacencyGraph]` (or `List[NodeSet]` where each exposes a canonical graph) + local graph.
- Nodes are registered on the merged `HyperAdjacencyGraph` via `register_node(name, metadata)` which stores `NodeRecord` (including `NodeOrigin` fields) — no dynamic attributes.
- Dependency edges are merged via graph's `add_dependency_group()` with write-time bitmask OR on `_edge_types` — identical semantics to `_merge_dependency_matrix()` but on the sparse graph structure.
- Node ordering derives from the merged graph's `topological_sort()`.
- `NodeSet._merge_dependency_matrix()` is deleted; `NodeSetMerger._merge_dependency_matrix()` calls are replaced by graph-level merge.
- The merger's fact/input dictionary merge stays at `NodeSet` level — these are not graph concerns.

**Transition path:** Completed for runtime. `NodeSetMerger.merge()` now uses graph-level edge merge and no longer falls back to dense matrix merge.

### 2.12 `NodeOrigin` Formalization

Phase 2 attaches `NodeOrigin` to merged nodes as a dynamic `_origin` attribute. Phase 2.5 formalizes this into `NodeRecord` storage on the graph:

**`NodeRecord`** gains fields that subsume `NodeOrigin`:
```python
@dataclass(frozen=True)
class NodeRecord:
    name: str
    stable_id: str
    runtime_id: int
    module: str
    import_namespace: str = ""       # e.g. "common_rules@2.1.0"
    import_version: str = ""          # e.g. "2.1.0"
    imported: bool = False            # True if node came from an imported module
    import_depth: int = 0             # 0 = local, 1 = directly imported, etc.
```

The `imported` and `import_depth` fields replace `NodeOrigin.imported` and `NodeOrigin.depth`. The `NodeOrigin` class is retained as a convenience factory for constructing `NodeRecord` metadata, but the graph's `NodeRecord` is the canonical storage.

**Migration:** `Node._origin` dynamic attribute is deprecated. Code that reads `node._origin` migrates to `graph.get_node_record(node_name)`. The `NodeSetMerger` stops setting `node._origin` and instead registers `NodeRecord` on the graph during merge.

---

## 3. Scope

### 3.1 Runtime Graph-First Refactor

- Refactor `InferenceEngine` internals to depend on `DependencyGraphPort` for parent lookup, child groups, topological order, and impacted traversal.
- Keep matrix access behind a legacy adapter boundary.
- Add a guardrail test that fails when hot-path inference methods call `get_dependency_matrix()`.
- Replace all `node.get_node_id()` calls with `node.get_stable_node_id()` or `node.get_node_name()` in engine hot paths.

### 3.2 Parser and NodeSet Bridge

- Extend `NodeSet` to expose a canonical `DependencyGraphPort`/`HyperAdjacencyGraph`.
- Keep `set_dependency_matrix()` and `get_dependency_matrix()` for old tests and legacy serialized rules.
- Create `GraphDependencyBuilder` that writes to `HyperAdjacencyGraph` directly during scanning, replacing `DependencyBuilder` → `DynamicVectorisedDependencyMatrix` → `DependencyMatrix` pipeline.
- `GraphDependencyBuilder` maintains an internal `id→name` mapping during the write phase: the parser's integer-based flow is preserved as a convenience, with the graph converting to name-based storage.
- Preserve deterministic node naming: graph node IDs are node names.
- **Migrate `NodeSetMerger`** from `_merge_dependency_matrix()` (dense 2D matrix merge) to graph-native merge via `add_dependency_group()` with write-time bitmask OR.
- **Migrate `NodeSet.add_node()`** from runtime `node_id` assignment to `stable_id`-first registration on the graph's `NodeRecord`. The `add_node()` method (added in Phase 2) becomes a thin wrapper that delegates to `graph.register_node(name, metadata)`.
- **Migrate `NodeSet.remove_node_by_name()`** (added in Phase 2) to also remove the node from the graph's `_nodes` and `_edge_types` indices.
- **Migrate `NodeSet.rebuild_dependency_groups()`** (added in Phase 2) to reconstruct graph edges from node dependency metadata instead of rebuilding a dense matrix.
- Delete `NodeSet._merge_dependency_matrix()` once graph-native merge is the only path.
- **Formalize `NodeOrigin`**: Replace `node._origin` dynamic attribute with `NodeRecord` storage on the graph (see §2.12). The merger registers `NodeRecord` entries instead of setting `_origin`.

### 3.3 Persistence Compatibility

- Continue reading old dense matrix payloads.
- Write new graph edge-list payloads for new/updated rule sets.
- Store graph schema version and source hash alongside persisted graph data.
- Provide a one-way migration path from dense matrix to graph edge list.
- Create `GraphToMatrixAdapter` for on-demand matrix derivation (reverse of `MatrixToHyperGraphAdapter`).

### 3.4 Topological Sort Migration

- Move runtime topological sorting to `HyperAdjacencyGraph.topological_sort()` or graphlib-backed graph helpers.
- Create `MLTopologicalSortStrategy` — standalone class that takes `DependencyGraphPort` + `Dict[str, HistoryRecord]` and produces ML-optimized traversal order. Separated from the graph to keep it purely structural.
- Keep matrix-based topological sort as legacy only.
- Preserve `dfs_topological_sort_with_record()` behavior for `ML_OPTIMIZED_DFS=true` until the graph-native `MLTopologicalSortStrategy` is proven by regression tests.

### 3.5 Test Migration

- Add graph-first tests for all runtime behavior.
- Keep matrix-vs-graph parity tests (golden tests comparing output of both backends on representative rule sets).
- Reduce new direct matrix mocks in inference tests.
- Add performance benchmarks for 1k, 5k, and 10k sparse rule graphs.

### 3.6 Port Contract Normalization

- Convert `FactStorePort` from `typing.Protocol` to `ABCMeta` — the only remaining Protocol-based port.
- Add default method implementations to `DependencyGraphPort` for the matrix-compatible query API (see §4.1).
- Keep contract tests for every port implementation.
- Add an import/style guard so new ports cannot be introduced as Protocols without justification.

### 3.7 `node_id` Deprecation

- Migrate `IterateLine` from integer `node_id` matrix row indexing to canonical node-name-keyed graph subgraph extraction.
- Migrate `InferenceEngine` from `node.get_node_id()` to graph-name keys in all hot-path methods.
- Mark `Node.get_node_id()`, `Node.set_node_id()`, `NodeSet.get_node_id_dictionary()`, `NodeSet.get_node_by_node_id()` as deprecated with `warnings.warn(DeprecationWarning)`.
- Keep `NodeSet.get_stable_node_id_dictionary()` + `NodeSet.get_node_by_stable_node_id()` as compatibility/persistence lookup APIs.
- Full removal of `node_id` field from `Node` deferred to Phase 3+.

### 3.8 `DynamicVectorisedDependencyMatrix` Deletion

- Delete `src/domain/nodes/dynamic_vectorised_dependency_matrix.py` entirely.
- Remove all imports and references.
- `GraphDependencyBuilder` (§3.2) replaces its role in the parser pipeline.

---

## 4. Technical Deep Dives

### 4.1 `HyperAdjacencyGraph` Augmentation

The graph gains three internal indices for O(1) lookups and explicit node storage:

```python
class HyperAdjacencyGraph(DependencyGraphPort):
    def __init__(self) -> None:
        # Existing
        self._children: Dict[str, Tuple[DependencyGroup, ...]] = {}
        self._parents: Dict[str, Set[str]] = {}
        self._topo_cache: Optional[Tuple[str, ...]] = None

        # New indices
        self._edge_types: Dict[Tuple[str, str], int] = {}   # (parent, child) → dep_type bitmask
        self._nodes: Dict[str, NodeRecord] = {}               # name → node metadata
        self._name_to_id: Dict[str, int] = {}                # name → runtime integer ID
        self._id_to_name: Dict[int, str] = {}                 # runtime ID → name
```

**`NodeRecord`** — explicit node storage (subsumes `NodeOrigin` fields from Phase 2):

```python
@dataclass(frozen=True)
class NodeRecord:
    name: str
    stable_id: str
    runtime_id: int
    module: str
    import_namespace: str = ""       # e.g. "common_rules@2.1.0"
    import_version: str = ""         # e.g. "2.1.0"
    imported: bool = False           # True if node came from an imported module (was NodeOrigin.imported)
    import_depth: int = 0            # 0 = local, 1 = directly imported, etc. (was NodeOrigin.depth)
```

The `imported` and `import_depth` fields replace Phase 2's `NodeOrigin.imported` and `NodeOrigin.depth`. The `NodeOrigin` class is retained as a convenience factory for constructing `NodeRecord` metadata during merge, but `NodeRecord` is the canonical storage. Code that reads `node._origin` migrates to `graph.get_node_record(node_name)`.

**Write-time bitmask merge:** When `add_dependency_group("P", AND, {"A"})` is called and child "A" already exists in another group for parent "P" with `MANDATORY|AND`, the graph ORs the bitmasks (`AND | MANDATORY|AND = MANDATORY|AND`), merges the child into the existing group, and updates `_edge_types[("P", "A")]` to the composed value.

### 4.2 `DependencyGraphPort` Default Methods

New abstract methods added to the port:

```python
@abstractmethod
def register_node(self, name: str, metadata: Optional[dict] = None) -> int: ...
@abstractmethod
def edges(self) -> Iterator[Tuple[str, str, int]]: ...
```

Default method implementations (inherited by all adapters):

```python
def get_children_by_type(self, node_name: str, type_mask: int) -> Tuple[str, ...]:
    """Return children matching a bitmask filter."""
    result = []
    for dep_type, children in self.get_child_groups(node_name):
        if dep_type & type_mask == type_mask:
            result.extend(children)
    return tuple(result)

def get_children_flat(self, node_name: str) -> Tuple[str, ...]:
    """Return all children as a flat tuple (regardless of type)."""
    result = []
    for _, children in self.get_child_groups(node_name):
        result.extend(children)
    return tuple(result)

def get_dependency_type(self, parent: str, child: str) -> int:
    """Return dep_type bitmask for a specific edge. Default: O(groups) scan."""
    for dep_type, children in self.get_child_groups(parent):
        if child in children:
            return dep_type
    return -1

def has_children_of_type(self, node_name: str, type_mask: int) -> bool:
    """Check if node has any children matching a bitmask."""
    return len(self.get_children_by_type(node_name, type_mask)) > 0

def subgraph(self, node_names: Set[str]) -> 'DependencyGraphPort':
    """Extract induced subgraph preserving all dependency types."""
    result = self.__class__()
    for name in node_names:
        if self.has_node(name):
            for dep_type, children in self.get_child_groups(name):
                in_sub = {c for c in children if c in node_names}
                if in_sub:
                    result.add_dependency_group(name, dep_type, in_sub)
    return result

def lookup_by_id(self, runtime_id: int) -> Optional[str]:
    """Look up node name by runtime integer ID. Default: not supported."""
    return None

def lookup_by_name(self, name: str) -> Optional[int]:
    """Look up runtime integer ID by node name. Default: not supported."""
    return None
```

`HyperAdjacencyGraph` overrides hot-path defaults with O(1) implementations:

```python
def get_dependency_type(self, parent: str, child: str) -> int:
    return self._edge_types.get((parent, child), -1)

def lookup_by_id(self, runtime_id: int) -> Optional[str]:
    return self._id_to_name.get(runtime_id)

def lookup_by_name(self, name: str) -> Optional[int]:
    return self._name_to_id.get(name)

def has_children_of_type(self, node_name: str, type_mask: int) -> bool:
    for group in self._children.get(node_name, ()):
        if int(group.dep_type) & type_mask == type_mask:
            return True
    return False
```

### 4.3 `DependencyType` Migration: `IntEnum` → `IntFlag`

The `src/domain/graph/dependency_type.py` enum is migrated from `IntEnum` to `IntFlag`:

```python
from enum import IntFlag

class DependencyType(IntFlag):
    MANDATORY = 64
    OPTIONAL = 32
    POSSIBLE = 16
    AND = 8
    OR = 4
    NOT = 2
    KNOWN = 1
```

This enables native bitmask operations:
- `DependencyType.MANDATORY | DependencyType.AND` → `DependencyType.MANDATORY|AND` (value 72)
- `DependencyType.AND in (DependencyType.MANDATORY | DependencyType.AND)` → `True`
- `72 & DependencyType.AND == DependencyType.AND` → `True`

**Port contract unchanged:** `dep_type` parameter in `DependencyGraphPort` stays `int`. The `IntFlag` is a domain-level convenience only.

**Backward compatibility:** `DependencyType.AND.value` still returns `8`. `int(DependencyType.MANDATORY | DependencyType.AND)` still returns `72`. Existing code using `.value` or `int()` comparisons continues to work.

### 4.4 `MLTopologicalSortStrategy`

Standalone class that accepts `DependencyGraphPort` + `Dict[str, HistoryRecord]`:

```python
class MLTopologicalSortStrategy:
    """ML-optimized topological sort using HistoryRecord data.

    sort() preserves topological validity and reorders newly available
    nodes using the dependency type that released them.

    sort_depth_first() preserves the legacy DFS optimization:
    parent first, then recursively visit OR children by highest true_rate
    and AND children by highest false_rate.
    """

    def __init__(self, graph: DependencyGraphPort):
        self._graph = graph

    def sort(self, records: Dict[str, HistoryRecord]) -> Tuple[str, ...]:
        ...

    def sort_depth_first(self, records: Dict[str, HistoryRecord]) -> Tuple[str, ...]:
        ...
```

**Key design:** The strategy does NOT call `node.get_node_id()`. It uses `graph.get_child_groups()` (primitive port API) for type-separated traversal. Record keys are canonical node-name graph keys, not runtime integers or stable IDs. Prefix compatibility for `not`, `known`, and `not known` HistoryRecord keys is preserved.

**Future hardening:** A structured record key can still replace prefix-compatible string keys later if collisions become a real issue. That should be a separate persistence migration rather than part of this runtime bridge.

### 4.5 `GraphDependencyBuilder`

Replaces `DependencyBuilder` → `DynamicVectorisedDependencyMatrix` → `DependencyMatrix` pipeline. Writes to `HyperAdjacencyGraph` directly:

```python
class GraphDependencyBuilder:
    """Builds a HyperAdjacencyGraph during rule scanning.

    Maintains an internal id→name mapping so the parser's integer-based
    flow continues to work. The graph converts to name-based storage.
    """

    def __init__(self, graph: HyperAdjacencyGraph):
        self._graph = graph
        self._id_to_name: Dict[int, str] = {}
        self._name_to_id: Dict[str, int] = {}
        self._next_id: int = 0

    def add_dependency(self, parent_id: int, child_id: int, dep_type: int) -> None:
        parent_name = self._id_to_name.get(parent_id, f"__node_{parent_id}__")
        child_name = self._id_to_name.get(child_id, f"__node_{child_id}__")
        # Bitmask merge: if edge already exists, OR the bitmasks
        existing = self._graph._edge_types.get((parent_name, child_name))
        if existing is not None:
            merged = existing | dep_type
            if merged != existing:
                self._graph.remove_dependency_group(parent_name, existing, {child_name})
                self._graph.add_dependency_group(parent_name, merged, {child_name})
        else:
            self._graph.add_dependency_group(parent_name, dep_type, {child_name})

    def register_node(self, node_id: int, name: str) -> None:
        self._id_to_name[node_id] = name
        self._name_to_id[name] = node_id
        self._graph.register_node(name)
```

### 4.6 GUI Query API

The graph's `NodeRecord` storage and bidirectional mapping support the INFERRA GUI requirement for rule name/variable/question retrieval by ID:

| Method | Returns | Use case |
|--------|---------|-----------|
| `lookup_by_id(runtime_id: int) → Optional[str]` | Node name from runtime integer ID | Legacy matrix-to-GUI bridge |
| `lookup_by_name(name: str) → Optional[int]` | Runtime ID from node name | GUI to matrix index |
| `get_node_record(name: str) → Optional[NodeRecord]` | Full metadata (stable_id, module, import_namespace) | GUI detail panels, provenance display |
| `find_nodes_by_module(module: str) → List[NodeRecord]` | All nodes from a given module | Module-level browsing |
| `find_nodes_by_namespace(namespace: str) → List[NodeRecord]` | All nodes from an import namespace | Import dependency browsing |

### 4.7 `GraphToMatrixAdapter`

Reverse of Phase 1's `MatrixToHyperGraphAdapter`. Derives a `DependencyMatrix` on demand from the canonical `HyperAdjacencyGraph`:

```python
class GraphToMatrixAdapter(DependencyMatrix):
    """Derives a DependencyMatrix from a HyperAdjacencyGraph on demand.

    Used during transition for legacy consumers that still require
    matrix access (e.g., old tests, legacy session loading).
    The matrix is NOT stored — it is reconstructed each time.
    """

    def __init__(self, graph: HyperAdjacencyGraph):
        self._graph = graph
        self._matrix_cache: Optional[List[List[int]]] = None
        self._id_map: Optional[Dict[int, str]] = None

    def _rebuild(self) -> None:
        """Reconstruct the N×N matrix from the graph's adjacency data."""
        ...

    def get_dependency_two_dimension_list(self) -> List[List[int]]:
        self._rebuild()
        return self._matrix_cache

    def get_node_id_dictionary(self) -> Dict[int, str]:
        self._rebuild()
        return self._id_map
```

### 4.8 `NodeSetMerger` Graph Migration

Phase 2's `NodeSetMerger` merges at the `NodeSet`/`DependencyMatrix` level. Phase 2.5 migrates it to merge at the `HyperAdjacencyGraph` level:

**Current merge flow (Phase 2):**
```
NodeSetMerger.merge(local_ns, [imported_ns_1, imported_ns_2])
  ├── Phase 1: Add imported nodes via NodeSet.add_node() (name dedup)
  ├── Phase 2: Add local nodes via NodeSet.add_node() (local-wins override)
  ├── Merge dependency matrices via NodeSet._merge_dependency_matrix()  ← DENSE MATRIX
  ├── Merge fact/input dictionaries
  └── Attach NodeOrigin via node._origin = NodeOrigin(...)
```

**Target merge flow (Phase 2.5):**
```
NodeSetMerger.merge(local_ns, [imported_ns_1, imported_ns_2])
  ├── Build merged HyperAdjacencyGraph from local + imported graphs
  │   ├── Register imported nodes via graph.register_node(name, NodeRecord(...))
  │   ├── Register local nodes (local-wins: overwrite on name collision)
  │   ├── Merge edges via graph.add_dependency_group() with write-time bitmask OR
  │   └── Node ordering from merged graph.topological_sort()
  ├── Assign merged graph to NodeSet via ns.set_graph(merged_graph)
  ├── Derive legacy matrix on demand via GraphToMatrixAdapter (for transition)
  ├── Merge fact/input dictionaries (unchanged — not a graph concern)
  └── NodeOrigin data stored in NodeRecord on graph (no dynamic _origin)
```

**Bitmask OR equivalence guarantee:** The Phase 2 `_merge_dependency_matrix()` ORs overlapping cells in the dense matrix. The Phase 2.5 `add_dependency_group()` with write-time merge ORs bitmasks on `_edge_types[(parent, child)]`. These produce identical results. A parity test must confirm:

```python
# For every (parent, child) pair in the merged output:
#   matrix_merge_result[parent_id][child_id]
#   == graph_merge_result._edge_types[(parent_name, child_name)]
```

**Transition strategy:** Completed for runtime. The public `merge()` method now copies edges from input graphs into the merged graph; dense matrix fallback has been removed.

### 4.9 `NodeOrigin` → `NodeRecord` Migration

Phase 2 sets `NodeOrigin` as a dynamic attribute (`node._origin`) during merge. Phase 2.5 stores this data in the graph's `NodeRecord`:

```python
# Phase 2 (current):
node._origin = NodeOrigin(module="common_rules", imported=True, depth=1)

# Phase 2.5 (target):
graph.register_node(
    name=node.get_node_name(),
    metadata=NodeRecord(
        name=node.get_node_name(),
        stable_id=node.get_stable_node_id(),
        runtime_id=node.get_node_id(),
        module="common_rules",
        import_namespace="common_rules@2.1.0",
        import_version="2.1.0",
        imported=True,
        import_depth=1,
    )
)
```

**Query migration:**
```python
# Phase 2 (current):
origin = node._origin
if origin.imported and origin.depth > 1: ...

# Phase 2.5 (target):
record = graph.get_node_record(node_name)
if record.imported and record.import_depth > 1: ...
```

**Backward compatibility:** During transition, `Node._origin` is kept as a read-only property that delegates to `graph.get_node_record(self.get_node_name())`. Once all consumers are migrated, the `_origin` attribute is removed.

---

## 5. Work Breakdown

| WS | Task | Acceptance Gate |
|----|------|-----------------|
| WS-1 Runtime | Replace `InferenceEngine` hot-path matrix calls with `DependencyGraphPort` calls; replace `node.get_node_id()` with canonical node-name keys | No hot-path direct `get_dependency_matrix()` or `get_node_id()` calls |
| WS-2 Parser | Create `GraphDependencyBuilder`; update `RuleSetScanner`/`NodeSet` to emit canonical `HyperAdjacencyGraph`; migrate `NodeSetMerger` from `_merge_dependency_matrix()` to graph-native merge via `add_dependency_group()` with write-time bitmask OR; formalize `NodeOrigin` into `NodeRecord` on graph; migrate `NodeSet.add_node()` / `remove_node_by_name()` / `rebuild_dependency_groups()` to graph-backed implementations | New parses expose a canonical graph; `NodeSetMerger` uses graph-native merge; `DynamicVectorisedDependencyMatrix` deleted; `NodeOrigin` stored in `NodeRecord` not `_origin` |
| WS-3 Persistence | Add graph edge-list serialization; create `GraphToMatrixAdapter`; persist rule-file graph envelopes | Old matrix-backed data still loads; new and updated rule files write graph edge-list format with schema metadata and `source_hash` |
| WS-4 Topology | Create `MLTopologicalSortStrategy`; migrate runtime topo sort to graph-native | Matrix topo sort is legacy only; ML sort produces equivalent output on regression tests |
| WS-5 Tests | Add parity, graph-first, and performance tests (1k/5k/10k sparse graphs); add `NodeSetMerger` matrix-vs-graph parity test confirming bitmask OR equivalence | Matrix and graph results match on representative rule sets |
| WS-6 Guardrails | Add import-linter or test-level boundary checks for `DependencyMatrix` and `node_id` usage | New production code cannot depend on `DependencyMatrix` or `node_id` (integer) |
| WS-7 Ports | Convert `FactStorePort` to ABCMeta; add default methods to `DependencyGraphPort` | No production port uses `typing.Protocol` without justification; all ports have contract tests |
| WS-8 Node Identity | Migrate `IterateLine` from `node_id` to canonical node-name-keyed graph subgraph extraction; deprecate `node_id` APIs with `DeprecationWarning`; remove `Node._origin` dynamic attribute in favor of `NodeRecord` | No hot-path `node_id` (integer) usage; canonical node-name key is primary runtime key; no `node._origin` reads |

**Execution order:** WS-6 → WS-7 → WS-2 → WS-1 → WS-4 → WS-8 → WS-3 → WS-5

Guardrails and port improvements come first because they define the boundary. Then the parser writes to the graph. Then consumers migrate. IterateLine migration (WS-8) comes after runtime refactor (WS-1) because iterate depends on the engine's graph-based traversal. Persistence (WS-3) and final tests (WS-5) come last.

---

## 6. Acceptance Criteria

- [x] `InferenceEngine` runtime traversal and propagation use `DependencyGraphPort`.
- [x] `DependencyMatrix` is not used by hot-path inference, propagation, question selection, topology, or iterate runtime paths.
- [x] `DynamicVectorisedDependencyMatrix` is deleted from production code.
- [x] Parser/scanner can emit `HyperAdjacencyGraph` directly for new rule sets via `GraphDependencyBuilder`.
- [x] Legacy dense matrix payloads still load through `MatrixToHyperGraphAdapter`.
- [x] New rule persistence writes graph-native edge-list data with schema version. New and updated rule files persist graph envelopes containing raw rule text, graph JSON, schema metadata, and `source_hash`; legacy raw blobs still decode normally.
- [x] `GraphToMatrixAdapter` derives matrix on demand from the canonical graph.
- [x] `dfs_topological_sort_with_record()` is preserved as a graph-backed compatibility entry point; `MLTopologicalSortStrategy.sort_depth_first()` now owns the legacy DFS-with-HistoryRecord path optimization with regression tests.
- [x] 1k/5k/10k sparse graph benchmarks are captured and compared against matrix baseline. Evidence: `benchmarks/baseline_phase2_5_sparse.json` and `tests/benchmarks/test_phase2_5_sparse_graph_benchmarks.py`; 1k materializes the legacy matrix for adapter parity, while 5k/10k compare graph edge counts against dense matrix cell-count and memory projections.
- [x] Matrix imports are limited to adapter, legacy migration shims, and tests. Guardrails prevent parser/NodeSet/scanner regressions.
- [x] All production ports use ABCMeta; `FactStorePort` converted from Protocol.
- [x] `DependencyGraphPort` has default method implementations for matrix-compatible API (`get_children_by_type`, `get_dependency_type`, `subgraph`, etc.).
- [x] `HyperAdjacencyGraph` has `_edge_types` reverse index for O(1) per-edge dep_type lookup.
- [x] `HyperAdjacencyGraph` has `_nodes: Dict[str, NodeRecord]` for explicit node storage.
- [x] `HyperAdjacencyGraph` has `_name_to_id` / `_id_to_name` bidirectional mapping for GUI queries.
- [x] `DependencyType` uses `IntFlag` (not `IntEnum`); port keeps `dep_type` as raw `int`.
- [x] Bitmask composition is preserved; write-time merge ORs bitmasks for same (parent, child) pair.
- [x] `subgraph()` preserves all edge dependency types unchanged; no type_mask filter.
- [~] Node key preference: canonical node-name key primary, `stable_id` compatibility/persistence only, `node_id` (integer) legacy adapter only. Deprecated integer APIs remain for compatibility tests.
- [x] `node_id` (plain integer) deprecated with `DeprecationWarning`; hot-path topology and iterate usage replaced with canonical node names.
- [x] `IterateLine` uses graph-native subgraph extraction instead of matrix row/col slicing.
- [~] Import namespace uses versioned package format (`common_rules@2.1.0`); local nodes use empty string. `NodeRecord` fields exist; resolver/version validation needs live import coverage.
- [x] Documentation marks `DependencyMatrix` and `node_id` as deprecated for runtime use.
- [x] **`NodeSetMerger`** uses graph-native merge via `add_dependency_group()` with write-time bitmask OR instead of `_merge_dependency_matrix()` dense matrix merge.
- [x] **`NodeSetMerger`** parity test confirms bitmask OR equivalence.
- [x] **`NodeOrigin`** is stored in `NodeRecord` on the graph (`NodeRecord.imported`, `NodeRecord.import_depth`), not as a dynamic `node._origin` attribute.
- [x] **`NodeSet.add_node()`** delegates to `graph.register_node()` for `NodeRecord` storage; runtime `node_id` assignment is secondary/legacy.
- [x] **`NodeSet._merge_dependency_matrix()`** is deleted; all callers use graph-native merge.
- [x] **`NodeSet.rebuild_dependency_groups()`** reconstructs graph edges instead of dense matrix.

---

## 7. Handoff to Phase 3

Phase 3 should start only after Phase 2.5 confirms the graph-first runtime is stable. Phase 3's `BackwardChainOrchestrator`, `SessionManager`, convergence hashing, ontology deltas, and PROV-O trace generation should depend on `DependencyGraphPort`, not on `DependencyMatrix` or numeric matrix node IDs.

If Phase 3 must begin before Phase 2.5 is complete, it must use a `LegacyOrchestrator` fallback and treat graph-first migration as a blocking hardening item before production deployment.

---

## 8. `node_id` Deprecation Roadmap

| Phase | Action | Impact | Risk |
|-------|--------|--------|------|
| **Phase 2** (historical) | Add `stable_id` generation with new inputs; `NodeSet.get_stable_node_id_dictionary()`; new graph runtime code uses canonical node-name keys; `get_node_id()` deprecated but functional; `NodeSetMerger` merges via `_merge_dependency_matrix()` with bitmask OR; `NodeOrigin` set as `node._origin` dynamic attribute; `NodeSet.add_node()` / `remove_node_by_name()` / `rebuild_dependency_groups()` added | Additive only | Low |
| **Phase 2.5** (bridge) | Migrate engine, iterate, topo_sort from `node_id` to canonical node-name keys; `DeprecationWarning` on `get_node_id()`; graph is primary; matrix derived on demand; `NodeSetMerger` migrates from `_merge_dependency_matrix()` to graph-native merge; imported nodes use canonical qualified names; rule-file writes persist graph edge-list envelopes; `NodeOrigin` moves from `node._origin` to `NodeRecord` on graph; `NodeSet.add_node()` delegates to `graph.register_node()`; `NodeSet._merge_dependency_matrix()` deleted; `NodeSet.rebuild_dependency_groups()` reconstructs graph edges | Complete; sparse benchmark acceptance captured | Low |
| **Phase 3+** | Remove `node_id` field from `Node`; remove `get_node_id_dictionary()` from `NodeSet`; delete `DependencyMatrix`; remove `node._origin` property wrapper; all provenance reads go through `graph.get_node_record()` | Full removal | Low (once all consumers migrated) |

---

## 9. Phase 2.5 Bridge Handoff Inventory — Remaining Matrix Dependencies

Audited 2026-05-04; refreshed 2026-05-11. Phase 2 is **complete** (all 29 tasks done; Task #8 was completed through Phase 2.5), and Phase 2.5 graph bridge implementation is now complete. This inventory catalogs all remaining direct `DependencyMatrix` / `DynamicVectorisedDependencyMatrix` / `DependencyBuilder` dependencies in the codebase. Phase 2 production code does NOT directly depend on `DependencyMatrix` (only `matrix_to_hyper_adapter.py` is the sanctioned adapter). Performance baselines captured in `benchmarks/baseline_phase2.json` and `benchmarks/baseline_phase2_5_sparse.json`.

### 9.1 Source Code: `DependencyMatrix` Direct Imports

| # | File | Lines | Usage | Owner (P2.5 WS) | Risk | Migration Target |
|---|------|-------|-------|-----------------|------|-------------------|
| 1 | `src/domain/nodes/node_set.py` | No direct matrix import | Graph is source of truth; `get_dependency_matrix()` derives a compatibility view through `GraphToMatrixAdapter`; `set_dependency_matrix()` adapts legacy payloads through `MatrixToHyperGraphAdapter` | WS-2 (NodeSet dual storage) | **Closed for runtime** | Compatibility APIs retained at adapter boundary |
| 2 | `src/domain/nodes/iterate_line.py` | No direct matrix import | Iterate-local clone graph is built from `DependencyGraphPort.get_children_flat()` / `get_dependency_type()` and canonical node names; manual `node_id_dictionary` state removed | WS-8 (IterateLine) | **Closed for runtime** | Guardrail prevents runtime node-id dictionary regression |
| 3 | `src/domain/graph/matrix_to_hyper_adapter.py` | 16 | Adapter: converts `DependencyMatrix` → `HyperAdjacencyGraph` | WS-6 (adapter, keep) | **Low** — sanctioned bridge | Retained as legacy migration path |
| 4 | `src/domain/rule_parser/rule_set_parser.py` | No direct matrix import | `create_dependency_graph()` builds graph first; `create_dependency_matrix()` derives a compatibility view from the graph | WS-7 (parser pipeline) | **Closed for runtime** | `GraphDependencyBuilder` emits graph directly |
| 5 | `src/domain/rule_parser/i_scan_feeder.py` | No direct matrix import | `create_dependency_graph()` is the graph-first API and returns the `NodeSet` graph; legacy `create_dependency_matrix()` remains only as an abstract compatibility method | WS-7 (parser pipeline) | **Closed for runtime** | Graph-first feeder API |

### 9.2 Source Code: `DependencyBuilder` + `DynamicVectorisedDependencyMatrix`

| # | File | Lines | Usage | Owner (P2.5 WS) | Risk | Migration Target |
|---|------|-------|-------|-----------------|------|-------------------|
| 6 | `src/domain/nodes/dependency_builder.py` | File removed | Legacy builder removed from production source | WS-7 (parser pipeline) | **Closed** | `GraphDependencyBuilder` |
| 7 | `src/domain/nodes/dynamic_vectorised_dependency_matrix.py` | File removed | NumPy-based intermediate matrix deleted | WS-8 (delete) | **Closed** | Graph replaces it |
| 8 | `src/domain/rule_parser/rule_set_parser.py` | `GraphDependencyBuilder` import only | Parser graph builder replaces legacy builder/matrix pipeline | WS-7 (parser pipeline) | **Closed** | `GraphDependencyBuilder` |
| 9 | `src/domain/nodes/node_set.py` | No `DependencyBuilder` import | `rebuild_dependency_groups()` reconstructs graph edges from node metadata | WS-2 (NodeSet) | **Closed** | Graph-native rebuild |

### 9.3 Source Code: Matrix API Consumers (Hot Path)

| # | File | `get_dependency_matrix()` Calls | Usage | Owner (P2.5 WS) | Risk |
|---|------|-------------------------------|-------|-----------------|------|
| 10 | `src/domain/inference/inference_engine.py` | ~15 call sites (144, 250–251, 438–442, 671–675, 751, 770–771, 787, 814, 843) | Hot-path traversal: parent/child deps, dependency type checks, iterate child lists | WS-1 (InferenceEngine) | **Critical** |
| 11 | `src/domain/inference/topo_sort.py` | Deprecated public facade only | Public BFS/DFS/ML topo sort adapts legacy matrices into graph traversal; dense helper methods removed | WS-6 (topo sort) | **Closed for runtime** |
| 12 | `src/domain/rule_parser/rule_set_scanner.py` | None | `establish_node_set()` calls `create_dependency_graph()` and `set_graph()` directly | WS-7 (parser pipeline) | **Closed for runtime** |
| 13 | `src/domain/rule_parser/node_set_merger.py` | None | Graph-native merge via `add_dependency_group()` with write-time bitmask OR | WS-2 (NodeSetMerger graph migration) | **Closed** |

### 9.4 Test Code: Matrix References

| # | File | Approx Refs | Notes |
|---|------|-------------|-------|
| 14 | `tests/domain/nodes/test_iterate_line_coverage.py` | Compatibility mocks only | Graph-native iterate subgraph tests plus legacy API coverage |
| 15 | `tests/domain/inference/test_inference_engine.py` | ~5 | `get_dependency_matrix.return_value` |
| 16 | `tests/domain/nodes/test_node_set.py` | ~10 | `set/get_dependency_matrix`, `MagicMock(spec=DependencyMatrix)` |
| 17 | `tests/domain/rule_parser/test_node_set_merger.py` | ~8 | `DependencyMatrix` construction, `_merge_dependency_matrix` parity |
| 18 | `tests/domain/nodes/test_dependency_matrix.py` | ~7 | Direct `DependencyMatrix` unit tests |
| 19 | `tests/domain/nodes/test_dynamic_vectorised_dependency_matrix.py` | File removed | Deleted with class |
| 20 | `tests/domain/inference/test_topo_sort.py` | 0 private matrix helpers | Public compatibility facade only |
| 21 | `tests/domain/graph/test_hyper_adjacency_graph.py` | ~3 | `MatrixToHyperGraphAdapter` parity tests |
| 22 | `tests/domain/rule_parser/test_rule_set_parser.py` | ~3 | `create_dependency_matrix` |
| 23 | `tests/domain/rule_parser/test_rule_set_scanner.py` | ~2 | `DependencyMatrix([[]])` in mock feeder |
| 24 | `tests/domain/nodes/test_iterate_context.py` | ~1 | `get_dependency_matrix.return_value` |
| 25 | `tests/services/test_rule_service.py` | ~1 | `get_dependency_two_dimension_list.return_value` |
| 26 | `tests/domain/nodes/test_node_identity.py` | ~3 | `create_dependency_matrix` in identity test |
| 27 | `tests/integration/test_phase1_acceptance_gaps.py` | ~5 | `set_dependency_matrix`, `DependencyMatrix` construction |

**Total test refs: ~71** (down from earlier estimate of ~327 — Phase 2 `node_id` deprecation already reduced many)

### 9.5 Phase 2 Production Code: No Direct Matrix Dependency

Verified: all Phase 2 production modules (`src/domain/imports/`, `src/domain/graph/inference_propagator.py`, `src/domain/state/`, `src/adapters/inbound/http/routes/`, `src/tasks/`) use `DependencyGraphPort` or are matrix-agnostic. The only sanctioned bridge is `matrix_to_hyper_adapter.py`.

### 9.6 Migration Priority (WS ordering)

1. **WS-6** — Keep `MatrixToHyperGraphAdapter` + add `GraphToMatrixAdapter`; graphlib topo sort
2. **WS-7** — Parser pipeline graph-first migration is closed; `GraphDependencyBuilder` replaces `DependencyBuilder` → `DynamicVectorisedDependencyMatrix` → `DependencyMatrix`
3. **WS-2** — `NodeSet` graph-as-source-of-truth and `NodeSetMerger` graph migration are closed for runtime; compatibility views remain at adapter boundaries
4. **WS-1** — `InferenceEngine` hot-path traversal → `DependencyGraphPort`
5. **WS-4** — `NodeOrigin` → `NodeRecord` on graph
6. **WS-8** — `IterateLine` graph-native subgraph and `DynamicVectorisedDependencyMatrix` deletion are closed; keep regression guardrails active
7. **WS-3/WS-5** — Test migration; `FactStorePort` → ABCMeta; `topo_sort.py` cleanup
