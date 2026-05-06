# Suggested Enhancements for INFERRA Phase 2 Implementation Plan

> Review of `INFERRA_Phase2_Implementation_Plan.md` (v1.0) against Phase 1 enhanced plan (v3.0),
> architectural soundness, runtime robustness, operational readiness, and spec completeness.

---

## 🔴 Critical Enhancements (Must Fix Before Sprint)

### 1. IncrementalPropagator Reimplements BFS Without Phase 1's Cycle Guard

§4.1 — `_forward_propagate_incremental` uses a plain `while queue: node = queue.pop(0)` BFS loop with **no visited set and no max-iteration guard**. Phase 1 already added `CyclicGraphError` protection to `HyperAdjacencyGraph.back_propagate()` (visited set + `steps > len(all_nodes) * 2`). The new propagator is a regression — a cyclic dependency graph will cause an infinite loop here.

Additionally, `queue.pop(0)` on a Python `list` is **O(n)** per pop. Phase 1 correctly used `collections.deque.popleft()` for O(1).

**Suggestion:**
- Replace `list.pop(0)` with `collections.deque` and `.popleft()`.
- Add a visited set + max-iteration guard consistent with Phase 1's `CyclicGraphError`.
- Better yet: **refactor to delegate BFS traversal** to `HyperAdjacencyGraph.back_propagate()` (already implemented in Phase 1) rather than reimplementing BFS. The propagator should call `graph.back_propagate(changed_node)` to get the ordered parent list, then topo-sort + evaluate only that subgraph. This eliminates duplicated traversal logic and guarantees cycle protection.

```python
def _forward_propagate_incremental(self, changed_node_ids: Set[str]) -> None:
    # Delegate BFS to Phase 1's cycle-guarded traversal
    impacted_ordered = self.graph.back_propagate(changed_node_ids)
    # Topo-sort ONLY impacted subgraph
    sub_children = {n: self.graph.get_child_groups(n) for n in impacted_ordered}
    ordered = self._topo_sort_subgraph(set(impacted_ordered), sub_children)
    for nid in ordered:
        if self._can_evaluate_parent(nid):
            self._evaluate_and_store(nid)
```

---

### 2. IterationEngine.record_answer() Violates FactStorePort Contract

§4.2 — `IterationEngine.record_answer()` calls:
```python
self._store.set_fact(question_name, FactValue(is_true), source=FactSource.INFERRED, metadata={"iterate_index": index})
```

But Phase 1's `FactStorePort.set_fact()` signature is:
```python
def set_fact(self, name: str, value: FactValue, source: FactSource = FactSource.ASSERTED) -> None: ...
```

There is **no `metadata` parameter** in the port contract. This will raise a `TypeError` at runtime. Either:
- (a) Extend `FactStorePort.set_fact()` to accept `Optional[Dict] metadata = None`, or
- (b) Store iterate-index metadata in a separate side-channel (`IterateContext` already tracks progress — the metadata is redundant).

**Suggestion:** Option (b) is cleaner. `IterateContext.progress` already stores `{index: bool}`. Remove the `metadata` kwarg from `record_answer()` and keep provenance tracking in `IterateContext` where it belongs. If metadata is needed later for PROV-O tracing, add a dedicated `IterateProvenanceStore` rather than overloading the fact store.

---

### 3. IterationEngine Has No Thread-Safety — Phase 1 Regression

§4.2 — Phase 1 explicitly added `asyncio.Lock` to `IterateLine.feed_iterate_answer()` with a documented concurrency model. The Phase 2 `IterationEngine.record_answer()` is a plain synchronous method with no lock, no concurrency model documentation, and no thread-safety guarantees. This is a regression.

**Suggestion:**
- Add `asyncio.Lock` to `IterationEngine` matching Phase 1's pattern.
- Make `record_answer()` async: `async def record_answer(...)` with `async with self._lock:`.
- Document the concurrency model explicitly in the class docstring.
- Add the same runtime guard pattern: `assert self._lock.locked()` inside `_ctx` mutations if session is declared single-threaded.

---

### 4. IterationEngine Lacks Phase 1's FactStorePort Methods

