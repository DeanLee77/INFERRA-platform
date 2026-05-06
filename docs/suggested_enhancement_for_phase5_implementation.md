# Suggested Enhancements for INFERRA Phase 5 Implementation Plan

> Review of `INFERRA_Phase5_Implementation_Plan.md` (v1.0) against Phase 1 (v3.0), Phase 2 (v3.0), Phase 3 (v4.0),
> and Phase 4 (v4.0) enhanced plans, architectural soundness, runtime robustness, operational readiness,
> spec completeness, and cross-phase consistency.

---

## 🔴 Critical Enhancements (Must Fix Before Sprint)

### 1. AbductionPort Is a Concrete Class, Not a Protocol — Port Architecture Violation

§4.1 — `AbductionPort` is defined as a concrete class with implementation logic embedded (`_find_unsatisfied_dependencies`, `_build_z3_constraints`, `_enumerate_and_rank`). Phase 1–4 established a strict port-based architecture where core depends only on Protocol interfaces, and concrete implementations live in `src/adapters/`. `AbductionPort` should be a `Protocol` (like `FactStorePort`, `SessionStorePort`, `LLMOrchestratorPort`), with the Z3 implementation as a separate adapter.

This violation makes it impossible to:
- Swap Z3 for an alternative solver (e.g., custom SAT, local LLM-based abduction).
- Test the router without a real Z3 dependency.
- Provide a `NullAbductionAdapter` for `ABDUCTION_ENABLED=false`.

**Suggestion:**

```python
# src/ports/abduction_port.py
from typing import Dict, List, Optional, Protocol
from src.domain.reasoning.hypothesis import Hypothesis

class AbductionPort(Protocol):
    """Port contract for abduction (diagnostic hypothesis generation).
    Any implementation must satisfy these methods."""
    def propose_hypotheses(self, target: str, working_memory: Dict, graph: HyperAdjacencyGraph) -> List[Hypothesis]: ...

# src/adapters/outbound/reasoning/z3_abduction_adapter.py
class Z3AbductionAdapter:
    """Production abduction adapter using Z3 constraint solver.
    Includes timeout, model enumeration cap, and depth pruning."""
    MAX_MODELS = 50
    SOLVER_TIMEOUT_MS = 2000

    def propose_hypotheses(self, target: str, working_memory: Dict, graph: HyperAdjacencyGraph) -> List[Hypothesis]:
        missing = self._find_unsatisfied_dependencies(target, working_memory, graph)
        solver = self._build_z3_constraints(missing, graph)
        return self._enumerate_and_rank(solver, missing, working_memory)

# src/adapters/outbound/reasoning/null_abduction_adapter.py
class NullAbductionAdapter:
    """Null adapter for ABDUCTION_ENABLED=false. Returns empty hypothesis list."""
    def propose_hypotheses(self, target, working_memory, graph):
        return []
```

- Add `AbductionPort` Protocol matching Phase 1's `FactStorePort` pattern.
- Add `NullAbductionAdapter` for `ABDUCTION_ENABLED=false`.
- Add `MockAbductionAdapter` for deterministic testing.
- All routes depend on `AbductionPort`, never on `Z3AbductionAdapter` directly.
- Feature flag `ABDUCTION_ENABLED` controls which implementation is injected.

---

### 2. Z3 Constraint Solver Has No Timeout, No Depth Guard, No Model Enumeration Cap

§4.1 — `propose_hypotheses()` calls `self._enumerate_and_rank(solver, ...)` with:
- **No timeout** — if the constraint system is complex (many AND/OR/MANDATORY combinations), Z3 can hang indefinitely or take minutes.
- **No model enumeration cap** — `enumerate_and_rank` could produce thousands of models for an under-constrained system. The risk table mentions "max 50" but the code doesn't enforce it.
- **No depth guard** — `_find_unsatisfied_dependencies` traverses the `HyperAdjacencyGraph` with no cycle/distance limit. Phase 1 added `CyclicGraphError` + `max_steps` to `back_propagate()`. The abduction traversal must respect the same guard.
- This is a Phase 1 regression — cycle-protected BFS was explicitly added to `HyperAdjacencyGraph.back_propagate()`.

**Suggestion:**

