# Suggested Enhancements for INFERRA Phase 3 Implementation Plan

> Review of `INFERRA_Phase3_Implementation_Plan.md` (v1.0) against Phase 1 (v3.0) and Phase 2 (v3.0) enhanced plans,
> architectural soundness, runtime robustness, operational readiness, spec completeness, and cross-phase consistency.

---

## 🔴 Critical Enhancements (Must Fix Before Sprint)

### 1. SessionManager.check_convergence() Uses Non-Deterministic Hash for Fixed-Point Detection

§4.2 — `hashlib.sha256(str(wm).encode()).hexdigest()` is used to detect working-memory stability. However, `str(wm)` on a `dict` is **not order-deterministic** in the general case. While Python 3.7+ preserves insertion order, two dicts with the same keys/values but different insertion histories (e.g., one built via successive `set_fact()` calls, another deserialized from Redis) will produce different `str()` representations, causing `state_stable` to be `False` even when the working memory hasn't actually changed. This produces **false non-convergence** and wastes iterations, potentially hitting `ITERATION_CAP` on every session.

Additionally, `str(wm)` on a `Dict[str, FactValue]` depends on `FactValue.__repr__()` which is not guaranteed to be stable across sessions or serialisation boundaries.

**Suggestion:**

```python
import hashlib, json

class SessionManager:
    def _compute_wm_hash(self, wm: Dict[str, FactValue]) -> str:
        """Deterministic hash: sort keys, use stable FactValue serialisation."""
        canonical = json.dumps(
            {k: wm[k].to_canonical_string() for k in sorted(wm.keys())},
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def check_convergence(self, session_id: str, goal: str, mandatory: List[str]) -> ConvergenceResult:
        ctx = self._snapshots[session_id]
        wm = ctx.fact_store.get_unified_view()

        goal_reached = goal in wm and wm[goal].get_value() is not None
        mandatory_met = all(m in wm for m in mandatory)

        current_hash = self._compute_wm_hash(wm)
        state_stable = self._prev_wm_hashes.get(session_id) == current_hash
        ontology_stable = getattr(ctx, 'ontology_delta', 0) == 0

        self._prev_wm_hashes[session_id] = current_hash

        if goal_reached and mandatory_met and state_stable and ontology_stable:
            return ConvergenceResult(True, "FIXED_POINT", ctx.iteration_count, current_hash, 0)
        if goal_reached and mandatory_met:
            return ConvergenceResult(True, "GOAL_REACHED", ctx.iteration_count, current_hash, getattr(ctx, 'ontology_delta', 0))
        return ConvergenceResult(False, "PENDING", ctx.iteration_count, current_hash, getattr(ctx, 'ontology_delta', 0))
```

- Add `FactValue.to_canonical_string()` method that produces a stable, deterministic representation.
- Sort keys before hashing to guarantee determinism regardless of insertion order.
- Add unit test: create two dicts with same keys/values but different insertion order → assert identical hash.
- Add property-based test: `check_convergence` returns same result when called twice with identical working memory.

---

### 2. Async Post-Reasoning Pipeline Writes to FactStorePort Without Synchronisation

§4.3 — `run_post_reasoning()` calls `FactStorePort.set_fact(name, val, source=FactSource.SEMANTIC)` from a **Celery worker** (separate process/thread) while the main session's `/feed-answer` handler may be simultaneously reading/writing to the same `LayeredFactStore`. This is a race condition:

- The Celery worker writes `SEMANTIC` facts into the store while `get_unified_view()` is iterating the three layer dicts.
- `IncrementalPropagator._forward_propagate_incremental()` may read a partially-updated `SEMANTIC` layer.
- No lock, no atomicity, no version check — the `asyncio.Lock` from Phase 2's `IterationEngine` only protects within a single event loop, not across processes.

This is a Phase 1/2 regression — both phases explicitly added concurrency guards (`asyncio.Lock` on `IterateLine`, `asyncio.Lock` on `IterationEngine`).

**Suggestion:**

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_post_reasoning(self, session_id: str, rule_name: str, working_memory_snapshot: dict) -> dict:
    try:
        new_triples = OntologyPort.persist_conclusions(rule_name, session_id, working_memory_snapshot)
        delta_facts = OntologyPort.run_reasoner()
        # Publish deltas as events — do NOT write directly to FactStore from Celery worker
        publish_ontology_delta_event(session_id, delta_facts)
        return {"session_id": session_id, "injected": len(delta_facts)}
    except Exception as exc:
        self.retry(exc=exc)

# Main process consumes the event and injects under its own lock
class OntologyDeltaConsumer:
    async def on_ontology_delta(self, session_id: str, delta_facts: List[Tuple[str, FactValue]]):
        async with self._lock:  # Same lock that guards /feed-answer
            for name, val in delta_facts:
                self._store.set_fact(name, val, source=FactSource.SEMANTIC)
            log.info("ontology_delta_injected", session_id=session_id, delta_count=len(delta_facts))