§4.2 — `IterationEngine` routes answers through `FactStorePort` but never uses Phase 1's `remove_fact()`, `invalidate_layer()`, or `get_fact_sources()`. When an iterate conclusion is superseded (e.g., user re-answers a question), the stale `INFERRED` entry must be properly handled via truth maintenance. Phase 1 added the `_overrides` tracking set for exactly this scenario — the `IterationEngine` must participate.

**Suggestion:**
- Before recording a new iterate answer, call `self._store.get_fact_sources(question_name)`. If the fact already exists as `ASSERTED`, skip the `INFERRED` write (or log a layer-override event via structlog).
- When an iterate is reset (e.g., session rollback), call `self._store.invalidate_layer(FactSource.INFERRED)` to clear stale conclusions.
- Add `reset_iterate_context()` method to `IterationEngine` that calls `invalidate_layer` + reinitializes `IterateContext`.

---

### 5. RuleSetImportResolver DFS Lacks Depth Guard & Timeout

§4.4 — The DFS resolution uses `in_stack` for cycle detection, which is correct. However:
- There is **no depth limit** — a maliciously deep import chain (e.g., 10k levels via transitive imports) will blow the Python call stack with a `RecursionError`.
- There is **no timeout** — if `_load_rule()` hangs on a slow DB/filesystem call, the entire validation blocks indefinitely.
- `path.append(rule_name)` / `path.pop()` are redundant with `in_stack` — they duplicate tracking and the path list is only used for error messages.

**Suggestion:**
```python
MAX_IMPORT_DEPTH = 100  # prevent RecursionError on deep chains

def _dfs_resolve(self, rule_name, visited, in_stack, path, depth=0):
    if depth > MAX_IMPORT_DEPTH:
        raise CircularImportError(f"Import depth exceeded {MAX_IMPORT_DEPTH} — possible chain too deep: {' → '.join(path)}")
    if rule_name in in_stack:
        raise CircularImportError(f"Cycle detected: {' → '.join(path + [rule_name])}")
    ...
```
- Add an `asyncio.timeout` or `functools.timeout` wrapper around `_load_rule()` for production safety.
- Simplify: use `in_stack` for cycle detection only; construct the error path from a separate lightweight list that doesn't need to be popped on every return.

---

### 6. Async Sync Pipeline Has No Dead-Letter Queue or Failure Observability

§4.3 — The Celery task `compile_and_push_to_fuseki` retries 3 times then silently fails. There is:
- **No dead-letter queue (DLQ)** — after 3 retries, the failure is lost. No reprocessing possible.
- **No failure event emission** — the orchestrator never learns that RDF projection failed.
- **No correlation with Phase 1's structured logging** — the Celery task doesn't emit `structlog` events with `session_id`, `rule_name`, `correlation_id`.
- **No circuit breaker** — if Fuseki is down, every rule save will trigger 3 retries × N concurrent tasks, potentially overwhelming the system.

**Suggestion:**
```python
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def compile_and_push_to_fuseki(self, rule_name: str, rule_text: str, source_hash: str) -> dict:
    import structlog
    log = structlog.get_logger().bind(rule_name=rule_name, source_hash=source_hash)
    try:
        rdf_triples = InferraToRdfCompiler.compile(rule_text, rule_name)
        FusekiAdapter.execute_sparql_idempotent_insert(rdf_triples, version=source_hash)
        log.info("fuseki_sync_success")
        return {"status": "success", "rule": rule_name, "hash": source_hash}
    except FusekiConnectionError as exc:
        log.warning("fuseki_connection_failed", retry=self.request.retries)
        self.retry(exc=exc)
    except Exception as exc:
        log.error("fuseki_sync_failed_permanently", error=str(exc))
        # Publish to dead-letter queue for manual reprocessing
        publish_dead_letter_event(rule_name, rule_text, source_hash, str(exc))
        raise

# Add circuit breaker
from circuitbreaker import circuit
FusekiAdapter.execute_sparql_idempotent_insert = circuit(
    failure_threshold=5, recovery_timeout=60
)(FusekiAdapter.execute_sparql_idempotent_insert)
```
- Add a `GET /api/v1/sync/status?rule_name=` endpoint so clients can check if async projection completed.
- Emit `RuleSyncFailed` event that the orchestrator can subscribe to for alerting.

---

## 🟡 Important Enhancements (Should Consider for Phase 2)

