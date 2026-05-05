# Suggested Enhancements for INFERRA Phase 4 Implementation Plan

> Review of `INFERRA_Phase4_Implementation_Plan.md` (v1.0) against Phase 1 (v3.0) and Phase 2 (v3.0) enhanced plans,
> architectural soundness, runtime robustness, operational readiness, spec completeness, and cross-phase consistency.

---

## :red_circle: Critical Enhancements (Must Fix Before Sprint)

### 1. RedisSessionStore Lacks Thread-Safety & Atomicity Guarantees

S4.1 -- `RedisSessionStore` uses plain `self.client.setex()` / `self.client.get()` / `self.client.delete()` calls with no locking, no atomic read-modify-write, and no concurrency model documentation. This is a regression from Phase 1's `asyncio.Lock` pattern on `IterateLine` and Phase 2's `IterationEngine` lock.

Specific issues:
- Two concurrent `/feed-answer` requests for the same session can read the same state, each apply their mutation, and the second write overwrites the first (lost update).
- `update()` calls `create()` which is a non-atomic overwrite -- no CAS (compare-and-swap) or optimistic concurrency control.
- No connection pool exhaustion guard -- `max_connections=50` is set but there's no backpressure when the pool is saturated.

**Suggestion:**

``python
class RedisSessionStore:
    def __init__(self, redis_url: str, ttl: int = 86400):
        self.client = redis.Redis.from_url(redis_url, decode_responses=True, max_connections=50)
        self.ttl = ttl
        self._lock_prefix = "inferra:session_lock:"

    def update(self, session: InferenceSession) -> None:
        key = f"inferra:session:{session.id}"
        lock_key = f"{self._lock_prefix}{session.id}"
        lock = self.client.lock(lock_key, timeout=5, thread_local=True)
        with lock:
            current = self.client.get(key)
            if current:
                existing = InferenceSession.deserialize(json.loads(current))
                if existing.version != session.version:
                    raise ConcurrentModificationError(
                        f"Session {session.id} was modified by another worker. "
                        f"Expected version {session.version}, found {existing.version}."
                    )
            session.version = getattr(session, 'version', 0) + 1
            self.client.setex(key, self.ttl, json.dumps(session.serialize()))

    def get(self, session_id: str) -> Optional[InferenceSession]:
        payload = self.client.get(f"inferra:session:{session_id}")
        if payload is None:
            return None
        session = InferenceSession.deserialize(json.loads(payload))
        session.version = json.loads(payload).get("version", 0)
        return session
``

- Add `ConcurrentModificationError` exception type with retry guidance.
- Add `version` field to `InferenceSession` for optimistic concurrency control.
- Document the concurrency model explicitly in the class docstring.
- Add connection pool monitoring: log warning when pool usage > 80%.

---

### 2. RedisSessionStore Has No Serialization Validation or Schema Versioning

S4.1 -- `session.serialize()` -> `json.dumps()` -> `json.loads()` -> `session.deserialize()` has no schema validation, no version field, and no migration path. This is a direct regression from Phase 1's `SessionMetadata.schema_version` and Phase 2's explicit `CURRENT_SCHEMA_VERSION = 2` with migration logic.

If Phase 4 changes the session schema (e.g., adding `version`, `llm_interaction_log`, `convergence_trace`), existing Redis-stored sessions from Phase 3 will fail to deserialize silently or with opaque errors.

**Suggestion:**

``python
class RedisSessionStore:
    CURRENT_STORE_SCHEMA = 3  # Phase 4 schema

    def create(self, session: InferenceSession) -> str:
        payload = session.serialize()
        payload["_store_schema"] = self.CURRENT_STORE_SCHEMA
        payload["_created_by"] = "phase4"
        key = f"inferra:session:{session.id}"
        self.client.setex(key, self.ttl, json.dumps(payload))
        return session.id

    def get(self, session_id: str) -> Optional[InferenceSession]:
        raw = self.client.get(f"inferra:session:{session_id}")
        if raw is None:
            return None
        data = json.loads(raw)
        store_schema = data.get("_store_schema", 0)
        if store_schema < self.CURRENT_STORE_SCHEMA:
            data = self._migrate_session_store(data, from_version=store_schema)
        return InferenceSession.deserialize(data)

    def _migrate_session_store(self, data: dict, from_version: int) -> dict:
        if from_version < 3:
            data.setdefault("version", 0)
            data.setdefault("llm_interactions", [])
            data.setdefault("convergence_trace", [])
        data["_store_schema"] = self.CURRENT_STORE_SCHEMA
        return data