```python
class Z3AbductionAdapter:
    MAX_MODELS = 50
    SOLVER_TIMEOUT_MS = 2000
    MAX_DEPENDENCY_DEPTH = 10

    def propose_hypotheses(self, target: str, working_memory: Dict, graph: HyperAdjacencyGraph) -> List[Hypothesis]:
        # Delegate dependency traversal to graph.back_propagate() with cycle guard
        impacted = graph.back_propagate(target, max_steps=self.MAX_DEPENDENCY_DEPTH * 2)
        missing = [n for n in impacted if n not in working_memory]
        if not missing:
            return []

        solver = self._build_z3_constraints(missing, graph)
        solver.set("timeout", self.SOLVER_TIMEOUT_MS)

        models = []
        while len(models) < self.MAX_MODELS:
            result = solver.check()
            if result == z3.unsat or result == z3.unknown:
                break
            model = solver.model()
            models.append(self._model_to_hypothesis(model, missing))
            solver.add(z3.Or([var != val for var, val in self._model_decls(model)]))

        return self._rank_by_confidence(models)
```

- Use `solver.set("timeout", 2000)` to cap Z3 execution at 2 seconds.
- Enforce `MAX_MODELS = 50` hard cap on model enumeration.
- Delegate graph traversal to `graph.back_propagate()` which has Phase 1's `CyclicGraphError` guard.
- Add `MAX_DEPENDENCY_DEPTH = 10` to prevent traversing the entire graph.

---

### 3. ReasoningRouter Can Bypass Deduction Without Actually Attempting It First

§4.3 — The router checks `convergence.reason == "MISSING_MANDATORY"` and immediately jumps to abduction:

```python
if convergence.reason == "MISSING_MANDATORY":
    hypotheses = self.abduction.propose(...)
```

But this doesn't verify that deduction has actually been attempted. If the router is called before the convergence loop runs (e.g., on session creation, or after a single `/feed-answer`), it will jump straight to abduction for any session with missing mandatory facts — even those the user hasn't been asked about yet.

The router should only invoke abduction when:
1. The convergence loop has run at least once with the current state.
2. All askable questions have been asked (i.e., `QuestionStrategy.select_next()` returns `None`).
3. The session is genuinely "stalled" — not just "early in the process."

**Suggestion:**

```python
class ReasoningRouter:
    MIN_DEDUCTION_ITERATIONS_BEFORE_ABDUCTION = 2  # At least 2 deduction attempts

    def route(self, session_state: InferenceContext, convergence: ConvergenceResult,
              has_unasked_questions: bool = True) -> RoutingDecision:
        if convergence.converged:
            return RoutingDecision("DEDUCTION", 1.0, "RETURN_RESULT")

        # Never bypass deduction if there are still questions to ask
        if has_unasked_questions:
            return RoutingDecision("DEDUCTION", 0.9, "CONTINUE_LOOP")

        # Only attempt abduction after minimum deduction iterations
        if (convergence.reason in ("MISSING_MANDATORY", "PENDING")
            and convergence.iteration >= self.MIN_DEDUCTION_ITERATIONS_BEFORE_ABDUCTION
            and not has_unasked_questions):
            if self.abduction_enabled:
                hypotheses = self.abduction.propose_hypotheses(
                    session_state.target,
                    session_state.fact_store.get_unified_view(),
                    session_state.graph
                )
                if hypotheses and hypotheses[0].confidence >= self.confidence_threshold:
                    return RoutingDecision("ABDUCTION", hypotheses[0].confidence, "INJECT_HYPOTHESIS")
            return RoutingDecision("DEDUCTION", 0.5, "REQUEST_USER_INPUT", fallback=True)

        return RoutingDecision("DEDUCTION", 0.9, "CONTINUE_LOOP")
```

- Add `has_unasked_questions` parameter — router checks if `QuestionStrategy.select_next()` returns `None`.
- Add `MIN_DEDUCTION_ITERATIONS_BEFORE_ABDUCTION = 2` — abduction only attempted after at least 2 deduction iterations.
- Add `self.abduction_enabled` flag check — consistent with `ABDUCTION_ENABLED` feature flag.
- Add test: session with unasked questions → router always returns `CONTINUE_LOOP`, never `ABDUCTION`.

---

### 4. Induction Pipeline Has No DLQ, No Structlog, No Circuit Breaker — Phase 2/3/4 Regression

