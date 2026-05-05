# INFERRA Phase 2.5 Bridge Plan
## DependencyMatrix Runtime Retirement & Graph-First Migration

**Document Status:** Bridge Plan v2.2 — Phase 2 complete (all 29 tasks done; Task #8 deferred to Phase 2.5). Updated to reflect Phase 2 final deliverables including performance baselines (`baseline_phase2.json`) and feature flag matrix tests.  
**Placement:** Must be referenced from `INFERRA_Phase2_Implementation_Plan.md` as the formal handoff between Phase 2 and Phase 3.  
**Timing:** Phase 2 is stable and complete; Phase 2.5 can begin immediately.  
**Goal:** Convert INFERRA from a hybrid matrix/graph runtime to a graph-first runtime without breaking legacy rule/session compatibility.

---

## 1. Why Phase 2.5 Exists

Phase 2 introduced `HyperAdjacencyGraph`, `DependencyGraphPort`, `MatrixToHyperGraphAdapter`, `IncrementalPropagator`, `IterationPort`/`IterationEngine`, `RuleSetImportResolver`, `ModuleRegistry`, `SemanticCache`, `RDF_RANGE_TO_FACT_TYPE` bridge, and `NodeSetMerger`. However, the codebase still has substantial legacy `DependencyMatrix` coupling:

- `InferenceEngine` still calls `node_set.get_dependency_matrix()` in ~53 locations across hot-path methods.
- `topo_sort.py` still operates on dense matrix lists with integer node IDs.
- `rule_set_scanner.py` still creates and stores a dependency matrix on `NodeSet`.
- `rule_service.py` still serializes `get_dependency_matrix().get_dependency_two_dimension_list()`.
- `IterateLine` still uses integer `node_id` for matrix row/col indexing in ~54 locations.
- `NodeSet` stores both `node_id_dictionary: Dict[int, str]` and `stable_node_id_dictionary: Dict[str, str]`.
- `DynamicVectorisedDependencyMatrix` still exists as a NumPy-based intermediate that should be deleted.
- `FactStorePort` still uses `typing.Protocol` instead of `ABCMeta`.
- Many tests still mock matrix APIs directly (~327 node_id refs in test files).
- **`NodeSetMerger.merge()`** (Phase 2 Task #19) merges `NodeSet` instances via `_merge_dependency_matrix()` which operates on dense 2D matrices — the merger must migrate to graph-native merge in Phase 2.5.
- **`NodeSet.add_node()` / `remove_node_by_name()`** (Phase 2) are building blocks for `GraphDependencyBuilder`, but they still assign runtime `node_id` integers — Phase 2.5 must transition these to `stable_id`-first registration.
- **`Node._origin`** is set as a dynamic attribute by the merger — Phase 2.5 must formalize `NodeOrigin` into `NodeRecord` storage on the graph.
- **`NodeSet._merge_dependency_matrix()`** performs bitmask OR on overlapping dense matrix cells — this logic must move to the graph's write-time merge (`add_dependency_group` with bitmask OR on `_edge_types`).

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
- **Phase 2 (additive):** `NodeSet` gains `get_stable_node_id_dictionary()` + `get_node_by_stable_node_id()`. All new code uses `stable_id`. `get_node_id()` becomes a deprecated alias.
- **Phase 2.5 (migrate consumers):** Engine, iterate, topo_sort migrate from `node_id` → `stable_id`/`node_name`. `node_id` still works via `HyperAdjacencyGraph._name_to_id` mapping.
- **Phase 3+ (remove):** `node_id` field removed from `Node`; `get_node_id_dictionary()` removed from `NodeSet`; `DependencyMatrix` deleted.

**`stable_id` generation inputs** (no `line_number`):
1. `module_path` — source module/rule path
2. `rule_name` — line type (e.g. "VALUE_CONCLUSION")
3. `variable_name` — the node's variable name
4. `normalized_text` — stripped/lowered node text
5. `parent_module_path` — parent rule/module path (empty for root nodes)
6. `import_namespace` — versioned package (e.g. `common_rules@2.1.0`); empty string for local nodes

**Node key preference:** New graph-native code prefers `stable_node_id` with `node_name` fallback. Legacy matrix code keeps `node_id` (integer) for row/col indexing.

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

### 2.8 NodeSet Dual Storage

**Graph as source of truth.** Matrix derived on demand via `GraphToMatrixAdapter` (the reverse of Phase 1's `MatrixToHyperGraphAdapter`). This avoids data drift between the two representations.

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

**Transition path:** During Phase 2.5 WS-2, `NodeSetMerger.merge()` gains a parallel code path that merges graphs when `NodeSet.get_graph()` is available, falling back to matrix merge for legacy `NodeSet` instances without a graph. Once all `NodeSet` instances carry a canonical graph, the matrix fallback is removed.

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
- **Migrate `NodeSetMerger`** from `_merge_dependency_matrix()` (dense 2D matrix merge) to graph-native merge via `add_dependency_group()` with write-time bitmask OR. Add a parallel code path during transition: merge graphs when `NodeSet.get_graph()` is available, fall back to matrix merge for legacy instances.
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

- Migrate `IterateLine` from integer `node_id` matrix row indexing to `stable_id`/`node_name`-keyed graph subgraph extraction.
- Migrate `InferenceEngine` from `node.get_node_id()` to `node.get_stable_node_id()` or `node.get_node_name()` in all hot-path methods.
- Mark `Node.get_node_id()`, `Node.set_node_id()`, `NodeSet.get_node_id_dictionary()`, `NodeSet.get_node_by_node_id()` as deprecated with `warnings.warn(DeprecationWarning)`.
- Add `NodeSet.get_stable_node_id_dictionary()` + `NodeSet.get_node_by_stable_node_id()` as the primary lookup API.
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

    For OR children: visit most-likely-TRUE first.
    For AND children: visit most-likely-FALSE first.
    Mixed children: OR first (most-TRUE), then AND (most-FALSE).
    Falls back to standard topological_sort() when no records available.
    """

    def __init__(self, graph: DependencyGraphPort):
        self._graph = graph

    def sort(self, records: Dict[str, HistoryRecord]) -> Tuple[str, ...]:
        ...
```

**Key design:** The strategy does NOT call `node.get_node_id()`. It uses `graph.get_child_groups()` (primitive port API) and `graph.get_typed_child_groups()` (domain convenience) for type-separated traversal. Record keys are `stable_id` strings, matching the new node identity model.

**Record key migration:** Move from string-conatenated names (e.g. `"not" + node_name`) to structured keys. Add `RecordKey` NamedTuple:

```python
class RecordKey(NamedTuple):
    node_stable_id: str
    dep_type_mask: int   # raw bitmask, for NOT/KNOWN prefix resolution
```

This avoids collisions like `"not" + node_name` vs a node actually named `"notapplicable"`.

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

**Transition strategy:** The merger gains a `_merge_graphs()` internal method. The public `merge()` method detects whether `NodeSet.get_graph()` is available on all inputs:
- If all inputs have graphs → call `_merge_graphs()`.
- If any input lacks a graph → fall back to `_merge_dependency_matrix()`.
- Once all `NodeSet` instances carry a canonical graph (after WS-2), remove the matrix fallback and delete `_merge_dependency_matrix()`.

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
| WS-1 Runtime | Replace `InferenceEngine` hot-path matrix calls with `DependencyGraphPort` calls; replace `node.get_node_id()` with `stable_id`/`node_name` | No hot-path direct `get_dependency_matrix()` or `get_node_id()` calls |
| WS-2 Parser | Create `GraphDependencyBuilder`; update `RuleSetScanner`/`NodeSet` to emit canonical `HyperAdjacencyGraph`; migrate `NodeSetMerger` from `_merge_dependency_matrix()` to graph-native merge via `add_dependency_group()` with write-time bitmask OR; formalize `NodeOrigin` into `NodeRecord` on graph; add parallel code path with matrix fallback; migrate `NodeSet.add_node()` / `remove_node_by_name()` / `rebuild_dependency_groups()` to graph-backed implementations | New parses expose a canonical graph; `NodeSetMerger` uses graph-native merge; `DynamicVectorisedDependencyMatrix` deleted; `NodeOrigin` stored in `NodeRecord` not `_origin` |
| WS-3 Persistence | Add graph edge-list serialization; create `GraphToMatrixAdapter` | Old matrix-backed data still loads; new data writes edge-list format |
| WS-4 Topology | Create `MLTopologicalSortStrategy`; migrate runtime topo sort to graph-native | Matrix topo sort is legacy only; ML sort produces identical output on regression tests |
| WS-5 Tests | Add parity, graph-first, and performance tests (1k/5k/10k sparse graphs); add `NodeSetMerger` matrix-vs-graph parity test confirming bitmask OR equivalence | Matrix and graph results match on representative rule sets |
| WS-6 Guardrails | Add import-linter or test-level boundary checks for `DependencyMatrix` and `node_id` usage | New production code cannot depend on `DependencyMatrix` or `node_id` (integer) |
| WS-7 Ports | Convert `FactStorePort` to ABCMeta; add default methods to `DependencyGraphPort` | No production port uses `typing.Protocol` without justification; all ports have contract tests |
| WS-8 Node Identity | Migrate `IterateLine` from `node_id` to `stable_id`/`node_name` graph subgraph extraction; deprecate `node_id` APIs with `DeprecationWarning`; remove `Node._origin` dynamic attribute in favor of `NodeRecord` | No hot-path `node_id` (integer) usage; `stable_id` is primary key; no `node._origin` reads |

**Execution order:** WS-6 → WS-7 → WS-2 → WS-1 → WS-4 → WS-8 → WS-3 → WS-5

Guardrails and port improvements come first because they define the boundary. Then the parser writes to the graph. Then consumers migrate. IterateLine migration (WS-8) comes after runtime refactor (WS-1) because iterate depends on the engine's graph-based traversal. Persistence (WS-3) and final tests (WS-5) come last.

---

## 6. Acceptance Criteria

- [ ] `InferenceEngine` runtime traversal and propagation use `DependencyGraphPort`.
- [ ] `DependencyMatrix` is not used by hot-path inference, propagation, or question selection.
- [ ] `DynamicVectorisedDependencyMatrix` is deleted.
- [ ] Parser/scanner can emit `HyperAdjacencyGraph` directly for new rule sets via `GraphDependencyBuilder`.
- [ ] Legacy dense matrix payloads still load through `MatrixToHyperGraphAdapter`.
- [ ] New rule persistence writes graph-native edge-list data with schema version.
- [ ] `GraphToMatrixAdapter` derives matrix on demand from the canonical graph (no dual storage).
- [ ] `dfs_topological_sort_with_record()` is preserved or graph-native `MLTopologicalSortStrategy` is regression-tested with golden tests comparing old vs new output.
- [ ] 1k/5k/10k sparse graph benchmarks are captured and compared against matrix baseline.
- [ ] Matrix imports are limited to adapter, legacy migration, and tests.
- [ ] All production ports use ABCMeta; `FactStorePort` converted from Protocol; Protocol only used for lightweight structural typing with documented justification.
- [ ] `DependencyGraphPort` has default method implementations for matrix-compatible API (`get_children_by_type`, `get_dependency_type`, `subgraph`, etc.).
- [ ] `HyperAdjacencyGraph` has `_edge_types` reverse index for O(1) per-edge dep_type lookup.
- [ ] `HyperAdjacencyGraph` has `_nodes: Dict[str, NodeRecord]` for explicit node storage.
- [ ] `HyperAdjacencyGraph` has `_name_to_id` / `_id_to_name` bidirectional mapping for GUI queries.
- [ ] `DependencyType` uses `IntFlag` (not `IntEnum`); port keeps `dep_type` as raw `int`.
- [ ] Bitmask composition is preserved; write-time merge ORs bitmasks for same (parent, child) pair.
- [ ] `subgraph()` preserves all edge dependency types unchanged; no type_mask filter.
- [ ] Node key preference: `stable_node_id` primary, `node_name` fallback, `node_id` (integer) legacy only.
- [ ] `node_id` (plain integer) deprecated with `DeprecationWarning`; all hot-path usage replaced with `stable_id`/`node_name`.
- [ ] `IterateLine` uses graph-native subgraph extraction instead of matrix row/col slicing.
- [ ] Import namespace uses versioned package format (`common_rules@2.1.0`); local nodes use empty string.
- [ ] Documentation marks `DependencyMatrix` and `node_id` as deprecated for runtime use.
- [ ] **`NodeSetMerger`** uses graph-native merge via `add_dependency_group()` with write-time bitmask OR instead of `_merge_dependency_matrix()` dense matrix merge; matrix fallback removed.
- [ ] **`NodeSetMerger`** parity test confirms bitmask OR equivalence: for every (parent, child) pair, `matrix_merge_result[parent_id][child_id] == graph_merge_result._edge_types[(parent_name, child_name)]`.
- [ ] **`NodeOrigin`** is stored in `NodeRecord` on the graph (`NodeRecord.imported`, `NodeRecord.import_depth`), not as a dynamic `node._origin` attribute; `node._origin` reads are migrated to `graph.get_node_record(node_name)`.
- [ ] **`NodeSet.add_node()`** delegates to `graph.register_node()` for `NodeRecord` storage; runtime `node_id` assignment is secondary/legacy.
- [ ] **`NodeSet._merge_dependency_matrix()`** is deleted; all callers use graph-native merge.
- [ ] **`NodeSet.rebuild_dependency_groups()`** reconstructs graph edges instead of dense matrix.

---

## 7. Handoff to Phase 3

Phase 3 should start only after Phase 2.5 confirms the graph-first runtime is stable. Phase 3's `BackwardChainOrchestrator`, `SessionManager`, convergence hashing, ontology deltas, and PROV-O trace generation should depend on `DependencyGraphPort`, not on `DependencyMatrix` or numeric matrix node IDs.

If Phase 3 must begin before Phase 2.5 is complete, it must use a `LegacyOrchestrator` fallback and treat graph-first migration as a blocking hardening item before production deployment.

---

## 8. `node_id` Deprecation Roadmap

| Phase | Action | Impact | Risk |
|-------|--------|--------|------|
| **Phase 2** (current) | Add `stable_id` generation with new inputs; `NodeSet.get_stable_node_id_dictionary()`; all new code uses `stable_id`; `get_node_id()` deprecated but functional; `NodeSetMerger` merges via `_merge_dependency_matrix()` with bitmask OR; `NodeOrigin` set as `node._origin` dynamic attribute; `NodeSet.add_node()` / `remove_node_by_name()` / `rebuild_dependency_groups()` added | Additive only — no breaking change | Low |
| **Phase 2.5** (bridge) | Migrate engine, iterate, topo_sort from `node_id` → `stable_id`/`node_name`; `DeprecationWarning` on `get_node_id()`; graph is primary; matrix derived on demand; `NodeSetMerger` migrates from `_merge_dependency_matrix()` to graph-native merge; `NodeOrigin` moves from `node._origin` to `NodeRecord` on graph; `NodeSet.add_node()` delegates to `graph.register_node()`; `NodeSet._merge_dependency_matrix()` deleted; `NodeSet.rebuild_dependency_groups()` reconstructs graph edges | Consumer-by-consumer migration | Medium |
| **Phase 3+** | Remove `node_id` field from `Node`; remove `get_node_id_dictionary()` from `NodeSet`; delete `DependencyMatrix`; remove `node._origin` property wrapper; all provenance reads go through `graph.get_node_record()` | Full removal | Low (once all consumers migrated) |

---

## 9. Phase 2.5 Bridge Handoff Inventory — Remaining Matrix Dependencies

Audited 2026-05-04. Phase 2 is **complete** (all 29 tasks done; Task #8 deferred to Phase 2.5). This inventory catalogs all remaining direct `DependencyMatrix` / `DynamicVectorisedDependencyMatrix` / `DependencyBuilder` dependencies in the codebase. Phase 2 production code does NOT directly depend on `DependencyMatrix` (only `matrix_to_hyper_adapter.py` is the sanctioned adapter). Performance baselines captured in `benchmarks/baseline_phase2.json` (forward_propagate_1k_5pct p95=0.323ms, 128× faster than full-scan baseline).

### 9.1 Source Code: `DependencyMatrix` Direct Imports

| # | File | Lines | Usage | Owner (P2.5 WS) | Risk | Migration Target |
|---|------|-------|-------|-----------------|------|-------------------|
| 1 | `src/domain/nodes/node_set.py` | 12, 46, 53, 151, 154, 155, 420, 432, 451, 474 | Stores `__dependency_matrix: DependencyMatrix`; `get/set_dependency_matrix()`; `rebuild_dependency_groups()` rebuilds matrix | WS-2 (NodeSet dual storage) | **High** — central data structure | Graph as source of truth; matrix derived on demand via `GraphToMatrixAdapter` |
| 2 | `src/domain/nodes/iterate_line.py` | 27, 249, 322, 677 | `parent_dependency_matrix: DependencyMatrix`; matrix row/col indexing for iterate subgraph extraction | WS-8 (IterateLine) | **High** — 54 `node_id` refs | Graph-native subgraph extraction via `DependencyGraphPort` |
| 3 | `src/domain/graph/matrix_to_hyper_adapter.py` | 16 | Adapter: converts `DependencyMatrix` → `HyperAdjacencyGraph` | WS-6 (adapter, keep) | **Low** — sanctioned bridge | Retained as legacy migration path |
| 4 | `src/domain/rule_parser/rule_set_parser.py` | 14, 246–265 | `create_dependency_matrix()` builds `DependencyMatrix` from dependency list | WS-7 (parser pipeline) | **Medium** — production path | `GraphDependencyBuilder` emits graph directly |
| 5 | `src/domain/rule_parser/i_scan_feeder.py` | 9, 100 | `create_dependency_matrix()` abstract method | WS-7 (parser pipeline) | **Medium** — production path | Replaced by graph-native builder |

### 9.2 Source Code: `DependencyBuilder` + `DynamicVectorisedDependencyMatrix`

| # | File | Lines | Usage | Owner (P2.5 WS) | Risk | Migration Target |
|---|------|-------|-------|-----------------|------|-------------------|
| 6 | `src/domain/nodes/dependency_builder.py` | 11, 34, 55, 80 | Collects dependencies → builds `DynamicVectorisedDependencyMatrix` | WS-7 (parser pipeline) | **Medium** | `GraphDependencyBuilder` |
| 7 | `src/domain/nodes/dynamic_vectorised_dependency_matrix.py` | 13–293 | NumPy-based intermediate matrix | WS-8 (delete) | **Low** — no new code depends | **Delete entirely** |
| 8 | `src/domain/rule_parser/rule_set_parser.py` | 12, 57, 77 | `DependencyBuilder` instance + `build_matrix()` | WS-7 (parser pipeline) | **Medium** | `GraphDependencyBuilder` |
| 9 | `src/domain/nodes/node_set.py` | 399, 403 | `DependencyBuilder` used in `rebuild_dependency_groups()` | WS-2 (NodeSet) | **Medium** | Graph-native rebuild |

### 9.3 Source Code: Matrix API Consumers (Hot Path)

| # | File | `get_dependency_matrix()` Calls | Usage | Owner (P2.5 WS) | Risk |
|---|------|-------------------------------|-------|-----------------|------|
| 10 | `src/domain/inference/inference_engine.py` | ~15 call sites (144, 250–251, 438–442, 671–675, 751, 770–771, 787, 814, 843) | Hot-path traversal: parent/child deps, dependency type checks, iterate child lists | WS-1 (InferenceEngine) | **Critical** |
| 11 | `src/domain/inference/topo_sort.py` | 31–479 (dense matrix params throughout) | BFS/DFS topo sort operates on `List[List[Any]]` | WS-6 (topo sort) | **High** |
| 12 | `src/domain/rule_parser/rule_set_scanner.py` | 145, 151, 158 | `set_dependency_matrix()`, `get_dependency_two_dimension_list()` | WS-7 (parser pipeline) | **Medium** |
| 13 | `src/domain/rule_parser/node_set_merger.py` | 42, 86, 88 | `_merge_dependency_matrix()` on merged NodeSet | WS-2 (NodeSetMerger graph migration) | **Medium** |

### 9.4 Test Code: Matrix References

| # | File | Approx Refs | Notes |
|---|------|-------------|-------|
| 14 | `tests/domain/nodes/test_iterate_line_coverage.py` | ~15 | `MagicMock(spec=DependencyMatrix)`, `get_dependency_matrix.return_value` |
| 15 | `tests/domain/inference/test_inference_engine.py` | ~5 | `get_dependency_matrix.return_value` |
| 16 | `tests/domain/nodes/test_node_set.py` | ~10 | `set/get_dependency_matrix`, `MagicMock(spec=DependencyMatrix)` |
| 17 | `tests/domain/rule_parser/test_node_set_merger.py` | ~8 | `DependencyMatrix` construction, `_merge_dependency_matrix` parity |
| 18 | `tests/domain/nodes/test_dependency_matrix.py` | ~7 | Direct `DependencyMatrix` unit tests |
| 19 | `tests/domain/nodes/test_dynamic_vectorised_dependency_matrix.py` | ~5 | `DynamicVectorisedDependencyMatrix` unit tests — delete with class |
| 20 | `tests/domain/inference/test_topo_sort.py` | ~3 | `_create_copy_of_dependency_matrix` |
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
2. **WS-7** — Parser pipeline: `GraphDependencyBuilder` replaces `DependencyBuilder` → `DynamicVectorisedDependencyMatrix` → `DependencyMatrix`
3. **WS-2** — `NodeSet` dual storage → graph as source of truth; `NodeSetMerger` graph migration
4. **WS-1** — `InferenceEngine` hot-path traversal → `DependencyGraphPort`
5. **WS-4** — `NodeOrigin` → `NodeRecord` on graph
6. **WS-8** — `IterateLine` → graph-native subgraph; delete `DynamicVectorisedDependencyMatrix`
7. **WS-3/WS-5** — Test migration; `FactStorePort` → ABCMeta; `topo_sort.py` cleanup
