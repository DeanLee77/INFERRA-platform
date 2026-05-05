
 🔴 Critical Enhancements (Should Fix Before Sprint)

 ### 1. Hash ID Collision Strategy Is Fragile

 §4.1 — A 12-char hex ID gives ~48 bits of entropy. For large rule sets with many imports, birthday-paradox collision probability becomes non-trivial at scale.

 Suggestion:
 - Increase to 16 chars (64 bits) — negligible cost, exponentially lower collision risk.
 - Add a deterministic collision-resolution step: if generate_node_id() produces a duplicate within the same parse context, append a monotonic counter suffix (:1, :2, …)
 rather than falling back to a global counter which breaks determinism.
 - Add a start-up sanity check that validates no existing persisted session references collide with newly-generated IDs.

 ### 2. LayeredFactStore Missing Deletion & Layer-Precedence Edge Cases

 §4.2 — The get_unified_view() merge uses {**semantic, **inferred, **asserted} — ASSERTED always wins. But there's no delete_fact() or clear_layer() method, and no
 handling for:

 - A fact re-asserted after being INFERRED (stale INFERRED entry lingers).
 - An INFERRED fact that should be invalidated when its antecedent changes (truth maintenance).

 Suggestion:

 ```python
   def remove_fact(self, name: str, source: FactSource) -> None: ...
   def invalidate_layer(self, source: FactSource) -> None: ...  # e.g., re-tract all INFERRED
   def get_fact_sources(self, name: str) -> Set[FactSource]: ...  # which layers hold this fact?
 ```

 Add a truth-maintenance hook: when set_fact(..., ASSERTED) overwrites an INFERRED fact, either (a) remove the INFERRED entry or (b) record an override flag so
 get_unified_view() doesn't need to rely solely on dict-merge ordering.

 ### 3. IterateContext Thread-Safety Is Not Addressed

 §4.3 — IterateContext.progress is a plain Dict[int, bool]. If concurrent requests hit /feed-answer for the same iterate node, you have a data race.

 Suggestion:
 - Add a per-session lock (or asyncio.Lock if fully async) around feed_iterate_answer().
 - Document the concurrency model explicitly: is a session single-threaded by design? If yes, assert it with a runtime guard (assert self._lock.locked()).

 ### 4. MatrixToHyperGraphAdapter._rebuild() Assumes Dense Matrix

 §4.4 — Iterating the entire matrix with for pid, row in enumerate(...) is O(n²). For sparse rule sets (common — most nodes have few dependencies), this is wasteful.

 Suggestion:
 - Use a sparse iteration path: for (pid, cid), dep_type in matrix.sparse_items() or equivalent.
 - Add a memoization guard: if the legacy matrix hasn't changed, skip _rebuild().
 - Document the matrix format contract (dense? CSR? custom?) so the adapter isn't guessing.

 ────────────────────────────────────────────────────────────────────────────────

 🟡 Important Enhancements (Should Consider for Phase 1)

 ### 5. No Observability / Structured Logging Strategy

 The plan mentions "trace logging" on Friday of WS-5 but has no structured logging standard. When debugging multi-layer state issues post-deployment, plain
 print/logging.info won't cut it.

 Suggestion:
 - Adopt structlog (or logging with JSON formatter) from day 1.
 - Define mandatory log fields: session_id, node_id, fact_source, correlation_id.
 - Add a correlation-ID middleware in FastAPI so every request can be traced end-to-end.
 - Log all layer transitions: ASSERTED → INFERRED override, INFERRED → invalidated, etc.

 ### 6. API Contracts Missing Error & Pagination Specs

 §4.6 — The API contracts define happy-path shapes but lack:

 - Error response schema ({ error_code, message, details? }).
 - Pagination for /summary (a session with 10k nodes returns a huge payload).
 - Rate limiting / idempotency for /feed-answer (duplicate submission?).

 Suggestion:

 ```yaml
   POST /api/v1/inference/feed-answer
     Headers: Idempotency-Key (optional)
     Returns:
       200: { has_more, goal_rule_name?, goal_rule_value? }
       409: { error_code: "DUPLICATE_ANSWER", message: "..." }
       422: { error_code: "INVALID_SESSION", message: "..." }
 ```

 Add pagination to /summary: ?session_id=&offset=&limit=.

 ### 7. Feature Flag Rollback Path Is Declared but Not Tested

 The plan says "rollback path verified" in §7, but §5's test matrix only tests USE_HYPERGRAPH={true,false}. There's no test for mid-session flag flip or flag-induced
 data incompatibility.

 Suggestion:
 - Add a flag-flip integration test: start a session with USE_HYPERGRAPH=false, flip to true mid-session, assert the session continues without error or is gracefully
 terminated.
 - Document: "Feature flags are start-of-session sticky — cannot flip mid-session."

 ### 8. RuleValidationService Caching Is Mentioned in Risks but Not Designed

 §6 Risk mentions "Cache results for identical rule text" but there's no implementation or cache schema.

 Suggestion:
 - Add a content-hash → ValidationResult cache (in-memory LRU, max 512 entries).
 - Invalidate on rule-name change (same text, different name = different import scope).
 - Set a TTL (e.g., 5 minutes) to handle transitive import changes.

 ### 9. No Database Migration / Schema Versioning Strategy

 The plan introduces FactSource tagging and IterateContext.progress but doesn't address how existing persisted sessions are migrated.

 Suggestion:
 - Add a session schema version field to persisted sessions.
 - Write a one-time migration script: existing facts → FactSource.ASSERTED (safe default).
 - Add a compatibility layer: if a session has no fact_source tags, treat all facts as ASSERTED.

 ### 10. Performance Benchmarks Lack Real-World Baseline

 §5 specifies <50ms validation, <100ms first question, <5% adapter overhead — but these numbers appear arbitrary without a known baseline.

 Suggestion:
 - Run the current system through the same benchmarks before any changes to establish a baseline.
 - Store baseline results in the repo (e.g., benchmarks/baseline_v0.json).
 - Fail CI if any benchmark regresses >10% from baseline.

 ────────────────────────────────────────────────────────────────────────────────

 🟢 Nice-to-Have Enhancements (Can Defer to Phase 2 but Worth Noting)

 ### 11. DependencyGroup Should Be Immutable & Hashable

 §4.4 — DependencyGroup(dep_type, frozenset(children)) uses a frozenset for children, but the DependencyGroup itself is stored in a list and doesn't guarantee
 immutability.

 Suggestion: Make DependencyGroup a NamedTuple or frozen dataclass with __hash__/__eq__.

 ### 12. No Health-Check / Readiness Endpoint

 The plan doesn't include a /health or /ready endpoint for Redis connectivity or graph initialization status.

 Suggestion: Add GET /health returning { redis: "ok", graph_init: bool } — critical for deployment orchestration.

 ### 13. Missing Contract Tests for FactStorePort

 §4.2 defines a Protocol but there's no explicit contract test suite that any implementation of FactStorePort must pass.

 Suggestion: Create tests/contracts/test_fact_store_port.py using pytest's @pytest.mark.parametrize over [LayeredFactStore, ...] — this pays dividends when you add
 Redis-backed or hybrid stores in Phase 2.

 ### 14. Back-Propagation Loop Detection

 §2.3 sequence diagram shows a BFS loop for back-propagation but doesn't address cyclic graph protection at runtime. The DAG check in RuleValidationService is pre-save
 only.

 Suggestion: Add a visited set in the BFS traversal and a max-iteration guard (e.g., if steps > len(all_nodes) * 2: raise CyclicGraphError).

 ### 15. Sprint Schedule Is Aggressive

 10 working days for 5 workstreams in parallel is extremely tight, especially with 92% coverage targets and property-based testing.

 Suggestion:
 - Add 2 buffer days explicitly (or mark Friday as "buffer + polish" rather than feature delivery).
 - Consider staggering WS-3 (IterateLine) to start Tuesday instead of Monday — it depends on FactSource from WS-2.
 - Define a daily stand-up check-in protocol with explicit "blocker escalation" path.

 ────────────────────────────────────────────────────────────────────────────────

 Summary Matrix

 ┌────┬───────────────────────────────────┬──────────────┬────────┐
 │ #  │ Enhancement                       │ Severity     │ Effort │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 1  │ Hash ID collision resolution      │ Critical     │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 2  │ Fact deletion & truth maintenance │ Critical     │ Medium │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 3  │ IterateContext thread-safety      │ Critical     │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 4  │ Sparse matrix adapter             │ Critical     │ Medium │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 5  │ Structured logging (structlog)    │ Important    │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 6  │ API error schemas & pagination    │ Important    │ Medium │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 7  │ Feature flag flip test            │ Important    │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 8  │ Validation cache design           │ Important    │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 9  │ Session schema migration          │ Important    │ Medium │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 10 │ Performance baselines             │ Important    │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 11 │ Immutable DependencyGroup         │ Nice-to-have │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 12 │ Health-check endpoint             │ Nice-to-have │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 13 │ Port contract tests               │ Nice-to-have │ Medium │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 14 │ Back-propagation loop guard       │ Nice-to-have │ Low    │
 ├────┼───────────────────────────────────┼──────────────┼────────┤
 │ 15 │ Sprint buffer & staggering        │ Nice-to-have │ N/A    │
 └────┴───────────────────────────────────┴──────────────┴────────┘

 The plan is architecturally sound and well-structured. The enhancements above primarily target runtime robustness (collision handling, concurrency, truth maintenance),
 operational readiness (logging, health checks, migrations), and spec completeness (API errors, caching, performance baselines). I'd strongly recommend addressing items
 1–4 before sprint kick-off, as they affect core correctness.