§4.2 — `run_induction_batch()` uses bare `self.retry(exc=exc)` on all exceptions with:
- **No dead-letter queue** — after 2 retries, the failure is lost. Phase 2 explicitly added `publish_dead_letter_event()` for the async sync pipeline, and Phase 3 added it for the post-reasoning pipeline.
- **No `structlog` calls** — the Celery task doesn't emit any logging events. Phase 2 mandated `structlog` for all async tasks.
- **No circuit breaker** — if the PROV-O trace source (Fuseki) is down, every induction batch will trigger 2 retries × N concurrent tasks. Phase 2 added `@circuit(failure_threshold=5, recovery_timeout=60)` for Fuseki writes; Phase 3 added `@circuit(failure_threshold=3, recovery_timeout=30)` for ontology writes.
- **No `source_hash` / idempotency** — duplicate batch submissions for the same session IDs will produce duplicate candidate rules.

**Suggestion:**

```python
@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def run_induction_batch(self, session_ids: List[str], rule_name: str) -> dict:
    import structlog
    log = structlog.get_logger().bind(rule_name=rule_name, task_id=self.request.id,
                                       session_count=len(session_ids))
    try:
        patterns = _extract_with_breaker(session_ids)
        candidates = RuleCompiler.compile_to_inferra_syntax(patterns)
        validated = [c for c in candidates if RuleValidationService.validate(c.text, rule_name).valid]
        log.info("induction_batch_success", candidate_count=len(validated),
                 total_candidates=len(candidates))
        return {"job_id": self.request.id, "candidates": len(validated), "status": "REVIEW"}
    except FusekiConnectionError as exc:
        log.warning("induction_batch_fuseki_failed", retry=self.request.retries)
        self.retry(exc=exc)
    except Exception as exc:
        log.error("induction_batch_failed_permanently", error=str(exc))
        publish_dead_letter_event("induction", rule_name, str(session_ids)[:200], str(exc))
        raise

@circuit(failure_threshold=3, recovery_timeout=30)
def _extract_with_breaker(session_ids):
    return TraceMiner.extract_decision_paths(session_ids)
```

- Add DLQ matching Phase 2/3's pattern.
- Add `structlog` with mandatory fields (`rule_name`, `task_id`, `session_count`).
- Add circuit breaker with `failure_threshold=3, recovery_timeout=30` on Fuseki reads.
- Add idempotency: hash session_ids + rule_name as deduplication key.

---

### 5. FactSource.HYPOTHETICAL and LEARNED Have No Truth-Maintenance Integration

§4.4 — The `FactSource` enum is extended with `HYPOTHETICAL` and `LEARNED`, but Phase 1's `LayeredFactStore` established a strict layer-precedence model (`ASSERTED > INFERRED > SEMANTIC`) with truth-maintenance (`_overrides` set, `invalidate_layer()`, `get_fact_sources()`). Phase 5 introduces two new layers without defining:

- **Precedence order**: Where do `HYPOTHETICAL` and `LEARNED` fall? If `HYPOTHETICAL` is below `INFERRED`, a subsequent deduction-run will overwrite the hypothesis. If above, hypotheses override inferred facts — which is semantically wrong.
- **Truth-maintenance**: What happens when a `HYPOTHETICAL` fact is later `ASSERTED` by the user? The `_overrides` set should track this.
- **Invalidation**: When should `HYPOTHETICAL` facts be invalidated? After a successful convergence? After a new `ASSERTED` answer?
- **`get_unified_view()` merge order**: The current `{**semantic, **inferred, **asserted}` merge must be extended.

**Suggestion:**

```python
class FactSource(Enum):
    ASSERTED = "ASSERTED"       # User input — highest precedence
    INFERRED = "INFERRED"       # Rule engine / iterate conclusions
    HYPOTHETICAL = "HYPOTHETICAL"  # Abduction — below INFERRED, above SEMANTIC
    LEARNED = "LEARNED"           # Induction (after promotion) — same as INFERRED
    SEMANTIC = "SEMANTIC"       # Ontology-derived — lowest precedence

# LayeredFactStore.get_unified_view() merge order (lowest to highest):
# {**semantic, **learned, **hypothetical, **inferred, **asserted}
```

- `HYPOTHETICAL` sits between `SEMANTIC` and `INFERRED` — hypotheses are weaker than deductions but stronger than ontology facts.
- `LEARNED` is equivalent to `INFERRED` — promoted induction rules produce inferred conclusions.
- When `ASSERTED` overwrites a `HYPOTHETICAL` fact, add to `_overrides` set (Phase 1 truth-maintenance).
- Add `invalidate_hypotheses(session_id)` method called after convergence — clear `HYPOTHETICAL` layer once session converges (hypotheses are no longer needed).
- Add test: `ASSERTED` overwrites `HYPOTHETICAL` → `get_unified_view()` returns `ASSERTED` value.
- Add test: `invalidate_hypotheses()` clears only `HYPOTHETICAL` layer.