```

- Do NOT write to `FactStorePort` from Celery workers — they run in separate processes.
- Publish `OntologyDeltaEvent` to Redis pub/sub or a results queue.
- Main process consumes events and injects under the same lock that guards `/feed-answer`.
- Document the concurrency model: "Celery workers produce deltas; main process consumes and injects under session lock. No cross-process writes to `LayeredFactStore`."

---

### 3. InferenceContext Attributes `ontology_delta` and `iteration_count` Are Undefined

§4.1/4.2 — `SessionManager.check_convergence()` accesses `ctx.ontology_delta` and `ctx.iteration_count`, but `InferenceContext` is not defined in Phase 3, and Phase 1/2 don't define these attributes. This will raise `AttributeError` at runtime.

**Suggestion:**

Define `InferenceContext` explicitly with all attributes referenced by `SessionManager`:

```python
# src/domain/session/inference_context.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from src.ports.fact_store_port import FactStorePort
from src.domain.state.fact_source import FactSource

@dataclass
class InferenceContext:
    session_id: str
    rule_name: str
    target: str
    mandatory: List[str]
    fact_store: FactStorePort
    started_at: datetime = field(default_factory=datetime.utcnow)
    iteration_count: int = 0
    ontology_delta: int = 0
    question_strategy_name: str = "conservative"
    prov_o_trace: Optional[str] = None

    def increment_iteration(self) -> None:
        self.iteration_count += 1

    def set_ontology_delta(self, delta: int) -> None:
        self.ontology_delta = delta
```

- Add `InferenceContext` dataclass with all attributes referenced by `SessionManager`, `BackwardChainOrchestrator`, and `ProvOTraceGenerator`.
- Add `started_at` for PROV-O trace generation (`prov:startedAtTime`).
- Add `question_strategy_name` for debugging which strategy is active.
- Add unit tests for `InferenceContext` lifecycle: creation → increment → convergence check.

---

### 4. ProvOTraceGenerator Produces Invalid RDF via String Concatenation

§4.4 — The generator builds triples using f-string interpolation:

```python
triples.append(f"<inf:fact:{session_id}:{fact_name}> a prov:Entity ;")
```

This has multiple issues:
- **No RDF escaping**: Special characters in `fact_name` (spaces, angle brackets, quotes, `#`, `/`) will produce malformed Turtle.
- **No namespace management**: Prefixes `inf:` and `prov:` are used but never declared.
- **No validation**: Output is never checked for well-formedness.
- **Phase 2 regression**: Phase 2 already introduced `rdflib.Graph` for the `SemanticCache`. The `ProvOTraceGenerator` should use the same library, not raw string concatenation.

**Suggestion:**

```python
# src/domain/trace/prov_o_generator.py
import rdflib
from rdflib import Namespace, Literal, URIRef
from rdflib.namespace import PROV, RDF, XSD
from datetime import datetime
import structlog

log = structlog.get_logger()

INF = Namespace("http://inferra.ai/ontology#")

class ProvOTraceGenerator:
    def __init__(self):
        self.INF = INF

    def generate(self, session_id: str, context: InferenceContext) -> rdflib.Graph:
        g = rdflib.Graph()
        g.bind("inf", INF)
        g.bind("prov", PROV)

        session_uri = INF[f"session/{session_id}"]
        g.add((session_uri, RDF.type, PROV.Activity))
        g.add((session_uri, RDF.type, INF.Session))
        g.add((session_uri, PROV.startedAtTime,
               Literal(context.started_at.isoformat(), datatype=XSD.dateTime)))

        if context.fact_store is not None:
            for fact_name, fact_val in context.fact_store.get_unified_view().items():
                safe_name = rdflib.URIRef(fact_name)  # rdflib handles escaping
                fact_uri = INF[f"fact/{session_id}/{safe_name}"]
                g.add((fact_uri, RDF.type, PROV.Entity))
                g.add((fact_uri, PROV.wasGeneratedBy, session_uri))
                source = getattr(context, 'fact_source_map', {}).get(fact_name, FactSource.ASSERTED)
                g.add((fact_uri, INF.factSource, INF[source.value]))

        log.info("prov_o_trace_generated", session_id=session_id, triple_count=len(g))
        return g

    def to_turtle(self, session_id: str, context: InferenceContext) -> str:
        return self.generate(session_id, context).serialize(format="turtle")

    def to_json_ld(self, session_id: str, context: InferenceContext) -> str:
        return self.generate(session_id, context).serialize(format="json-ld")
```