### 7. Structured Logging Not Propagated from Phase 1

Phase 1 established `structlog` with mandatory fields (`session_id`, `node_id`, `fact_source`, `correlation_id`) and correlation-ID middleware. Phase 2's code samples use no logging at all — not even `print()`. Every Phase 2 module must adopt the same logging standard.

**Suggestion:**
- Add `structlog` calls to all Phase 2 modules with the same mandatory fields.
- Add mandatory logging events specific to Phase 2:
  - Propagation: `forward_propagation_start`, `forward_propagation_complete` (with `impacted_count`, `evaluated_count`, `duration_ms`)
  - Iterate: `iterate_answer_recorded`, `iterate_completed` (with `quantifier`, `true_count`, `list_size`)
  - Async: `rule_updated_published`, `fuseki_sync_success`, `fuseki_sync_failed`
  - Import: `import_resolved`, `circular_import_detected` (with `path`)
  - Cache: `semantic_cache_preload`, `semantic_cache_hit`, `semantic_cache_miss`
- Add Phase 2 fields to the correlation context: `rule_name`, `import_depth`, `propagation_depth`.

---

### 8. API Contracts Missing for New Endpoints & No Error Schemas

§4.4 mentions `/rules/{name}/imports` and `/rules/validate` endpoints but provides no YAML contract. Phase 1 established a clear API contract format with error response schemas (404/409/422). Phase 2 must follow the same standard.

**Suggestion:**
```yaml
GET /api/v1/rules/{rule_name}/imports
  Returns:
    200: { rule_name, imports: [{ name, content_hash, node_count, depth }], has_cycles: false }
    404: { error_code: "RULE_NOT_FOUND", message: "..." }
    422: { error_code: "CIRCULAR_IMPORT", message: "Cycle detected: A → B → C → A" }

GET /api/v1/rules/{rule_name}/validate
  Returns:
    200: { valid: true, errors: [], warnings: [] }
    200: { valid: false, errors: [{ code, message, location? }], warnings: [] }
    404: { error_code: "RULE_NOT_FOUND", message: "..." }

GET /api/v1/sync/status?rule_name=
  Returns:
    200: { rule_name, status: "pending" | "completed" | "failed", source_hash, completed_at?, error? }
    404: { error_code: "RULE_NOT_FOUND", message: "..." }
```

Also add pagination to `/rules/{rule_name}/imports` for large import trees: `?depth=&offset=&limit=`.

---

### 9. ModuleRegistry Has No Eviction Policy & No Size Bounds

§4.4 — `ModuleRegistry` caches by `(rule_name, content_hash)` but has:
- **No maximum size** — unbounded memory growth as rules accumulate.
- **No TTL** — stale entries are never evicted if a rule's transitive imports change without the rule's own content_hash changing.
- **No LRU eviction** — least-recently-used entries should be evicted under memory pressure.
- Phase 1's `RuleValidationService` cache has explicit `cache_maxsize=512` and `cache_ttl_seconds=300`. `ModuleRegistry` should follow the same pattern.

**Suggestion:**
```python
class ModuleRegistry:
    def __init__(self, maxsize: int = 256, ttl_seconds: int = 600):
        self._cache: OrderedDict[Tuple[str, str], NodeSet] = OrderedDict()
        self._timestamps: Dict[Tuple[str, str], float] = {}
        self._maxsize = maxsize
        self._ttl = ttl_seconds

    def get(self, rule_name: str, content_hash: str) -> Optional[NodeSet]:
        key = (rule_name, content_hash)
        if key in self._cache:
            if time.time() - self._timestamps[key] > self._ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None
            self._cache.move_to_end(key)  # LRU
            return self._cache[key]
        return None

    def put(self, rule_name: str, content_hash: str, node_set: NodeSet) -> None:
        key = (rule_name, content_hash)
        if len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            del self._timestamps[oldest]
        self._cache[key] = node_set
        self._timestamps[key] = time.time()

    def invalidate(self, rule_name: str) -> None:
        """Invalidate all entries for a rule (triggered by RuleUpdated event)."""
        keys_to_remove = [k for k in self._cache if k[0] == rule_name]
        for k in keys_to_remove:
            del self._cache[k]
            del self._timestamps[k]
```
- On `RuleUpdated` event, call `registry.invalidate(rule_name)` to evict stale transitive caches.
- Add `registry.size()` and `registry.hit_rate()` for observability.