---

### 6. Sandbox Promoted Rules Skip Phase 1's RuleValidationService Gate

§4.2 / §2.2 — The sandbox approval workflow promotes rules to `RuleDB`:

```
Sand->>RuleDB: Persist + publish RuleUpdated
```

But the acceptance criteria says "validates via `RuleValidationService`" only for induction candidates, not for sandbox-promoted rules. If a human approves a syntactically-invalid or cyclic candidate, it will be persisted and crash the next session that imports it. Phase 1 established `RuleValidationService` as a **synchronous pre-save gate** that blocks persistence on `valid=False`. The sandbox must enforce the same gate.

**Suggestion:**

```python
class RuleSandbox:
    def promote(self, candidate_id: str, approver_id: str) -> PromotionResult:
        candidate = self._store.get(candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_id)

        # Phase 1's validation gate — MANDATORY before any persistence
        validation = RuleValidationService.validate(candidate.text, candidate.rule_name)
        if not validation.valid:
            log.warning("sandbox_promotion_blocked", candidate_id=candidate_id,
                        errors=validation.errors)
            return PromotionResult(promoted=False, reason="VALIDATION_FAILED",
                                   errors=validation.errors)

        # Phase 2's import resolution — detect transitive cycles
        try:
            resolved = RuleSetImportResolver.resolve(candidate.rule_name, ModuleRegistry())
        except CircularImportError as exc:
            return PromotionResult(promoted=False, reason="CIRCULAR_IMPORT", errors=[str(exc)])

        # Persist and publish
        self._rule_db.save(candidate.rule_name, candidate.text)
        publish_rule_updated_event(candidate.rule_name, candidate.text)
        log.info("sandbox_rule_promoted", candidate_id=candidate_id, approver=approver_id,
                 rule_name=candidate.rule_name)
        return PromotionResult(promoted=True, rule_name=candidate.rule_name)
```

- Enforce `RuleValidationService.validate()` on every sandbox promotion — even human-approved rules must pass the gate.
- Enforce `RuleSetImportResolver` — detect transitive import cycles before persistence.
- Add `PromotionResult` with `promoted`, `reason`, and `errors` fields.
- Add test: promote an invalid rule → blocked with `VALIDATION_FAILED`.
- Add test: promote a rule with circular import → blocked with `CIRCULAR_IMPORT`.

---

### 7. No Concurrency Model for Abduction — Concurrent Hypothesis Injection Races

§4.1/§4.3 — The `ReasoningRouter` can inject `HYPOTHETICAL` facts into `LayeredFactStore` while:
- The convergence loop is reading `get_unified_view()`.
- A `/feed-answer` handler is writing `ASSERTED` facts.
- The async post-reasoning consumer is injecting `SEMANTIC` deltas.

Phase 1 added `asyncio.Lock` to `IterateLine`. Phase 2 added `asyncio.Lock` to `IterationEngine`. Phase 3 added `asyncio.Lock` to `BackwardChainOrchestrator`. Phase 5's router and abduction adapter have **zero concurrency protection**.

**Suggestion:**

- The `ReasoningRouter` should use the same session lock as `BackwardChainOrchestrator` — inject `HYPOTHETICAL` facts under the orchestrator's lock.
- `propose_hypotheses()` should be read-only (reads working memory and graph, returns hypotheses without side effects).
- Injection of `HYPOTHETICAL` facts should happen inside `run_convergence_loop()` under the existing lock:

```python
# In BackwardChainOrchestrator.run_convergence_loop()
async with self._lock:
    res = self.session_mgr.check_convergence(session_id)
    if not res.converged and self.router.should_attempt_abduction(res, has_unasked_questions):
        hypotheses = self.abduction.propose_hypotheses(...)
        if hypotheses and hypotheses[0].confidence >= threshold:
            self._store.set_fact(hypotheses[0].fact_name, hypotheses[0].suggested_value,
                                 source=FactSource.HYPOTHETICAL)
            # Re-check convergence after injection
            res = self.session_mgr.check_convergence(session_id)
```

- Document: "Abduction is read-only (proposal phase). Hypothesis injection happens under the orchestrator's session lock. No concurrent mutation of LayeredFactStore from the router."

---

### 8. InferenceContext Not Extended for Phase 5 Fields