- Use `rdflib.Graph` for type-safe triple construction (consistent with Phase 2's `SemanticCache`).
- `rdflib` handles URI escaping, namespace prefix declarations, and output validation.
- Return `rdflib.Graph` from `generate()` for flexibility; add `to_turtle()` and `to_json_ld()` convenience methods.
- Add round-trip test: generate → parse → assert same triples.

---

### 5. BackwardChainOrchestrator.run_convergence_loop() Has No Thread-Safety

§4.1 — The convergence loop is a plain synchronous `for` loop with no lock, no concurrency model documentation, and no thread-safety guarantees. Phase 1 added `asyncio.Lock` to `IterateLine.feed_iterate_answer()`. Phase 2 added `asyncio.Lock` to `IterationEngine.record_answer()`. Phase 3's orchestrator is the most critical coordination point and has **zero concurrency protection**.

If two concurrent `/feed-answer` requests trigger `run_convergence_loop()` for the same session:
- Both read the same `_prev_wm_hashes` state.
- Both compute the same `current_hash`.
- Both may conclude convergence simultaneously and trigger duplicate PROV-O trace generation.

**Suggestion:**

```python
import asyncio, structlog

log = structlog.get_logger()

class BackwardChainOrchestrator:
    def __init__(self, engine: InferenceEngine, session_mgr: SessionManager,
                 ontology: OntologyPort, strategy: QuestionStrategy):
        self.engine = engine
        self.session_mgr = session_mgr
        self.ontology = ontology
        self.strategy = strategy
        self._lock: asyncio.Lock = asyncio.Lock()
        """Concurrency model: sessions are single-threaded by design; asyncio.Lock
        provides a safety net for async frameworks that may interleave coroutines.
        Consistent with Phase 1/2 convention."""

    async def run_convergence_loop(self, session_id: str, max_iterations: int = 10) -> ConvergenceResult:
        async with self._lock:
            for i in range(1, max_iterations + 1):
                res = self.session_mgr.check_convergence(session_id)
                if res.converged:
                    log.info("convergence_achieved", session_id=session_id, reason=res.reason, iteration=i)
                    return res
                log.debug("convergence_iteration", session_id=session_id, iteration=i, reason=res.reason)

            log.warning("convergence_cap_exceeded", session_id=session_id, max_iterations=max_iterations)
            return ConvergenceResult(False, "ITERATION_CAP", max_iterations,
                                     self.session_mgr.get_wm_hash(session_id),
                                     self.session_mgr.get_ontology_delta(session_id))
```

- Make `run_convergence_loop()` async with `asyncio.Lock` (Phase 1/2 convention).
- Add `structlog` calls for convergence events (Phase 1/2 mandatory logging).
- Document concurrency model in class docstring.
- Add test: concurrent calls to `run_convergence_loop()` for same session → only one convergence trace generated.

---

### 6. Convergence Criteria Are Too Strict — Async Pipeline Latency Causes False ITERATION_CAP

§4.2 — The fixed-point check requires ALL four criteria simultaneously:
```
goal_reached AND mandatory_met AND state_stable AND ontology_stable
```

But `ontology_stable` (`ontology_delta == 0`) depends on the **async post-reasoning pipeline** completing. The convergence loop runs synchronously after each `/feed-answer`, but the Celery worker may take seconds to complete. This means:

1. `/feed-answer` triggers convergence check → `ontology_delta > 0` (pipeline still running).
2. Loop iterates again → `state_stable = True` but `ontology_stable = False`.
3. After 10 iterations → `ITERATION_CAP` hit, even though the goal was reached and mandatory facts are present.
4. User gets a `ConvergenceLimitExceeded` error when the session should have converged.

**Suggestion:**

```python
def check_convergence(self, session_id: str, goal: str, mandatory: List[str]) -> ConvergenceResult:
    ctx = self._snapshots[session_id]
    wm = ctx.fact_store.get_unified_view()

    goal_reached = goal in wm and wm[goal].get_value() is not None
    mandatory_met = all(m in wm for m in mandatory)

    current_hash = self._compute_wm_hash(wm)
    state_stable = self._prev_wm_hashes.get(session_id) == current_hash
    ontology_stable = getattr(ctx, 'ontology_delta', 0) == 0

    self._prev_wm_hashes[session_id] = current_hash

    # Tiered convergence: strongest guarantee first
    if goal_reached and mandatory_met and state_stable and ontology_stable:
        return ConvergenceResult(True, "FIXED_POINT", ctx.iteration_count, current_hash, 0)
    if goal_reached and mandatory_met and state_stable:
        # Working memory stable but async pipeline may still be running.
        # This is a valid convergence state — SEMANTIC deltas are non-blocking.
        return ConvergenceResult(True, "GOAL_REACHED_STABLE", ctx.iteration_count, current_hash, getattr(ctx, 'ontology_delta', 0))
    if goal_reached and mandatory_met:
        return ConvergenceResult(True, "GOAL_REACHED", ctx.iteration_count, current_hash, getattr(ctx, 'ontology_delta', 0))
    return ConvergenceResult(False, "PENDING", ctx.iteration_count, current_hash, getattr(ctx, 'ontology_delta', 0))
```

- Add `GOAL_REACHED_STABLE` as an intermediate convergence state: goal + mandatory + stable WM, but async pipeline still running.
- `GOAL_REACHED` should be sufficient for convergence — SEMANTIC deltas are supplementary, not mandatory.
- Document: "SEMANTIC deltas are non-blocking enhancements. Convergence does not require `ontology_stable` unless `FIXED_POINT` guarantee is explicitly requested."
- Add integration test: session with goal reached but async pipeline still running → converges on `GOAL_REACHED`, not `ITERATION_CAP`.

---

### 7. Async Post-Reasoning Lacks Dead-Letter Queue, Structlog, and Circuit Breaker — Phase 2 Regression

§4.3 — `run_post_reasoning()` uses bare `self.retry(exc=exc)` on all exceptions with:
- **No dead-letter queue** — after 3 retries, the failure is lost. No reprocessing possible. Phase 2 explicitly added `publish_dead_letter_event()`.
- **No `structlog` calls** — the Celery task doesn't emit any logging events. Phase 2 mandated `structlog` for all async tasks.
- **No circuit breaker** — if the ontology reasoner is down, every answer will trigger 3 retries × N concurrent tasks. Phase 2 added `@circuit(failure_threshold=5, recovery_timeout=60)` for Fuseki writes.
- **No `source_hash` / idempotency** — the task is keyed on `session_id + answer_index` but there's no content hash to prevent duplicate triple injection on retry.

**Suggestion:**

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_post_reasoning(self, session_id: str, rule_name: str, working_memory_snapshot: dict) -> dict:
    import structlog
    log = structlog.get_logger().bind(session_id=session_id, rule_name=rule_name, task_id=self.request.id)
    try:
        # 1. Persist conclusions to Fuseki
        new_triples = _persist_with_breaker(rule_name, session_id, working_memory_snapshot)
        # 2. Run OWL reasoner & fetch deltas
        delta_facts = _run_reasoner_with_timeout(timeout_seconds=10.0)
        # 3. Publish deltas as events (don't write to FactStore from worker)
        publish_ontology_delta_event(session_id, delta_facts)
        log.info("post_reasoning_success", delta_count=len(delta_facts))
        return {"session_id": session_id, "injected": len(delta_facts)}
    except OntologyTimeoutError as exc:
        log.warning("post_reasoning_timeout", error=str(exc), retry=self.request.retries)
        self.retry(exc=exc)
    except Exception as exc:
        log.error("post_reasoning_failed_permanently", error=str(exc))
        publish_dead_letter_event(session_id, rule_name, str(working_memory_snapshot)[:200], str(exc))
        raise

@circuit(failure_threshold=3, recovery_timeout=30)
def _persist_with_breaker(rule_name, session_id, snapshot):
    return OntologyPort.persist_conclusions(rule_name, session_id, snapshot)

def publish_ontology_delta_event(session_id: str, delta_facts) -> None:
    """Publish deltas to Redis list for main process consumption."""
    import json, redis
    r = redis.Redis()
    r.rpush(f"inferra:ontology_deltas:{session_id}", json.dumps({
        "session_id": session_id,
        "deltas": [(name, str(val)) for name, val in delta_facts],
        "timestamp": time.time()
    }))

def publish_dead_letter_event(session_id, rule_name, snapshot_preview, error):
    import json, redis
    r = redis.Redis()
    r.lpush("inferra:dead_letter_queue", json.dumps({
        "session_id": session_id, "rule_name": rule_name,
        "snapshot_preview": snapshot_preview, "error": error,
        "timestamp": time.time()
    }))
```

- Add DLQ matching Phase 2's pattern.
- Add `structlog` with mandatory fields (`session_id`, `rule_name`, `task_id`).
- Add circuit breaker with `failure_threshold=3, recovery_timeout=30` (same as Phase 4's LLM breaker — ontology is external dependency).
- Publish deltas as events rather than writing to `FactStore` directly (see enhancement #2).
- Add `GET /api/v1/ontology/status?session_id=` endpoint for client visibility.

---

### 8. QuestionStrategy Protocol Doesn't Match Data Flow

§4.5 — The `QuestionStrategy` protocol defines:

```python
def should_ask(self, node: Node, working_memory: Dict[str, FactValue]) -> bool: ...
```

But the sequence diagram (§2.2) shows:

```
Orch->>Strat: should_ask(node, working_memory)
Strat-->>Orch: Next Question
```

`should_ask()` returns a `bool`, not a "Next Question". The protocol doesn't match the data flow — there's no method to select/return the next question to ask. The orchestrator needs a way to ask "which question should I ask next?" not just "should I ask this one?"

**Suggestion:**

```python
# src/ports/question_strategy_port.py
from typing import Optional, Protocol, List
from src.domain.nodes.node import Node
from src.domain.fact_values import FactValue
from src.domain.session.inference_context import InferenceContext

class QuestionStrategy(Protocol):
    """Port contract for question selection and ranking.
    
    Phase 3 establishes two distinct operations:
    1. should_ask() — gating: is this node worth asking about?
    2. select_next() — ranking: which unanswered node should be asked first?
    """
    def should_ask(self, node: Node, working_memory: Dict[str, FactValue]) -> bool: ...
    def select_next(self, candidates: List[Node], context: InferenceContext) -> Optional[Node]: ...
    def rank_candidates(self, candidates: List[Node], context: InferenceContext) -> List[Node]: ...

# src/domain/question/strategies/conservative_strategy.py
class ConservativeQuestionStrategy:
    def should_ask(self, node: Node, working_memory: Dict[str, FactValue]) -> bool:
        return node.get_node_name() not in working_memory

    def select_next(self, candidates: List[Node], context: InferenceContext) -> Optional[Node]:
        ranked = self.rank_candidates(candidates, context)
        return ranked[0] if ranked else None

    def rank_candidates(self, candidates: List[Node], context: InferenceContext) -> List[Node]:
        return [c for c in candidates if self.should_ask(c, context.fact_store.get_unified_view())]
```

- Add `select_next()` method that returns the highest-priority unanswered node.
- `should_ask()` is a boolean gate; `select_next()` is the question-selection method.
- `ConservativeQuestionStrategy.select_next()` returns first unanswered node in topological order.
- Update sequence diagram to show `select_next()` call.
- Wire `BackwardChainOrchestrator` to call `strategy.select_next(candidates, ctx)` instead of iterating + `should_ask()`.

---

## 🟡 Important Enhancements (Should Consider for Phase 3)

### 9. Structured Logging Not Propagated from Phase 1/2 — Zero structlog Calls in Phase 3

Phase 1 established `structlog` with mandatory fields (`session_id`, `node_id`, `fact_source`, `correlation_id`). Phase 2 added fields (`rule_name`, `import_depth`, `propagation_depth`, `source_hash`) and mandatory logging events. Phase 3's code samples have **ZERO `structlog` calls** — not even `print()`. Every Phase 3 module must adopt the same logging standard.

**Suggestion:**
- Add `structlog` calls to all Phase 3 modules with the same mandatory fields.
- Add mandatory logging events specific to Phase 3:
  - Convergence: `convergence_check`, `convergence_achieved`, `convergence_cap_exceeded` (with `reason`, `iteration`, `wm_hash`, `ontology_delta`)
  - Session: `session_created`, `session_snapshot_created`, `session_converged`, `session_expired`
  - Ontology: `pre_reasoning_start`, `pre_reasoning_complete`, `post_reasoning_delta_injected` (with `delta_count`)
  - PROV-O: `prov_o_trace_generated` (with `triple_count`, `format`)
  - Strategy: `question_selected` (with `node_name`, `strategy_name`)
- Add Phase 3 fields to the correlation context: `convergence_reason`, `iteration_count`, `ontology_delta`.

---

### 10. API Contracts Missing for New Endpoints & No Error Schemas

§4.4/4.5 mention enriched `/summary`, `/trace`, and `/next-question` APIs but provides no YAML contract. Phase 1/2 established clear API contract formats with error response schemas. Phase 3 must follow the same standard.

**Suggestion:**

```yaml
GET /api/v1/inference/summary?session_id=&offset=&limit=
  Summary: Enriched session summary with fact provenance
  Returns:
    200:
      summary: [{ node_text, node_value, fact_source, origin_module? }]
      total_count: int
      offset: int
      limit: int
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }

GET /api/v1/inference/trace?session_id=&format=turtle
  Summary: PROV-O trace for a converged session
  Parameters:
    format: "turtle" | "json-ld" (default: "turtle")
  Returns:
    200:
      session_id: str
      format: str
      trace: str  # RDF content
      triple_count: int
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }
    422: { error_code: "SESSION_NOT_CONVERGED", message: "Trace requires a converged session" }

GET /api/v1/inference/next-question?session_id=
  Summary: Next question with enriched provenance and iterate progress
  Returns:
    200:
      questions: [{ text, value_type, origin_module?, fact_source? }]
      has_more: bool
      iterate_progress?: { answered: int, total: int }
      convergence_state?: { converged: bool, reason: str, iteration: int }
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }

GET /api/v1/ontology/status?session_id=
  Summary: Check if async post-reasoning has completed for a session
  Returns:
    200:
      session_id: str
      status: "pending" | "completed" | "failed"
      delta_count: int
      completed_at?: str (ISO 8601)
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }

GET /api/v1/health
  Summary: Extended health-check for Phase 3 dependencies
  Returns:
    200:
      status: "ok"
      redis: "ok"
      celery: "ok"
      fuseki: "ok"
      graph_init: true
      semantic_cache: { triples: 12345, memory_mb: 8.3, hit_rate: 0.92 }
      ontology_reasoner: "ok"
      version: "3.0.0"
    503:
      status: "degraded"
      ontology_reasoner: "unavailable"