``

- Reuse Phase 1/2's established migration pattern.
- Add integration test: store a Phase 3 session in Redis, load it with Phase 4 code, assert zero errors.
- Add backward-compat test: store a Phase 4 session, load it with Phase 3 deserializer (should gracefully ignore unknown fields).

---

### 3. LLMOrchestrator Has No Timeout, Retry, or Circuit Breaker -- Phase 2 Regression

S4.2 -- `LLMOrchestrator.map_nl_to_goal()` and `generate_explanation()` call `self.client.generate(prompt)` synchronously with:
- **No timeout** -- if the LLM API hangs, the entire `/feed-answer` request blocks indefinitely.
- **No retry with backoff** -- a transient 429/503 is a permanent failure.
- **No circuit breaker** -- if the LLM provider is down, every request will timeout sequentially, consuming all worker threads.
- Phase 2 explicitly added `circuitbreaker` (`failure_threshold=5, recovery_timeout=60`) for the async Fuseki pipeline. The LLM integration is equally external and must have the same protection.

**Suggestion:**

``python
from circuitbreaker import circuit
import httpx

class LLMOrchestrator:
    def __init__(self, client, ontology_cache, min_confidence: float = 0.7,
                 timeout_seconds: float = 10.0, max_retries: int = 2):
        self.client = client
        self.ontology_cache = ontology_cache
        self.min_confidence = min_confidence
        self.timeout = timeout_seconds
        self.max_retries = max_retries

    @circuit(failure_threshold=3, recovery_timeout=30)
    def map_nl_to_goal(self, user_query: str, rule_name: str) -> GoalMapping:
        context = self.ontology_cache.query_rule_goals(rule_name)
        prompt = self._build_goal_prompt(user_query, context)
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.generate(prompt, timeout=self.timeout)
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                if attempt == self.max_retries:
                    log.warning("llm_goal_mapping_failed", error=str(exc), attempts=attempt + 1)
                    return GoalMapping(fallback=True, message="LLM unavailable. Please select a goal explicitly.")
                import time; time.sleep(2 ** attempt)
        if response.confidence >= self.min_confidence:
            return GoalMapping(node_name=response.goal, confidence=response.confidence)
        return GoalMapping(fallback=True, message="Please select a goal explicitly.")
``

- Add `@circuit` decorator with `failure_threshold=3, recovery_timeout=30` -- LLM is less critical than Fuseki, so lower threshold + faster recovery.
- Make all LLM calls async: `async def map_nl_to_goal(...)` with `httpx.AsyncClient`.
- Document: "LLM calls are non-blocking; on timeout/circuit-open, fallback to UI goal selector."
- Add `LLMUnavailableError` that triggers the existing `GoalMapping(fallback=True)` path.

---

### 4. LLMOrchestrator Lacks Input Sanitization & Prompt Injection Protection

S4.2 -- `map_nl_to_goal()` inserts `user_query` directly into the prompt with no sanitization. S6 Risk mentions "Prompt injection via user input" but the implementation has no guard. A malicious user can inject:
- System prompt overrides (`"Ignore previous instructions and..."`)
- Data exfiltration via prompt smuggling
- Goal manipulation to bypass deterministic reasoning

**Suggestion:**

``python
class LLMPromptSanitizer:
    MAX_INPUT_LENGTH = 1000
    BLOCKED_PATTERNS = [
        r"ignore\s+(previous|above|prior)\s+instructions?",
        r"system\s*:",
        r"assistant\s*:",
        r"</?(system|user|assistant)>",
    ]

    @classmethod
    def sanitize(cls, user_input: str) -> str:
        import re
        if len(user_input) > cls.MAX_INPUT_LENGTH:
            raise ValueError(f"Input exceeds maximum length of {cls.MAX_INPUT_LENGTH} characters")
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, user_input, re.IGNORECASE):
                log.warning("prompt_injection_blocked", pattern=pattern, input_preview=user_input[:100])
                raise ValueError("Input contains disallowed patterns")
        return user_input.strip()

class LLMOrchestrator:
    def map_nl_to_goal(self, user_query: str, rule_name: str) -> GoalMapping:
        sanitized_query = LLMPromptSanitizer.sanitize(user_query)
        context = self.ontology_cache.query_rule_goals(rule_name)
        prompt = self._build_goal_prompt(sanitized_query, context)
        ...