Phase 3 defined `InferenceContext` with `iteration_count`, `ontology_delta`, `question_strategy_name`, `prov_o_trace`, etc. Phase 5 introduces `reasoning_mode`, `confidence`, `hypothesis_trace`, and `induction_job_id` — none of which are reflected in `InferenceContext`. The router and API responses reference these fields but the data model doesn't define them.

**Suggestion:**

```python
# Extend InferenceContext for Phase 5
@dataclass
class InferenceContext:
    # ... Phase 3 fields ...
    reasoning_mode: str = "DEDUCTION"  # DEDUCTION | ABDUCTION | INDUCTION
    confidence: float = 1.0
    hypothesis_trace: List[Hypothesis] = field(default_factory=list)
    induction_job_id: Optional[str] = None
    abduction_attempted: bool = False
    abduction_count: int = 0
```

- Add `reasoning_mode` — tracks current mode for API responses and PROV-O trace.
- Add `confidence` — session-level confidence score.
- Add `hypothesis_trace` — list of all hypotheses proposed for this session (audit trail).
- Add `induction_job_id` — links to background induction batch if triggered.
- Add `abduction_attempted` / `abduction_count` — prevents infinite abduction retries and provides observability.

---

## 🟡 Important Enhancements (Should Consider for Phase 5)

### 9. Structured Logging Not Propagated — Zero structlog Calls in Phase 5

Phase 1 established `structlog` with mandatory fields. Phase 2 added Phase 2–specific events. Phase 3 added convergence events. Phase 4 added LLM events. Phase 5's code samples have **ZERO `structlog` calls**.

**Suggestion:**
- Add `structlog` calls to all Phase 5 modules.
- Add mandatory logging events:
  - Abduction: `abduction_propose_start`, `abduction_propose_complete` (with `hypothesis_count`, `best_confidence`, `solver_time_ms`), `abduction_hypothesis_injected` (with `fact_name`, `confidence`)
  - Induction: `induction_batch_start`, `induction_batch_success`, `induction_batch_failed`, `induction_candidate_promoted` (with `rule_name`, `approver_id`)
  - Router: `reasoning_route` (with `mode`, `confidence`, `action`, `fallback`)
  - Sandbox: `sandbox_candidate_submitted`, `sandbox_candidate_approved`, `sandbox_candidate_rejected`, `sandbox_candidate_promoted`
- Add Phase 5 fields to correlation context: `reasoning_mode`, `confidence`, `hypothesis_count`.

---

### 10. API Contracts Missing for New Endpoints & No Error Schemas

§4.1/§4.2 mention `/reasoning/abduct`, `/reasoning/induce/start`, `/reasoning/induce/status/{job_id}` but provide no YAML contract. Phase 1–4 established clear API contract formats with error response schemas.

**Suggestion:**

```yaml
POST /api/v1/reasoning/abduct
  Summary: Propose abduction hypotheses for a stalled session
  Authentication: Required when AUTH_ENABLED=true
  Rate Limit: 5/minute per user
  Body:
    session_id: str (required)
    target_node: str? (optional, defaults to session target)
    max_hypotheses: int? (optional, default 10, max 50)
  Returns:
    200:
      session_id: str
      hypotheses: [{ fact_name, suggested_value, confidence, dependency_path, ontology_consistent }]
      best_confidence: float
      injected: bool
    400: { error_code: "INVALID_INPUT", message: "..." }
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }
    422: { error_code: "SESSION_NOT_STALLED", message: "Abduction requires a stalled session" }
    503: { error_code: "ABDUCTION_UNAVAILABLE", message: "Z3 solver not available or timed out" }

POST /api/v1/reasoning/induce/start
  Summary: Start an async induction batch from PROV-O traces
  Authentication: Required when AUTH_ENABLED=true
  Rate Limit: 2/hour per user
  Body:
    session_ids: List[str] (required, min 10, max 1000)
    rule_name: str? (optional, scope to specific rule)
  Returns:
    202:
      job_id: str
      status: "PENDING"
      session_count: int
    400: { error_code: "INVALID_INPUT", message: "session_ids must contain 10-1000 items" }
    429: { error_code: "RATE_LIMITED", message: "Induction batch already running for this rule" }

GET /api/v1/reasoning/induce/status/{job_id}
  Summary: Get induction batch job status
  Returns:
    200:
      job_id: str
      status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED"
      candidates_total?: int
      candidates_valid?: int
      candidates_review?: int
      error?: str
    404: { error_code: "JOB_NOT_FOUND", message: "..." }
```