```

- Add `format` parameter to `/trace` for Turtle vs JSON-LD toggle (§4.4 mentions this).
- Add `convergence_state` to `/next-question` for client-side progress tracking.
- Add `/ontology/status` endpoint matching Phase 2's `/sync/status` pattern.
- Extend `/health` for Phase 3's ontology reasoner dependency.

---

### 11. No Session Schema Migration for Phase 2 → Phase 3

Phase 1 established `CURRENT_SCHEMA_VERSION = 1`. Phase 2 bumped to `CURRENT_SCHEMA_VERSION = 2`. Phase 3 introduces `ConvergenceResult`, `SessionManager._snapshots`, `question_strategy_name`, `prov_o_trace`, `convergence_trace`, and `question_strategy` fields. Existing sessions from Phase 2 will lack:

- `convergence_state` in the session payload
- `question_strategy_name` (defaults to "conservative")
- `prov_o_trace` (defaults to None)
- `convergence_trace` (defaults to empty list)

**Suggestion:**

- Bump `CURRENT_SCHEMA_VERSION = 3`.
- Write Phase 2 → 3 migration:

```python
# In SessionPersistenceService._migrate_session()
if from_version < 3:
    # Phase 2 → 3: add convergence state, question strategy, PROV-O trace
    data.setdefault("convergence_state", {
        "converged": False,
        "reason": "PENDING",
        "iteration": 0
    })
    data.setdefault("question_strategy_name", "conservative")
    data.setdefault("prov_o_trace", None)
    data.setdefault("convergence_trace", [])
    data.setdefault("ontology_pre_reasoned", False)