---

### 10. SemanticCache Has No Eviction, No Size Bounds, No OOM Protection Details

§4.5 — The risk table mentions "TTL eviction + max-triple cap; fallback to direct Fuseki query on cache miss" but the implementation is a stub (`return []`). This is the **most under-specified component** in the plan.

**Suggestion:**
```python
class SemanticCache:
    MAX_TRIPLES = 500_000
    TTL_SECONDS = 3600  # 1 hour

    def __init__(self):
        self.graph = rdflib.Graph()
        self._loaded_rules: Set[str] = set()
        self._last_query_timestamp: float = 0.0

    def preload(self, rule_name: str) -> None:
        if rule_name in self._loaded_rules:
            return
        if len(self.graph) > self.MAX_TRIPLES:
            log.warning("semantic_cache_near_oom", triple_count=len(self.graph))
            self._evict_oldest_entries(target=self.MAX_TRIPLES // 2)
        query = FusekiAdapter.get_rule_triples(rule_name)
        for triple in query:
            self.graph.add(triple)
        self._loaded_rules.add(rule_name)

    def _evict_oldest_entries(self, target: int) -> None:
        """Evict oldest preloaded rules until triple count is below target."""
        while len(self.graph) > target and self._loaded_rules:
            oldest = self._loaded_rules.pop()  # ordered set → FIFO
            # Remove triples associated with this rule
            self.graph -= self._rule_subgraph(oldest)

    def query_new_deltas(self, since_timestamp: float) -> List[Triple]:
        if since_timestamp == self._last_query_timestamp:
            return []
        deltas = FusekiAdapter.query_deltas(since_timestamp)
        self._last_query_timestamp = time.time()
        return deltas

    def clear(self) -> None:
        self.graph = rdflib.Graph()
        self._loaded_rules.clear()

    @property
    def triple_count(self) -> int:
        return len(self.graph)

    @property
    def memory_usage_mb(self) -> float:
        import sys
        return sys.getsizeof(self.graph.serialize()) / (1024 * 1024)
```
- Add OOM guard: if `memory_usage_mb > THRESHOLD`, log alert + fall back to direct Fuseki.
- Add metrics: `triple_count`, `memory_usage_mb`, `hit_rate` exposed via `/health` or Prometheus.
- Add `clear()` method for session teardown (prevent RDFLib graphs leaking across sessions).

---

### 11. No Session Schema Migration for Phase 1 → Phase 2

Phase 1 added `SessionMetadata.schema_version = 1` with migration logic. Phase 2 introduces `IterationEngine`, `ModuleRegistry`, semantic cache preloading, and `NodeOrigin` metadata. Existing sessions from Phase 1 will lack:
- `NodeOrigin` metadata on nodes
- `iteration_engine_state` in the session payload
- `semantic_cache_loaded_rules` tracking

**Suggestion:**
- Bump `CURRENT_SCHEMA_VERSION = 2`.
- Write Phase 1→2 migration:
  ```python
  if from_version < 2:
      # Add NodeOrigin metadata (default: module = "unknown", imported = False)
      for node in data.get("nodes", []):
          node.setdefault("origin", {"module": "unknown", "imported": False})
      # Migrate iterate progress from old IterateContext format
      data.setdefault("iteration_state", {})
      data.setdefault("semantic_cache_loaded", [])
  ```
- Add compatibility: if `iteration_state` is missing, reconstruct from `working_memory` facts tagged `INFERRED` that match iterate node patterns.
- Add integration test: load a Phase 1 session, assert Phase 2 code handles it without error.

---

### 12. _topo_sort_subgraph() Is Undocumented & Untested

§4.1 references `self._topo_sort_subgraph(impacted, sub_children)` but this method is not defined, not documented, and has no tests. This is the core of incremental propagation — if it's wrong, the entire propagation order is wrong.