- Add rate limiting headers: `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- Add `Idempotency-Key` header support on `/reasoning/abduct`.

---

### 11. No Session Schema Migration for Phase 4 → Phase 5

Phase 4 established `CURRENT_SCHEMA_VERSION = 4`. Phase 5 introduces `reasoning_mode`, `confidence`, `hypothesis_trace`, `induction_job_id`, `FactSource.HYPOTHETICAL`, and `FactSource.LEARNED`. Existing sessions from Phase 4 will lack these fields.

**Suggestion:**
- Bump `CURRENT_SCHEMA_VERSION = 5`.
- Write Phase 4 → 5 migration:

```python
if from_version < 5:
    data.setdefault("reasoning_mode", "DEDUCTION")
    data.setdefault("confidence", 1.0)
    data.setdefault("hypothesis_trace", [])
    data.setdefault("induction_job_id", None)
    data.setdefault("abduction_attempted", False)
    data.setdefault("abduction_count", 0)
    # Extend fact_sources dict to handle new layers
    for name, source in data.get("fact_sources", {}).items():
        if source not in ("ASSERTED", "INFERRED", "SEMANTIC", "HYPOTHETICAL", "LEARNED"):
            data["fact_sources"][name] = "INFERRED"  # Safe default for unknown sources
```

- Add integration test: load a Phase 4 session, assert Phase 5 code handles it without error.

---

### 12. Feature Flag Matrix Is Incomplete & No Mid-Session Flip Tests

§5 CI/CD lists `ABDUCTION_ENABLED={true,false}`, `INDUCTION_PIPELINE={true,false}`, `REASONING_ROUTER={true,false}`, `CONFIDENCE_THRESHOLDS={true,false}` — but there are no mid-session flip tests. Phase 1–4 established "feature flags are start-of-session sticky."

**Suggestion:**
- Add mid-session flip tests:
  - Start session with `ABDUCTION_ENABLED=false`, flip to `true`, assert abduction is not attempted retroactively.
  - Start session with `REASONING_ROUTER=false`, flip to `true`, assert router is not instantiated retroactively.
  - Start session with `CONFIDENCE_THRESHOLDS=false`, flip to `true`, assert confidence gating doesn't affect existing hypotheses.
- Add `NullReasoningRouter` fallback for `REASONING_ROUTER=false` — always returns `RoutingDecision("DEDUCTION", 1.0, "CONTINUE_LOOP")`.
- Document: "Phase 5 feature flags are start-of-session sticky, consistent with Phase 1–4 policy."

---

### 13. No Observability for Abduction/Induction — Missing Prometheus Metrics

The abduction engine and induction pipeline are major new computational components with no metrics, no tracing, and no cost tracking. When production issues arise (hypothesis explosion, induction drift, solver timeouts), there will be no diagnostic data.

**Suggestion:**

```python
from prometheus_client import Counter, Histogram, Gauge