```

- Add integration test: load a Phase 2 session, assert Phase 3 code handles it without error.
- Add backward-compat test: Phase 2 code reading a Phase 3 session should gracefully ignore unknown fields (`convergence_state`, `question_strategy_name`, `prov_o_trace`).

---

### 12. Feature Flag Matrix Is Incomplete & No Mid-Session Flip Tests

§5 CI/CD lists `HYBRID_ORCHESTRATOR={true,false}` and `ASYNC_POST_REASONING={true,false}`. Missing flags:
- `PROV_O_TRACE` — no test for what happens when this is `false`.
- `ENRICHED_API` — no test for what happens when this is `false`.
- No null/legacy fallback for `HYBRID_ORCHESTRATOR=false`.

Phase 1/2 established "feature flags are start-of-session sticky" — Phase 3 must test the same constraint for its new flags.

**Suggestion:**
- Add missing flags to CI matrix: `PROV_O_TRACE={true,false}`, `ENRICHED_API={true,false}`.
- Add `LegacyInferenceEngine` fallback for `HYBRID_ORCHESTRATOR=false`:
  - When `false`, bypass `BackwardChainOrchestrator` + `SessionManager` and use the Phase 2 `InferenceEngine` directly.
  - Document: "When `HYBRID_ORCHESTRATOR=false`, convergence logic falls back to Phase 2 inline checks."
- Add mid-session flip tests for all Phase 3 flags:
  - Start session with `ASYNC_POST_REASONING=false`, flip to `true`, assert Celery tasks are not published retroactively.
  - Start session with `PROV_O_TRACE=false`, flip to `true`, assert trace is not generated retroactively.
  - Start session with `ENRICHED_API=false`, flip to `true`, assert API responses gain provenance fields on next request.
- Document: "Phase 3 feature flags are start-of-session sticky, consistent with Phase 1/2 policy."

---

### 13. No Observability for Convergence Loop — Missing Metrics & Tracing

The convergence loop is the most critical component in Phase 3 but has no metrics, no tracing, and no logging (beyond the zero `structlog` calls noted in #9). When convergence fails in production, there will be no diagnostic data.

**Suggestion:**
- Add Prometheus-style metrics (or extend Phase 2's existing `/metrics` endpoint):

```python
from prometheus_client import Counter, Histogram, Gauge

convergence_total = Counter(
    "inferra_convergence_total", "Convergence loop outcomes",
    ["reason"]  # FIXED_POINT | GOAL_REACHED | GOAL_REACHED_STABLE | ITERATION_CAP | PENDING
)
convergence_iterations = Histogram(
    "inferra_convergence_iterations", "Iterations to convergence",
    buckets=[1, 2, 3, 5, 7, 10]
)
convergence_wm_hash_stability = Counter(
    "inferra_convergence_wm_hash_stability", "Working memory hash stability events",
    ["stable_or_changed"]  # stable | changed
)
ontology_post_reasoning_delta_count = Histogram(
    "inferra_ontology_post_reasoning_delta_count", "Ontology deltas injected per post-reasoning cycle",
    buckets=[0, 1, 3, 5, 10, 25, 50]
)
prov_o_triple_count = Histogram(
    "inferra_prov_o_triple_count", "PROV-O trace triple counts per session"
)
```

- Correlate convergence events with Phase 1's correlation-ID via `structlog.contextvars`.
- Add convergence-specific tracing spans in OpenTelemetry: `convergence.check`, `convergence.achieved`, `convergence.cap_exceeded`.

---

### 14. No Performance Baselines for Phase 3 Components

Phase 1 stored baselines in `benchmarks/baseline_v0.json`. Phase 2 stored baselines in `benchmarks/baseline_phase2.json`. Phase 3 introduces convergence loops, async post-reasoning, and PROV-O generation — all of which add latency overhead. The plan mentions P95 < +50ms but has no mechanism to establish or track baselines.

**Suggestion:**
- Run Phase 2 system through Phase 3 benchmarks before changes; store in `benchmarks/baseline_phase3.json`.
- Define benchmark scenarios:
  - Convergence loop: single-session convergence with 0/1/5 ontology deltas, measure iterations + wall time.
  - Async post-reasoning: 100 concurrent sessions, measure Celery task completion rate + delta injection latency.
  - PROV-O generation: 50 sessions with varying conclusion counts, measure trace generation time + triple count.
  - Full hybrid flow: init → pre-reason → ask → answer → post-reason → converge → trace.
- Fail CI if any benchmark regresses >10% from baseline.
- Validate P95 latency increase < 50ms vs Phase 2 baseline.

---

### 15. SessionManager._snapshots Grows Unbounded — No Eviction Policy

§4.2 — `SessionManager._snapshots` is a plain `Dict[str, InferenceContext]` with no maximum size, no TTL, and no eviction policy. Over time, completed sessions accumulate in memory, causing unbounded growth. The risk table mentions "LRU cache for snapshots (max 50/session)" but the implementation doesn't match.

**Suggestion:**

```python
from collections import OrderedDict
import time

class SessionManager:
    MAX_SNAPSHOTS = 1000
    SNAPSHOT_TTL_SECONDS = 86400  # 24 hours

    def __init__(self):
        self._snapshots: OrderedDict[str, InferenceContext] = OrderedDict()
        self._snapshot_timestamps: Dict[str, float] = {}
        self._prev_wm_hashes: Dict[str, str] = {}

    def _put_snapshot(self, session_id: str, ctx: InferenceContext) -> None:
        if len(self._snapshots) >= self.MAX_SNAPSHOTS:
            oldest = next(iter(self._snapshots))
            del self._snapshots[oldest]
            self._snapshot_timestamps.pop(oldest, None)
            self._prev_wm_hashes.pop(oldest, None)
        self._snapshots[session_id] = ctx
        self._snapshots.move_to_end(session_id)  # LRU
        self._snapshot_timestamps[session_id] = time.time()

    def _get_snapshot(self, session_id: str) -> Optional[InferenceContext]:
        if session_id not in self._snapshots:
            return None
        if time.time() - self._snapshot_timestamps.get(session_id, 0) > self.SNAPSHOT_TTL_SECONDS:
            del self._snapshots[session_id]
            self._snapshot_timestamps.pop(session_id, None)
            self._prev_wm_hashes.pop(session_id, None)
            return None
        self._snapshots.move_to_end(session_id)  # LRU
        return self._snapshots[session_id]

    def remove_snapshot(self, session_id: str) -> None:
        """Called on session close to prevent memory leaks."""
        self._snapshots.pop(session_id, None)
        self._snapshot_timestamps.pop(session_id, None)
        self._prev_wm_hashes.pop(session_id, None)