**Suggestion:**
- Define the method explicitly:
  ```python
  def _topo_sort_subgraph(self, node_ids: Set[str], child_map: Dict[str, Tuple[DependencyGroup, ...]]) -> List[str]:
      """Topologically sort an impacted subgraph using graphlib.TopologicalSorter.
      Only considers edges within the subgraph — external dependencies are ignored."""
      sorter = graphlib.TopologicalSorter()
      for nid in node_ids:
          sorter.add(nid)
          for group in child_map.get(nid, ()):
              for child in group.children:
                  if child in node_ids:  # only intra-subgraph edges
                      sorter.add(nid, child)
      return list(sorter.static_order())
  ```
- Add unit tests for: empty subgraph, single node, diamond dependency, disconnected components, cycle within subgraph.
- Add property-based test: `topo_sort_subgraph` output is always a valid topological ordering of the subgraph.

---

### 13. Feature Flag Matrix Is Incomplete & No Mid-Session Flip Tests

§5 CI/CD lists `USE_HYPERGRAPH={true,false}`, `LEGACY_ITERATE={true,false}`, `MODULAR_IMPORTS=true` — but `ASYNC_SYNC_ENABLED` is missing from the matrix. Also, Phase 1 established "feature flags are start-of-session sticky" — Phase 2 must test that same constraint for its new flags.

**Suggestion:**
- Add `ASYNC_SYNC_ENABLED={true,false}` to the CI feature flag matrix.
- Add `MODULAR_IMPORTS={true,false}` (currently only `true` — must test the false/legacy path).
- Add mid-session flip tests for all Phase 2 flags:
  - Start session with `ASYNC_SYNC_ENABLED=false`, flip to `true`, assert Celery tasks are not published retroactively.
  - Start session with `MODULAR_IMPORTS=false`, flip to `true`, assert import resolution doesn't corrupt mid-session state.
- Document: "Phase 2 feature flags are start-of-session sticky, consistent with Phase 1 policy."

---

### 14. No Observability for Async Pipeline — Missing Metrics & Tracing

The async pipeline (Celery → Fuseki → SemanticCache) has no metrics, no tracing, and no dashboard. When production issues arise (stale ontology, failed syncs, cache misses), there will be no diagnostic data.

**Suggestion:**
- Add Prometheus-style metrics (or simple `/metrics` endpoint):
  - `inferra_fuseki_sync_total{status="success|failed|retry"}`
  - `inferra_fuseki_sync_duration_seconds`
  - `inferra_semantic_cache_triples_loaded`
  - `inferra_semantic_cache_hit_rate`
  - `inferra_propagation_duration_seconds{direction="forward|backward"}`
  - `inferra_propagation_impacted_nodes`
  - `inferra_import_resolve_depth`
- Correlate Celery task IDs with Phase 1's correlation-ID via `structlog.contextvars`.
- Add a `/api/v1/metrics` or Prometheus `/metrics` endpoint that aggregates these.

---

## 🟢 Nice-to-Have Enhancements (Can Defer to Phase 3 but Worth Noting)

### 15. IterationPort Contract Test Suite Missing

Phase 1 added `FactStorePort` contract tests (`tests/contracts/test_fact_store_port.py`). Phase 2 introduces `IterationPort` but has no equivalent contract test. When Phase 3 adds alternative implementations (e.g., distributed iterate for multi-node sessions), contract tests pay dividends.

**Suggestion:**
- Create `tests/contracts/test_iteration_port.py` using `@pytest.mark.parametrize` over `[IterationEngine, ...]`.
- Test contract: `initialise()` → `record_answer()` → `evaluate()` → `get_progress()` lifecycle.
- Test edge cases: double-initialise (idempotent), record after completion, evaluate before completion (raises).

---

### 16. No Health-Check Extensions for Phase 2 Dependencies

Phase 1 added `GET /health` checking Redis + graph_init. Phase 2 adds Celery, Fuseki, and RDFLib dependencies that should be included.

**Suggestion:**
```yaml
GET /api/v1/health
  Returns:
    200: {
      status: "ok",
      redis: "ok",
      celery: "ok",
      fuseki: "ok",
      graph_init: true,
      semantic_cache: { triples: 12345, memory_mb: 8.3 },
      version: "..."
    }
    503: {
      status: "degraded",
      redis: "ok",
      celery: "ok",
      fuseki: "unavailable",
      graph_init: true,
      semantic_cache: { triples: 0, memory_mb: 0 }
    }
```
- Add `/health` check for Celery broker connectivity.
- Add `/health` check for Fuseki endpoint availability.
- Add semantic cache stats (triple count, memory usage).