abduction_total = Counter(
    "inferra_abduction_total", "Abduction proposals",
    ["status"]  # success | timeout | no_hypotheses | circuit_open
)
abduction_latency_seconds = Histogram(
    "inferra_abduction_latency_seconds", "Abduction solver latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)
abduction_hypothesis_count = Histogram(
    "inferra_abduction_hypothesis_count", "Hypotheses per abduction call",
    buckets=[1, 5, 10, 25, 50]
)
abduction_confidence_score = Histogram(
    "inferra_abduction_confidence_score", "Abduction confidence scores",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
)
induction_batch_total = Counter(
    "inferra_induction_batch_total", "Induction batch jobs",
    ["status"]  # success | failed | timeout
)
induction_candidate_count = Histogram(
    "inferra_induction_candidate_count", "Induction candidates per batch"
)
induction_promotion_total = Counter(
    "inferra_induction_promotion_total", "Rule promotions from sandbox",
    ["status"]  # promoted | blocked | rejected
)
reasoning_mode_total = Counter(
    "inferra_reasoning_mode_total", "Reasoning mode selections",
    ["mode"]  # DEDUCTION | ABDUCTION | INDUCTION
)
```

- Correlate with Phase 1's correlation-ID via `structlog.contextvars`.
- Add OTel spans: `abduction.propose`, `induction.batch`, `induction.promote`, `router.route`.

---

### 14. No Performance Baselines for Phase 5 Components

Phase 1–4 stored baselines in `benchmarks/baseline_v0.json` through `baseline_phase4.json`. Phase 5 introduces Z3 constraint solving, trace mining, and rule compilation — all computationally expensive. The plan mentions targets but has no mechanism to track them.

**Suggestion:**
- Store in `benchmarks/baseline_phase5.json`:
  - Abduction: 100/500/1000 node graphs, measure solver latency + model count + memory.
  - Induction: 50/200/1000 sessions, measure extraction latency + candidate count.
  - Router: overhead of routing decision vs direct deduction (<10ms target).
  - Full tri-modal flow: deduction stall → abduction → converge → induction → promotion.
- Fail CI if any benchmark regresses >10% from baseline.

---

### 15. Confidence Threshold 0.7 Is Hardcoded — Should Be Configurable

§4.3 — The confidence threshold of `0.7` is hardcoded in the router. Different domains may require different thresholds (e.g., medical reasoning may need `0.95`, tax reasoning may tolerate `0.6`).

**Suggestion:**
- Make threshold configurable via `CONFIDENCE_THRESHOLD` environment variable (default `0.7`).
- Add `per-rule threshold override` — rules can declare `inf:minConfidence "0.85"^^xsd:decimal`.
- Add `per-session threshold override` — session creation can specify threshold.
- Precedence: session > rule > global default.
- Add test: threshold = 0.9 → hypotheses with confidence 0.8 are rejected.

---

### 16. No NullReasoningRouter Fallback for REASONING_ROUTER=false

Phase 1–4 established the pattern where every new component has a null/legacy fallback behind a feature flag. `ReasoningRouter` has no `NullReasoningRouter` fallback — what happens when `REASONING_ROUTER=false`?

**Suggestion:**

```python
# src/domain/reasoning/null_router.py
class NullReasoningRouter:
    """Fallback router for REASONING_ROUTER=false.
    Always returns DEDUCTION mode — no abduction or induction attempted."""
    def route(self, session_state, convergence, has_unasked_questions=True):
        if convergence.converged:
            return RoutingDecision("DEDUCTION", 1.0, "RETURN_RESULT")
        return RoutingDecision("DEDUCTION", 0.9, "CONTINUE_LOOP")

# src/infrastructure/router_factory.py
def create_router(abduction, induction):
    if os.getenv("REASONING_ROUTER", "true").lower() == "true":
        return ReasoningRouter(abduction, induction)
    return NullReasoningRouter()
```

---

## 🟢 Nice-to-Have Enhancements (Can Defer to Phase 6 but Worth Noting)

### 17. No AbductionPort Contract Test Suite

Phase 1 added `FactStorePort` contract tests. Phase 2 added `IterationPort` and `DependencyGraphPort` contract tests. Phase 3 added `SessionManagerPort` contract tests. Phase 5 introduces `AbductionPort` — equivalent contract tests are required.

**Suggestion:**
- Create `tests/contracts/test_abduction_port.py` using `@pytest.mark.parametrize` over `[Z3AbductionAdapter, NullAbductionAdapter, MockAbductionAdapter]`.
- Test contract: `propose_hypotheses()` returns `List[Hypothesis]` with valid `confidence` range [0.0, 1.0].
- Test edge cases: no missing dependencies → empty list; timeout → returns partial results; model explosion → capped at `MAX_MODELS`.

---

### 18. No InductionPort Contract Test Suite

Same pattern as enhancement #17 for `InductionPort`.

**Suggestion:**
- Create `tests/contracts/test_induction_port.py` using `@pytest.mark.parametrize` over `[CeleryInductionAdapter, NullInductionAdapter, MockInductionAdapter]`.
- Test contract: `start_batch()` returns `job_id`; `get_status()` returns valid status; `promote()` validates before persisting.

---

### 19. No Health-Check Extensions for Phase 5 Dependencies

Phase 1 added `GET /health` checking Redis + graph_init. Phase 2 extended for Celery, Fuseki, SemanticCache. Phase 3 extended for ontology reasoner. Phase 5 adds Z3 solver and induction worker status — none reflected.

**Suggestion:**

```yaml
GET /api/v1/health
  Returns:
    200:
      status: "ok"
      # ... Phase 4 fields ...
      z3_solver: "ok"
      induction_workers: { active: 2, pending_jobs: 5 }
      version: "5.0.0"
    503:
      status: "degraded"
      z3_solver: "unavailable"
```

- Add Z3 solver availability check.
- Add induction worker pool status.
- Mark Z3 as non-critical dependency (degraded, not down).

---

### 20. Sprint Schedule Is Aggressive & Lacks Buffer Days

Phase 1 (enhanced) added 2 buffer days. Phase 2 added 2 buffer days. Phase 3 added 2 buffer days. Phase 5 reverts to 5 pure feature days with no buffer, despite Phase 5 being the most computationally complex phase (Z3 constraint solving, trace mining, rule compilation, sandbox workflows, human-in-the-loop).

**Suggestion:**
- Add 2 buffer days (same as Phase 1–3).
- Designate Friday as "buffer + polish + integration" rather than feature delivery.
- WS-1 (Abduction) depends on Z3 library availability — add contingency: if Z3 cannot be installed in CI by Tuesday, WS-1 switches to `MockAbductionAdapter`-based development.
- WS-2 (Induction) depends on sufficient PROV-O trace data — add contingency: if trace data is insufficient, WS-2 switches to synthetic trace generation.
- Add daily stand-up protocol with blocker escalation (same as Phase 1–3).

---

## Summary Matrix

| #  | Enhancement                                              | Severity     | Effort |
| -- | -------------------------------------------------------- | ------------ | ------ |
| 1  | AbductionPort is concrete class, not Protocol            | Critical     | Low    |
| 2  | Z3 solver has no timeout, depth guard, model cap        | Critical     | Medium |
| 3  | Router bypasses deduction without attempting it first    | Critical     | Low    |
| 4  | Induction pipeline lacks DLQ, structlog, circuit breaker | Critical     | Medium |
| 5  | HYPOTHETICAL/LEARNED have no truth-maintenance          | Critical     | Medium |
| 6  | Sandbox promoted rules skip validation gate              | Critical     | Low    |
| 7  | No concurrency model for abduction hypothesis injection  | Critical     | Medium |
| 8  | InferenceContext not extended for Phase 5 fields         | Critical     | Low    |
| 9  | Structured logging not propagated (zero structlog calls) | Important    | Low    |
| 10 | API contracts missing for new endpoints + error schemas  | Important    | Medium |
| 11 | Session schema migration Phase 4 → Phase 5              | Important    | Medium |
| 12 | Feature flag matrix incomplete + no mid-session flip     | Important    | Low    |
| 13 | No observability for abduction/induction                 | Important    | Medium |
| 14 | No performance baselines for Phase 5 components          | Important    | Low    |
| 15 | Confidence threshold 0.7 hardcoded, not configurable   | Important    | Low    |
| 16 | No NullReasoningRouter fallback for feature flag         | Important    | Low    |
| 17 | AbductionPort contract test suite                        | Nice-to-have | Medium |
| 18 | InductionPort contract test suite                        | Nice-to-have | Medium |
| 19 | Health-check extensions for Phase 5 deps                 | Nice-to-have | Low    |
| 20 | Sprint buffer days + WS staggering                        | Nice-to-have | N/A    |

---

**The Phase 5 plan is architecturally ambitious and introduces the most significant reasoning extensions.** The primary concerns are:

1. **Port architecture violations** — `AbductionPort` is a concrete class, not a Protocol. This breaks the non-negotiable port-based isolation established across Phases 1–4. Both `AbductionPort` and `InductionPort` must be Protocols with null/mock/real implementations.

2. **Computational safety** — the Z3 solver has no timeout, no model cap, and no depth guard. In production, a complex rule set can cause the solver to hang indefinitely or produce thousands of hypotheses, consuming all worker resources.

3. **Deduction bypass risk** — the `ReasoningRouter` can jump to abduction without ensuring deduction has been fully attempted. Combined with the missing `has_unasked_questions` check, this could cause premature abduction injection for sessions that simply haven't been answered yet.

4. **Phase 2–4 regressions** — the induction pipeline is missing DLQ, structlog, circuit breaker, and idempotency controls that were explicitly added in Phases 2–4 for every other async pipeline. The truth-maintenance system for `HYPOTHETICAL`/`LEARNED` layers is undefined. The sandbox promotion path skips `RuleValidationService`.

5. **Concurrency model gap** — hypothesis injection from the router into `LayeredFactStore` has no lock, no atomicity, and no documented concurrency model. This is a regression from Phase 1–3's explicit lock-based pattern.

I strongly recommend addressing items 1–8 before sprint kick-off, as they affect core correctness, architectural consistency, and Phase 1–4 compatibility.