```

- Add LRU eviction with `MAX_SNAPSHOTS = 1000` and `SNAPSHOT_TTL_SECONDS = 86400`.
- Add `remove_snapshot()` for session teardown.
- Add `snapshot_count` property for observability.
- Log warning when approaching capacity (>80% of `MAX_SNAPSHOTS`).

---

### 16. BackwardChainOrchestrator Has No Null/Legacy Fallback for Feature Flag

§4.1 — `BackwardChainOrchestrator` is the new orchestration layer, but there's no `LegacyOrchestrator` or `NullOrchestrator` fallback when `HYBRID_ORCHESTRATOR=false`. Phase 1/2 established the pattern where every new component has a null/legacy fallback behind a feature flag. Without this:

- `HYBRID_ORCHESTRATOR=false` has no defined behaviour — what handles the convergence loop?
- Testing the hybrid orchestrator in isolation requires mocking the entire `InferenceEngine`.
- No graceful degradation path if the orchestrator has a bug.

**Suggestion:**

```python
# src/infrastructure/orchestrator_factory.py
import os, structlog

log = structlog.get_logger()

def create_orchestrator(engine, session_mgr, ontology, strategy):
    if os.getenv("HYBRID_ORCHESTRATOR", "false").lower() == "true":
        log.info("orchestrator_created", implementation="BackwardChainOrchestrator")
        return BackwardChainOrchestrator(engine, session_mgr, ontology, strategy)
    log.info("orchestrator_created", implementation="LegacyOrchestrator")
    return LegacyOrchestrator(engine)

# src/domain/inference/legacy_orchestrator.py
class LegacyOrchestrator:
    """Fallback orchestrator that delegates to Phase 2 InferenceEngine directly.
    Used when HYBRID_ORCHESTRATOR=false — provides backward-compatible convergence checks."""
    def __init__(self, engine: InferenceEngine):
        self.engine = engine

    async def run_convergence_loop(self, session_id: str, max_iterations: int = 10) -> ConvergenceResult:
        # Delegate to legacy inline convergence checks from Phase 2
        ctx = self.engine.get_context(session_id)
        if ctx.goal_reached and ctx.mandatory_met:
            return ConvergenceResult(True, "GOAL_REACHED", 0, "", 0)
        return ConvergenceResult(False, "PENDING", 0, "", 0)
```

- Feature flag `HYBRID_ORCHESTRATOR` controls which implementation is injected at session start.
- `LegacyOrchestrator` delegates to Phase 2's inline convergence logic.
- All API routes depend on the orchestrator port, never on `BackwardChainOrchestrator` directly.

---

## 🟢 Nice-to-Have Enhancements (Can Defer to Phase 4 but Worth Noting)

### 17. No SessionManagerPort Contract Test Suite

Phase 1 added `FactStorePort` contract tests. Phase 2 added `IterationPort` and `DependencyGraphPort` contract tests. Phase 3 introduces `SessionManager` with `check_convergence()`, snapshot lifecycle, and hash-based fixed-point detection — but has no port definition or contract tests.

**Suggestion:**
- Define `SessionManagerPort` Protocol:

```python
# src/ports/session_manager_port.py
from typing import Optional, Protocol

class SessionManagerPort(Protocol):
    def check_convergence(self, session_id: str, goal: str, mandatory: List[str]) -> ConvergenceResult: ...
    def create_snapshot(self, session_id: str, ctx: InferenceContext) -> None: ...
    def get_wm_hash(self, session_id: str) -> str: ...
    def get_ontology_delta(self, session_id: str) -> int: ...
    def remove_snapshot(self, session_id: str) -> None: ...
```

- Create `tests/contracts/test_session_manager_port.py` using `@pytest.mark.parametrize` over `[SessionManager]`.
- Test contract: `create_snapshot()` → `check_convergence()` → `remove_snapshot()` lifecycle.
- Test edge cases: check convergence on non-existent snapshot (raises), double-create (idempotent), hash stability for identical WM.

---

### 18. No Health-Check Extensions for Phase 3 Dependencies

Phase 1 added `GET /health` checking Redis + graph_init. Phase 2 extended for Celery, Fuseki, and SemanticCache. Phase 3 adds ontology pre/post-reasoning and convergence state — none reflected in health check.

**Suggestion:**

```yaml
GET /api/v1/health
  Returns:
    200:
      status: "ok"
      redis: "ok"
      celery: "ok"
      fuseki: "ok"
      graph_init: true
      semantic_cache: { triples: 12345, memory_mb: 8.3, hit_rate: 0.92 }
      ontology_reasoner: "ok"
      active_sessions: 42
      version: "3.0.0"
    503:
      status: "degraded"
      ontology_reasoner: "unavailable"