---

### 17. NodeSetMerger.merge() Is Referenced but Not Defined

§4.4 calls `NodeSetMerger.merge(rule_text, merged_imports, rule_name)` but this class/method is not defined, documented, or tested. This is the critical integration point where imported NodeSets are combined — if merge semantics are wrong, the entire import chain produces corrupted graphs.

**Suggestion:**
- Define `NodeSetMerger` with explicit merge rules:
  - **Name collision**: imported node with same variable name as local node → local wins (or raise error if `strict=True`).
  - **ID collision**: use Phase 1's `generate_node_id()` with module-qualified names to avoid collisions.
  - **Ordering**: imported nodes are prepended before local nodes in topological order.
  - **Dependency groups**: merged dependency groups are unioned; duplicate edges are deduplicated.
- Add `NodeOrigin` metadata to every merged node: `{module: "imported_rule", depth: import_depth}`.
- Add property-based tests: merging is associative, commutative, and idempotent for identical inputs.

---

### 18. No Backpressure on Celery Task Submission

§4.3 — `publish_rule_updated_event()` calls `compile_and_push_to_fuseki.delay()` without any rate limiting or backpressure. If 100 rules are saved simultaneously, 100 Celery tasks fire at once, potentially overwhelming Fuseki.

**Suggestion:**
- Add a Celery rate limit: `@shared_task(rate_limit="10/m")` to cap throughput.
- Or use a Celery chord/group to batch compilations.
- Add a simple throttle in `publish_rule_updated_event()`: track in-flight tasks per rule, skip if one is already pending for the same `source_hash` (idempotency at the submission level, not just execution level).

---

### 19. DependencyGraphPort Is Referenced but Never Defined for Phase 2

Phase 1 defined `FactStorePort` and `DependencyGraphPort` as interfaces. Phase 2's `IncrementalPropagator` takes `graph: DependencyGraphPort` but Phase 1's code shows `HyperAdjacencyGraph` implementing methods directly — the `DependencyGraphPort` Protocol is not explicitly defined with method signatures.

**Suggestion:**
- Define `DependencyGraphPort` explicitly:
  ```python
  class DependencyGraphPort(Protocol):
      def get_parent_edges(self, node_id: str) -> Set[str]: ...
      def get_child_groups(self, node_id: str) -> Tuple[DependencyGroup, ...]: ...
      def back_propagate(self, changed_node: str, max_steps: int = 0) -> Deque[str]: ...
      def get_all_node_ids(self) -> Set[str]: ...
  ```