``

- Add `LLMPromptSanitizer` with max length + pattern blocking.
- Use role-based prompt isolation: system prompt, context, and user input in separate blocks.
- Log all sanitization events with `structlog`.
- Add security test: attempt injection with known attack vectors, assert all are blocked.

---

### 5. Vite Frontend Has No Authentication or Authorization Model

S4.3 -- The Vite frontend is described with CORS (`allow_origins=["http://localhost:5173"]`) but no authentication, no authorization, and no session access control. In a multi-worker, Redis-backed deployment:
- Any user can access any session by guessing the `session_id`.
- No rate limiting on API endpoints from the frontend.
- No CSRF protection on state-changing endpoints.

**Suggestion:**
- Add API key or JWT-based authentication middleware in FastAPI:

``python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
security = HTTPBearer(auto_error=False)

@router.post("/api/v1/inference/sessions")
async def create_session(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not validate_token(credentials):
        raise HTTPException(status_code=401, detail="Invalid or missing authentication")
    ...
``

- Add session ownership: `session.owner_id` field validated on every read/write.
- Add rate limiting middleware: `slowapi` or `fastapi-limiter` with per-IP/per-user limits.
- Add CSRF tokens for browser-based form submissions.
- Document: "Phase 4 requires authentication for all non-health endpoints. Development mode allows unauthenticated access via `AUTH_ENABLED=false` feature flag."

---

### 6. Docker Compose Exposes Sensitive Services Without Auth

S4.4 -- The Docker Compose configuration exposes Redis (`6379:6379`) and Fuseki (`3030:3030`) on all interfaces with no authentication:
- Redis has no `requirepass` or ACL.
- Fuseki uses `ADMIN_PASSWORD` as an environment variable but no auth is configured on the endpoint.
- Jaeger UI is exposed on `16686` without auth.
- LLM API key is passed as plain environment variable with no secret management.

**Suggestion:**

``yaml
redis:
  image: redis:7-alpine
  ports: ["127.0.0.1:6379:6379"]  # Bind to localhost only
  command: redis-server --requirepass  --maxmemory 512mb --maxmemory-policy allkeys-lru

fuseki:
  image: stain/jena-fuseki:latest
  ports: ["127.0.0.1:3030:3030"]  # Bind to localhost only
  environment:
    ADMIN_PASSWORD: 
    JVM_ARGS: -Dfuseki.auth=
``

- Use Docker secrets or `.env` file with restricted permissions (not checked into git).
- Add `.env.example` to the repo with placeholder values; add `.env` to `.gitignore`.
- Bind Redis/Fuseki to `127.0.0.1` only -- they should only be accessible from the Docker network.
- Add Redis ACL: `--user inferra on > ~inferra:* +@all`.
- Document: "Production deployments must use Docker secrets or HashiCorp Vault for credential management."

---

### 7. SessionStorePort Contract Not Defined -- Port Architecture Incomplete

S4.1 introduces `RedisSessionStore` as a concrete class but Phase 1/2 established a strict port-based architecture where core depends only on Port interfaces. There is no `SessionStorePort` Protocol defined, no contract test suite, and no way to swap implementations (e.g., in-memory for tests, DynamoDB for AWS deployments).

This violates the consolidated architecture's non-negotiable commitment: "Port-based isolation ensures modularization does not disrupt core logic."

**Suggestion:**

``python
# src/ports/session_store_port.py
from typing import Optional, Protocol
from src.domain.session.inference_session import InferenceSession

class SessionStorePort(Protocol):
    """Port contract for session persistence. Any implementation must satisfy these methods."""
    def create(self, session: InferenceSession) -> str: ...
    def get(self, session_id: str) -> Optional[InferenceSession]: ...
    def update(self, session: InferenceSession) -> None: ...
    def delete(self, session_id: str) -> None: ...
    def exists(self, session_id: str) -> bool: ...
``

- Add `SessionStorePort` Protocol matching Phase 1's `FactStorePort` and Phase 2's `DependencyGraphPort` pattern.
- Add `InMemorySessionStore` for testing (no Redis dependency in unit tests).
- Add contract test suite: `tests/contracts/test_session_store_port.py` with `@pytest.mark.parametrize` over `[RedisSessionStore, InMemorySessionStore]`.
- Wire `BackwardChainOrchestrator` to depend on `SessionStorePort`, not `RedisSessionStore` directly.

---

### 8. No LLMOrchestratorPort Protocol -- External Dependency Not Isolated

S4.2 introduces `LLMOrchestrator` as a concrete class used directly by the API layer. Phase 1/2 established that all external dependencies should be behind Port interfaces (`OntologyPort`, `FactStorePort`, etc.). The LLM integration is an external dependency that must be similarly isolated for testability, swapability (OpenAI vs. local models), and graceful degradation.

**Suggestion:**

``python
# src/ports/llm_orchestrator_port.py
from typing import Optional, Protocol

class LLMOrchestratorPort(Protocol):
    """Port contract for LLM orchestration. Any implementation must satisfy these methods."""
    def map_nl_to_goal(self, user_query: str, rule_name: str) -> GoalMapping: ...
    def enhance_question_prompt(self, node: Node, ontology_context: dict) -> str: ...
    def generate_explanation(self, trace: ProvOTrace) -> str: ...

# Implementations:
# - RealLLMOrchestrator (production, calls external LLM API)
# - NullLLMOrchestrator (default fallback, always returns GoalMapping(fallback=True))
# - MockLLMOrchestrator (testing, returns pre-configured responses)
``

- Add `NullLLMOrchestrator` that always returns `GoalMapping(fallback=True)` -- zero LLM dependency when `LLM_ENHANCEMENTS=false`.
- Add `MockLLMOrchestrator` for deterministic testing.
- Feature flag `LLM_ENHANCEMENTS` controls which implementation is injected at session start.
- All API routes depend on `LLMOrchestratorPort`, never on `RealLLMOrchestrator` directly.

---
## :yellow_circle: Important Enhancements (Should Consider for Phase 4)

### 9. Structured Logging Not Propagated from Phase 1/2 -- JSON Formatter Regression

Phase 1 established `structlog` with JSON formatter for production. Phase 2 propagated all mandatory fields. Phase 4 S4.5 introduces `logging.config.dictConfig` with `pythonjsonlogger.jsonlogger.JsonFormatter` -- this **replaces** the `structlog` configuration instead of extending it.

The plan uses the standard library `logging` formatter, which lacks:
- Phase 1's mandatory fields (`session_id`, `node_id`, `fact_source`, `correlation_id`).
- Phase 2's additional fields (`rule_name`, `import_depth`, `propagation_depth`, `source_hash`).
- Phase 4's own new fields (`llm_model`, `llm_prompt_tokens`, `llm_latency_ms`).
- Context variable binding (`structlog.contextvars`).

**Suggestion:**
- Keep `structlog` as the logging framework (consistent with Phases 1-2).
- Configure OpenTelemetry log bridge to emit `structlog` events as OTLP log records.
- Add Phase 4-specific mandatory fields:
  - `llm_model` -- identifies the LLM model used
  - `llm_prompt_tokens` / `llm_completion_tokens` -- token usage tracking
  - `llm_latency_ms` -- round-trip latency
  - `redis_pool_usage` -- connection pool saturation
  - `worker_id` -- identifies the FastAPI worker process
- Add mandatory logging events:
  - LLM: `llm_goal_mapping_start` / `llm_goal_mapping_complete` / `llm_goal_mapping_fallback` / `llm_explanation_generated`
  - Session: `session_created` / `session_restored` / `session_serialized` / `session_lock_acquired` / `session_lock_released`
  - Redis: `redis_pool_exhausted` / `redis_connection_error` / `redis_session_migration`
  - Docker: `container_health_check` / `container_restart`
- Add correlation: bind `worker_id` to structlog context at worker startup.

---

### 10. API Contracts Missing for New Endpoints & No Error Schemas

S4.2 mentions LLM endpoints (`POST /reasoning/goal`, `GET /trace` with explanation) but provides no YAML contract. Phase 1/2 established clear API contract formats with error response schemas. Phase 4 must follow the same standard.

**Suggestion:**

``yaml
POST /api/v1/reasoning/goal
  Summary: Map natural language query to a rule goal node
  Body: { rule_name: str, nl_query: str }
  Returns:
    200:
      goal_mapping: { node_name: str?, confidence: float, fallback: bool, message: str }
      suggested_goals?: [{ node_name, label, description }]
    400: { error_code: "INVALID_INPUT", message: "Input exceeds maximum length or contains disallowed patterns" }
    404: { error_code: "RULE_NOT_FOUND", message: "..." }
    503: { error_code: "LLM_UNAVAILABLE", message: "LLM service is currently unavailable. Fallback to manual goal selection." }

POST /api/v1/reasoning/explain
  Summary: Generate natural language explanation for a session trace
  Body: { session_id: str, conclusion_name?: str }
  Returns:
    200:
      session_id: str
      explanation: str
      grounded_facts: [{ name, value, source }]
      confidence: float
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }
    422: { error_code: "SESSION_NOT_CONVERGED", message: "Explanation requires a converged session" }
    503: { error_code: "LLM_UNAVAILABLE", message: "..." }