```

- Add `/health` check for ontology reasoner availability.
- Add `active_sessions` count from `SessionManager._snapshots`.
- Add degraded response when ontology reasoner is unavailable (non-critical dependency — convergence still works without it).

---

### 19. ConvergenceResult Should Include Snapshot Metadata for Debugging

The current `ConvergenceResult` has `working_memory_hash` and `ontology_delta` but no `session_id`, `session_duration_ms`, `strategy_used`, or `convergence_trace`. These are critical for debugging convergence issues in production.

**Suggestion:**

```python
@dataclass
class ConvergenceResult:
    converged: bool
    reason: str
    iteration: int
    working_memory_hash: str
    ontology_delta: int
    session_id: str = ""
    session_duration_ms: float = 0.0
    strategy_used: str = "conservative"
    convergence_trace: List[str] = field(default_factory=list)
```

- Add `session_id` for correlation with `structlog` events.
- Add `session_duration_ms` for latency tracking.
- Add `strategy_used` for debugging which strategy was active.
- Add `convergence_trace` (list of `reason` strings from each iteration) for debugging convergence path.
- These fields are non-breaking additions — Phase 2 code ignores them.

---

### 20. Sprint Schedule Is Aggressive & Lacks Buffer Days

Phase 1 (enhanced) added 2 buffer days and designated Friday as "buffer + polish." Phase 2 (enhanced) added 2 buffer days. Phase 3 reverts to 5 pure feature days with no buffer, despite Phase 3 being the most architecturally transformative phase (orchestration layering, convergence formalization, async post-reasoning, PROV-O generation).

**Suggestion:**
- Add 2 buffer days (same as Phase 1/2).
- Designate Friday as "buffer + polish + integration" rather than feature delivery.
- WS-3 (PROV-O & API) depends on stable convergence from WS-1 — consider staggering WS-3 to start Tuesday.
- WS-2 (Ontology) depends on external Fuseki/ontology reasoner — add a contingency: if the reasoner is not available by Tuesday, WS-2 switches to `NullOntologyAdapter`-based development.
- Add daily stand-up protocol with blocker escalation (same as Phase 1/2).

---

## Summary Matrix

| #  | Enhancement                                              | Severity     | Effort |
| -- | -------------------------------------------------------- | ------------ | ------ |
| 1  | Non-deterministic WM hash for fixed-point detection      | Critical     | Low    |
| 2  | Async post-reasoning writes without synchronisation      | Critical     | Medium |
| 3  | InferenceContext undefined attributes (runtime error)     | Critical     | Low    |
| 4  | ProvOTraceGenerator invalid RDF via string concat         | Critical     | Medium |
| 5  | BackwardChainOrchestrator has no thread-safety           | Critical     | Low    |
| 6  | Convergence criteria too strict (false ITERATION_CAP)    | Critical     | Low    |
| 7  | Async pipeline lacks DLQ, structlog, circuit breaker     | Critical     | Medium |
| 8  | QuestionStrategy protocol doesn't match data flow        | Critical     | Low    |
| 9  | Structured logging not propagated (zero structlog calls) | Important    | Low    |
| 10 | API contracts missing for new endpoints + error schemas   | Important    | Medium |
| 11 | Session schema migration Phase 2 → Phase 3              | Important    | Medium |
| 12 | Feature flag matrix incomplete + no mid-session flip tests| Important    | Low    |
| 13 | No observability for convergence loop                     | Important    | Medium |
| 14 | No performance baselines for Phase 3 components          | Important    | Low    |
| 15 | SessionManager._snapshots unbounded (no eviction)        | Important    | Low    |
| 16 | No null/legacy fallback for HYBRID_ORCHESTRATOR flag     | Important    | Low    |
| 17 | SessionManagerPort contract test suite                    | Nice-to-have | Medium |
| 18 | Health-check extensions for Phase 3 dependencies         | Nice-to-have | Low    |
| 19 | ConvergenceResult snapshot metadata for debugging        | Nice-to-have | Low    |
| 20 | Sprint buffer days + WS staggering                       | Nice-to-have | N/A    |

---

**The Phase 3 plan is architecturally ambitious and introduces the most critical structural change** — orchestration layering on top of the Phase 1/2 foundation. The primary concerns are:

1. **Runtime correctness** — undefined `InferenceContext` attributes, non-deterministic hashing, and the `QuestionStrategy` protocol/data-flow mismatch will cause `AttributeError`, false non-convergence, and broken question selection at runtime.

2. **Cross-process concurrency** — Celery workers writing directly to `FactStorePort` from a separate process is the most dangerous regression from Phase 1/2's explicit lock-based concurrency model. The orchestrator itself also lacks thread-safety.

3. **Convergence logic soundness** — the four-criteria AND conjunction is too strict for an async pipeline, guaranteeing `ITERATION_CAP` hits in production whenever post-reasoning is enabled. Tiered convergence with `GOAL_REACHED` as a sufficient condition is essential.

4. **Phase 2 regressions** — the async pipeline is missing DLQ, structlog, circuit breaker, and idempotency controls that Phase 2 explicitly added for the Fuseki sync pipeline. These must be carried forward.

5. **Under-specified components** — `InferenceContext`, `QuestionStrategy.select_next()`, `LegacyOrchestrator`, session schema migration, and API contracts for enriched endpoints need concrete definitions before sprint start.

I strongly recommend addressing items 1–8 before sprint kick-off, as they affect core correctness, runtime stability, and Phase 1/2 compatibility.