- Add `get_all_node_ids()` method to `HyperAdjacencyGraph` (referenced in enhancement #1 but not defined).
- Add contract tests for `DependencyGraphPort` matching Phase 1's `FactStorePort` pattern.

---

### 20. Sprint Schedule Is Aggressive & Lacks Buffer Days

Phase 1 (enhanced) added 2 buffer days and designated Friday as "buffer + polish." Phase 2 reverts to 5 pure feature days with no buffer, despite Phase 2 being more complex (4 workstreams, async infrastructure, external Fuseki dependency, Celery integration).

**Suggestion:**
- Add 2 buffer days (same as Phase 1).
- Designate Friday as "buffer + polish + integration" rather than feature delivery.
- WS-3 (Async Sync) depends on external Fuseki availability — add a contingency: if Fuseki is not provisioned by Tuesday, WS-3 switches to mock-based development.
- WS-4 (Imports) depends on ModuleRegistry from WS-3 — consider staggering WS-4 to start Tuesday.
- Add daily stand-up protocol with blocker escalation (same as Phase 1).

---

## Summary Matrix

┌────┬──────────────────────────────────────────────────┬──────────────┬────────┐
│ #  │ Enhancement                                      │ Severity     │ Effort │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 1  │ BFS cycle guard + deque (Phase 1 regression)     │ Critical     │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 2  │ FactStorePort contract violation (metadata kwarg)│ Critical     │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 3  │ IterationEngine thread-safety (Phase 1 regress.) │ Critical     │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 4  │ Truth-maintenance integration in IterationEngine │ Critical     │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 5  │ Import DFS depth guard + timeout                  │ Critical     │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 6  │ Async DLQ + failure events + circuit breaker      │ Critical     │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 7  │ Structured logging propagation from Phase 1       │ Important   │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 8  │ API contracts for new endpoints + error schemas   │ Important   │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 9  │ ModuleRegistry eviction policy + size bounds      │ Important   │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 10 │ SemanticCache eviction, OOM guard, metrics        │ Important   │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 11 │ Session schema migration Phase 1 → Phase 2        │ Important   │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 12 │ _topo_sort_subgraph() definition + tests          │ Important   │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 13 │ Feature flag matrix completion + flip tests       │ Important   │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 14 │ Async pipeline observability + metrics             │ Important   │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 15 │ IterationPort contract test suite                 │ Nice-to-have │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 16 │ Health-check extensions for Phase 2 deps          │ Nice-to-have │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 17 │ NodeSetMerger.merge() definition + tests          │ Nice-to-have │ Medium │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 18 │ Celery backpressure / rate limiting                │ Nice-to-have │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 19 │ DependencyGraphPort Protocol definition           │ Nice-to-have │ Low    │
├────┼──────────────────────────────────────────────────┼──────────────┼────────┤
│ 20 │ Sprint buffer days + WS staggering                │ Nice-to-have │ N/A    │
└────┴──────────────────────────────────────────────────┴──────────────┴────────┘

**The Phase 2 plan is architecturally sound and well-structured.** The primary concerns are:
1. **Phase 1 regressions** — cycle guards, thread-safety, and contract compliance must not be lost in the transition.
2. **Under-specified components** — `SemanticCache`, `NodeSetMerger`, `_topo_sort_subgraph`, and `DependencyGraphPort` need concrete implementations before sprint start.
3. **Operational readiness** — logging, metrics, health checks, and failure handling for the async pipeline are essential for production deployment.
4. **Consistency with Phase 1 conventions** — structured logging, API error schemas, feature flag stickiness, session schema migration, and contract tests should carry forward seamlessly.

I strongly recommend addressing items 1–6 before sprint kick-off, as they affect core correctness and Phase 1 compatibility.

---

## 📋 Post-Integration Reconciliation Note (v3.1)

All 20 enhancement items (#1–#20) were incorporated into the Phase 2 Implementation Plan v3.0. Subsequently, v3.1 reconciled the plan against **actual Phase 1 delivered code** (not the assumed/idealized interfaces). The following mismatches were found and corrected:

| # | Mismatch | v3.0 Assumed | Actual Phase 1 Code | Resolution |
|---|----------|-------------|---------------------|------------|
| 1 | `DependencyGraphPort` base class | `Protocol` | `ABCMeta` | §4.9: Changed to ABC |
| 2 | `get_all_node_ids()` | Referenced | `all_node_names()` | §4.9: Fixed method name |
| 3 | `get_node_name()` on graph | Referenced | Does not exist (node IDs ARE names) | §4.1: Use `node_id` directly |
| 4 | `get_child_groups()` return type | `Tuple[DependencyGroup, ...]` | `Tuple[Tuple[int, Tuple[str, ...]], ...]` (primitives) | §4.1: Use primitive port API |
| 5 | `IterationPort` base class | `Protocol` | Project uses `ABCMeta` pattern | §4.9b: Changed to ABCMeta |
| 6 | Missing feature flags | 4 flags | 6 flags (+`LAYERED_MEMORY`, `ML_OPTIMIZED_DFS`) | §1, §5: Added to scope |
| 7 | `HistoryRecordStorePort` | Not mentioned | Already exists as ABC; DB adapter deferred to Phase 2 | §1, §7: Added as deliverable |
| 8 | `dfs_topological_sort_with_record()` | Not mentioned | Already exists, wired when `ML_OPTIMIZED_DFS=true` | §7: Preservation criterion |
| 9 | `_overrides` / `get_changed_since()` | Treated as Phase 2 gaps | Already fully wired in Phase 1 | §7: Noted as carry-forward |
| 10 | `IterateLine.__iterate_ie` removal | No transition plan | Still present; `LEGACY_ITERATE=true` default | §4.2b: Added delegation wiring |

See `INFERRA_Phase2_Implementation_Plan.md` Appendix B for the full reconciliation table.