GET /api/v1/session/status?session_id=
  Summary: Get session status including convergence state and worker affinity
  Returns:
    200:
      session_id: str
      status: "active" | "converged" | "expired" | "error"
      convergence: { converged: bool, reason: str, iteration: int }
      version: int
      worker_id?: str
      ttl_remaining_seconds: int
    404: { error_code: "SESSION_NOT_FOUND", message: "..." }

GET /api/v1/health
  Summary: Extended health-check for all Phase 4 dependencies
  Returns:
    200:
      status: "ok"
      redis: { status: "ok", pool_usage: 0.3, connected_clients: 5 }
      celery: "ok"
      fuseki: "ok"
      llm: { status: "ok", circuit: "closed", avg_latency_ms: 120 }
      graph_init: true
      semantic_cache: { triples: 12345, memory_mb: 8.3, hit_rate: 0.92 }
      version: "4.0.0"
    503:
      status: "degraded"
      redis: { status: "ok", pool_usage: 0.9, connected_clients: 48 }
      celery: "ok"
      fuseki: "unavailable"
      llm: { status: "circuit_open", circuit: "open", avg_latency_ms: 0 }
      graph_init: true
      semantic_cache: { triples: 0, memory_mb: 0, hit_rate: 0.0 }
``

- Add pagination to `/session/status` for batch queries: `?offset=&limit=`.
- Add rate limiting headers to LLM responses: `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- Add `Idempotency-Key` header support on `POST /reasoning/goal` (same pattern as Phase 1's `/feed-answer`).

---

### 11. No Session Schema Migration for Phase 3 -> Phase 4

Phase 2 established `CURRENT_SCHEMA_VERSION = 2` with migration logic for Phase 1 -> 2. Phase 3 introduced convergence traces, PROV-O metadata, and `QuestionStrategy` state. Phase 4 adds `version`, `owner_id`, `llm_interactions`, and Redis-specific fields. The plan has no migration code for Phase 3 -> 4 sessions stored in the new Redis backend.

**Suggestion:**
- Bump `CURRENT_SCHEMA_VERSION = 4` (Phase 3 would have been v3; Phase 4 is v4).
- Write Phase 3->4 migration:

``python
def _migrate_session_store(self, data: dict, from_version: int) -> dict:
    if from_version < 3:
        # Phase 2 -> 3: add convergence trace, question strategy state
        data.setdefault("convergence_trace", [])
        data.setdefault("question_strategy", "conservative")
        data.setdefault("prov_o_generated", False)
    if from_version < 4:
        # Phase 3 -> 4: add version control, ownership, LLM tracking
        data.setdefault("version", 0)
        data.setdefault("owner_id", None)
        data.setdefault("llm_interactions", [])
        data.setdefault("worker_id", None)
    data["_store_schema"] = self.CURRENT_STORE_SCHEMA
    return data
``

- Add end-to-end migration test: create a Phase 1 session (schema v1) -> migrate through v2, v3, v4 -> assert all fields populated with safe defaults.
- Add backward-compat: Phase 3 code reading a Phase 4 session should gracefully ignore unknown fields (`version`, `owner_id`, `llm_interactions`).

---

### 12. No LLM Observability -- Missing Metrics & Tracing for LLM Calls

The LLM integration is a major new external dependency in Phase 4. There are no metrics for LLM latency, token usage, cost tracking, or circuit breaker state. When production issues arise (hallucinations, latency spikes, cost overruns), there will be no diagnostic data.

**Suggestion:**
- Add Prometheus-style metrics (or extend Phase 2's existing `/metrics` endpoint):

``python
from prometheus_client import Counter, Histogram, Gauge

llm_call_total = Counter(
    "inferra_llm_call_total", "LLM API calls",
    ["operation", "status"]  # operation: goal_map|explain|enhance; status: success|timeout|error|fallback
)
llm_latency_seconds = Histogram(
    "inferra_llm_latency_seconds", "LLM API latency",
    ["operation"]
)
llm_tokens_total = Counter(
    "inferra_llm_tokens_total", "LLM token usage",
    ["type"]  # prompt_tokens | completion_tokens
)
llm_circuit_state = Gauge(
    "inferra_llm_circuit_state", "LLM circuit breaker state (0=closed, 1=open, 2=half-open)"
)
llm_confidence_score = Histogram(
    "inferra_llm_confidence_score", "LLM confidence scores",
    ["operation"]
)
``

- Correlate LLM calls with Phase 1's correlation-ID via `structlog.contextvars`.
- Add LLM-specific tracing spans in OpenTelemetry: `llm.goal_mapping`, `llm.explanation`, `llm.question_enhancement`.
- Track cost per session: accumulate `llm_tokens_total` per `session_id` for billing/analytics.

---

### 13. Feature Flag Matrix Is Incomplete & No Mid-Session Flip Tests

S5 lists feature flag testing but the CI matrix only mentions `REDIS_SESSION_STORE={true,false}` and `LLM_ENHANCEMENTS={true,false}`. Missing flags:
- `STRICT_PORT_CONTRACTS` -- no test for what happens when this is `false`.
- `OBSERVABILITY_ENABLED` -- no test for what happens when this is `false`.
- `AUTH_ENABLED` -- not defined but needed (see enhancement #5).

Phase 1/2 established "feature flags are start-of-session sticky" -- Phase 4 must test that same constraint for its new flags.

**Suggestion:**
- Add missing flags to CI matrix: `STRICT_PORT_CONTRACTS={true,false}`, `OBSERVABILITY_ENABLED={true,false}`, `AUTH_ENABLED={true,false}`.
- Add mid-session flip tests for all Phase 4 flags:
  - Start session with `LLM_ENHANCEMENTS=false`, flip to `true`, assert LLM orchestrator is not instantiated retroactively.
  - Start session with `REDIS_SESSION_STORE=true`, flip to `false`, assert session state is not lost.
  - Start session with `AUTH_ENABLED=true`, flip to `false`, assert existing authenticated session continues.
- Document: "Phase 4 feature flags are start-of-session sticky, consistent with Phase 1/2 policy."

---

### 14. No Performance Baselines for Phase 4 Components

Phase 1 stored baselines in `benchmarks/baseline_v0.json`. Phase 2 stored baselines in `benchmarks/baseline_phase2.json`. Phase 4 introduces Redis, LLM, Vite, and Docker -- all of which add latency overhead. The plan mentions P95 <300ms and <5% error rate but has no mechanism to establish or track baselines.

**Suggestion:**
- Run Phase 3 system through Phase 4 benchmarks before changes; store in `benchmarks/baseline_phase4.json`.
- Define benchmark scenarios:
  - Redis session store: create -> update -> get -> delete (single session, 100 concurrent sessions).
  - LLM goal mapping: 50 queries with known goals, measure latency + accuracy.
  - Full session flow: create -> ask -> answer -> converge -> trace (with and without LLM).
  - Docker Compose: cold start -> first request latency.
- Fail CI if any benchmark regresses >10% from baseline.
- Add LLM-specific budget: `llm_p95_latency_ms < 2000`, `llm_fallback_rate < 10%`.

---

### 15. Docker Compose Has No Health-Check Definitions

S4.4 defines the Docker Compose services but none have `healthcheck` definitions. Without health checks, Docker has no way to know if a service is actually ready, leading to:
- API workers starting before Redis is ready -> connection errors.
- Celery workers starting before Fuseki is ready -> task failures.
- Vite proxying to API before FastAPI is ready -> 502 errors.

**Suggestion:**

``yaml
redis:
  healthcheck:
    test: ["CMD", "redis-cli", "-a", "{REDIS_PASSWORD}", "ping"]
    interval: 5s
    timeout: 3s
    retries: 5

fuseki:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3030/$/ping"]
    interval: 10s
    timeout: 5s
    retries: 5

api:
  depends_on:
    redis:
      condition: service_healthy
    fuseki:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
    interval: 10s
    timeout: 5s
    retries: 5

worker:
  depends_on:
    redis:
      condition: service_healthy
    fuseki:
      condition: service_healthy
``

- Add health checks for all services in Docker Compose.
- Use `condition: service_healthy` for dependency ordering.
- Add startup grace period for Fuseki (JVM startup can be slow).

---

### 16. Vite Frontend Lacks Error Boundary & Offline Resilience

S4.3 describes the Vite frontend but has no error boundary strategy, no offline handling, and no retry logic. If the API is temporarily unavailable:
- Form submissions silently fail.
- Session state is lost (no local caching).
- No user-facing error messages for network failures, LLM unavailability, or session expiry.

**Suggestion:**
- Add Vue error boundary components wrapping `DynamicForm`, `IterateProgress`, and `TraceViewer`.
- Add local session state caching (`localStorage` or `indexedDB`) for offline resilience:
  - Cache last-known session state on every successful API response.
  - On reconnect, sync local changes with server using session `version` for conflict detection.
- Add user-facing toast/notification system for:
  - Network errors (`"Connection lost. Retrying..."`)
  - LLM fallback (`"AI suggestions unavailable. Using manual selection."`)
  - Session expiry (`"Session expired. Starting new session."`)
- Add retry logic with exponential backoff for all API calls (`axios-retry` or custom).

---
## :green_circle: Nice-to-Have Enhancements (Can Defer to Phase 5 but Worth Noting)

### 17. No SessionStorePort Contract Test Suite

Phase 1 added `FactStorePort` contract tests. Phase 2 added `DependencyGraphPort` and `IterationPort` contract tests. Phase 4 introduces `SessionStorePort` (enhancement #7) but this document is the first to suggest it. When Phase 5 adds distributed session stores, contract tests pay dividends.

**Suggestion:**
- Create `tests/contracts/test_session_store_port.py` using `@pytest.mark.parametrize` over `[RedisSessionStore, InMemorySessionStore]`.
- Test contract: `create()` -> `get()` -> `update()` -> `get()` -> `delete()` -> `get() returns None` lifecycle.
- Test edge cases: create twice (idempotent), update non-existent (raises), delete non-existent (no-op), concurrent update (optimistic lock failure).
- Test TTL behaviour: `time.sleep(TTL + 1)` -> `get()` returns `None`.

---

### 18. No Health-Check Extensions for Phase 4 Dependencies

Phase 1 added `GET /health` checking Redis + graph_init. Phase 2 extended for Celery, Fuseki, and SemanticCache. Phase 4 adds LLM, Redis pool stats, and Docker container health -- but the plan's health-check code (S4.5) only covers OpenTelemetry instrumentation, not the actual dependency checks.

**Suggestion:**

``yaml
GET /api/v1/health
  Summary: Extended health-check for all Phase 4 dependencies
  Returns:
    200:
      status: "ok"
      redis: { status: "ok", pool_usage: 0.3, connected_clients: 5, memory_mb: 128 }
      celery: { status: "ok", active_workers: 3 }
      fuseki: { status: "ok", triples: 45230 }
      llm: { status: "ok", circuit: "closed", avg_latency_ms: 120 }
      graph_init: true
      semantic_cache: { triples: 12345, memory_mb: 8.3, hit_rate: 0.92 }
      version: "4.0.0"
      uptime_seconds: 86400
    503:
      status: "degraded"
      redis: { status: "ok", pool_usage: 0.9, connected_clients: 48, memory_mb: 480 }
      celery: { status: "ok", active_workers: 3 }
      fuseki: { status: "unavailable" }
      llm: { status: "circuit_open", circuit: "open", avg_latency_ms: 0 }
      graph_init: true
      semantic_cache: { triples: 0, memory_mb: 0, hit_rate: 0.0 }
``

- Add LLM circuit breaker state to health check.
- Add Redis connection pool metrics (usage, connected clients, memory).
- Add Celery active worker count.
- Add `uptime_seconds` for operational monitoring.
- Add degraded response when LLM circuit is open (non-critical dependency).

---

### 19. No LLM Prompt Template Versioning

S4.2 builds prompts inline (`_build_goal_prompt()`, `_build_explain_prompt()`). Prompt templates are code-level artifacts that change frequently. Without versioning:
- Cannot A/B test prompt improvements.
- Cannot correlate LLM quality regressions with prompt changes.
- Cannot roll back prompt changes independently of code deployments.

**Suggestion:**
- Store prompt templates as versioned files: `src/domain/llm/prompts/goal_mapping_v1.txt`, `src/domain/llm/prompts/explanation_v1.txt`.
- Add `prompt_version` field to `GoalMapping` and explanation responses.
- Log `prompt_version` with every LLM call via `structlog`.
- Add configuration: `LLM_PROMPT_VERSION=1` allows runtime prompt switching without code changes.

---

### 20. Sprint Schedule Is Aggressive & Lacks Buffer Days

Phase 1 (enhanced) added 2 buffer days and designated Friday as "buffer + polish." Phase 2 followed the same pattern. Phase 4 reverts to 5 pure feature days with no buffer, despite Phase 4 being the most complex phase (Redis migration, LLM integration, Vite frontend, Docker Compose, observability, legacy removal, load testing, chaos testing).

**Suggestion:**
- Add 2 buffer days (same as Phase 1/2).
- Designate Friday as "buffer + polish + production readiness review" rather than feature delivery.
- WS-3 (LLM Orchestration) depends on external LLM API availability -- add a contingency: if API access is not provisioned by Tuesday, WS-3 switches to `NullLLMOrchestrator`-based development.
- WS-2 (Vite Frontend) depends on stable API contracts from WS-1 -- consider staggering WS-2 to start Tuesday.
- WS-4 (Docker/Observability) depends on all other WS completing -- add a smoke-test milestone on Wednesday to catch integration issues early.
- Add daily stand-up protocol with blocker escalation (same as Phase 1/2).

---

## Summary Matrix

| #  | Enhancement                                              | Severity     | Effort |
| -- | -------------------------------------------------------- | ------------ | ------ |
| 1  | RedisSessionStore thread-safety & atomicity              | Critical     | Medium |
| 2  | RedisSessionStore schema versioning & migration          | Critical     | Medium |
| 3  | LLMOrchestrator timeout, retry, circuit breaker          | Critical     | Low    |
| 4  | LLM prompt injection protection & sanitization           | Critical     | Low    |
| 5  | Vite frontend authentication & authorization             | Critical     | Medium |
| 6  | Docker Compose service auth & network binding             | Critical     | Low    |
| 7  | SessionStorePort Protocol definition & contract tests    | Critical     | Low    |
| 8  | LLMOrchestratorPort Protocol definition & Null impl      | Critical     | Low    |
| 9  | Structlog propagation (replace dictConfig regression)    | Important    | Low    |
| 10 | API contracts for new endpoints + error schemas          | Important    | Medium |
| 11 | Session schema migration Phase 3 -> Phase 4             | Important    | Medium |
| 12 | LLM observability: metrics, tracing, cost tracking      | Important    | Medium |
| 13 | Feature flag matrix completion + mid-session flip tests  | Important    | Low    |
| 14 | Performance baselines for Phase 4 components            | Important    | Low    |
| 15 | Docker Compose health-check definitions                  | Important    | Low    |
| 16 | Vite frontend error boundaries & offline resilience      | Important    | Medium |
| 17 | SessionStorePort contract test suite                      | Nice-to-have | Medium |
| 18 | Health-check extensions for Phase 4 dependencies        | Nice-to-have | Low    |
| 19 | LLM prompt template versioning                           | Nice-to-have | Low    |
| 20 | Sprint buffer days + WS staggering                       | Nice-to-have | N/A    |

---

**The Phase 4 plan is architecturally ambitious and well-scoped.** The primary concerns are:

1. **Cross-phase regressions** -- thread-safety, circuit breakers, structured logging, and schema migration patterns established in Phases 1-2 must not be lost in the transition to Redis, LLM, and Docker infrastructure.

2. **Security gaps** -- authentication, prompt injection, Docker network exposure, and credential management are production-critical and must be addressed before any deployment.

3. **Port architecture completeness** -- `SessionStorePort` and `LLMOrchestratorPort` must be defined to maintain the port-based isolation that Phases 1-2 established as non-negotiable.

4. **Operational readiness** -- LLM observability, health checks, performance baselines, and feature flag coverage are essential for a production deployment that includes external LLM dependencies.

5. **Under-specified components** -- the Vite frontend, LLM fallback paths, and Docker Compose configuration need concrete error-handling and resilience strategies before sprint start.

I strongly recommend addressing items 1-8 before sprint kick-off, as they affect core correctness, security, and Phase 1-3 compatibility.
