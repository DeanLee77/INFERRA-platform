
# INFERRA Future Extension Plan: Induction & Abduction Reasoning
**Document Status:** Extension Blueprint v1.0
**Scope:** Architectural design, phased implementation, data model extensions, API contracts, and checkable task plan for integrating non-deductive reasoning modes into INFERRA.
**Alignment:** Fully compliant with INFERRA's port-based modularization, layered working memory, async sync pipeline, PROV-O traceability, and deterministic convergence guarantees.

## Implementation Status Audit - 2026-05-07

**Reconciled status:** This future extension blueprint is partially superseded by `INFERRA_Phase5_Implementation_Plan.md`. The current codebase already includes Phase 5 implementations for `AbductionPort`, Z3-backed abduction, `InductionPort`, Celery induction adapter scaffolding, `ReasoningRouter`, `HYPOTHETICAL`/`LEARNED` fact layers, Phase 5 session schema migration, reasoning endpoints, and related tests.

**Live validation update:** Basic Docker, Redis, Fuseki, Celery, PostgreSQL, Z3, metrics, abduction, and disabled induction smoke checks pass in compose. Dockerized k6 at 20 VUs passes. Dockerized k6 at 500 VUs and the local Phase 4 restart chaos suite pass under the local compose production profile.

**Remaining future-plan blockers:** Full PROV-O trace mining, induction candidate quality benchmarking, human review UI, API/UI exposure for confidence override configuration, dedicated Celery/Fuseki induction workflow drills, staging repetition of the 500-VU production-load profile, and production hardening remain open. This document should not be marked complete until Phase 5 is complete and the future-only exploration items are either implemented or explicitly deferred.

**GraphRAG dependency:** GraphRAG remains deferred until Phase 1-5 and this induction/abduction hardening track are complete.

---

## 📖 1. Executive Summary

This plan extends INFERRA from a deterministic deduction engine into a **Tri-Modal Hybrid Reasoning Platform**:
- **Deduction** (Existing): Rule + Fact → Conclusion (deterministic, auditable)
- **Abduction** (Phase 1): Observation + Rules → Missing Facts / Hypotheses (diagnostic, plausible)
- **Induction** (Phase 2): Traces + Ontology → Candidate Rules (learning, probabilistic)

**Key Design Principles:**
- ✅ Abduction runs near-real-time using constraint solvers + LLM-assisted hypothesis ranking
- ✅ Induction runs asynchronously/offline via trace mining → candidate rule compilation → validation sandbox
- ✅ Both modes extend existing `Port` contracts, `FactSource` layers, and `InferenceContext`
- ✅ PROV-O schema updated to track `HYPOTHETICAL` and `LEARNED` provenance
- ✅ Zero disruption to backward-chaining core; new modes are opt-in or triggered on convergence failure

---

## 🧩 2. Architectural Integration Points

| INFERRA Component | Extension Strategy |
|-------------------|-------------------|
| `FactSource` Enum | Add `HYPOTHETICAL` (abduction), `LEARNED` (induction) |
| `InferenceContext` | Add `reasoning_mode`, `confidence`, `hypothesis_count`, `induction_job_id` |
| `LayeredFactStore` | Route `HYPOTHETICAL`/`LEARNED` facts to isolated layers with unified read view fallback |
| `AbductionPort` | Implemented as ABCMeta port with `propose_hypotheses()`; ranking/filtering currently lives in `ReasoningRouter` |
| `InductionPort` | Implemented as ABCMeta port with `start_batch()`, `get_status()`, and `promote()` |
| Async Pipeline | Celery/SQS workers for heavy induction jobs; lightweight Z3/LLM calls for abduction |
| PROV-O Schema | Extend `inf:Conclusion` with `inf:status: CANDIDATE | VALIDATED | PROMOTED` and `inf:confidence` |

---

## 🔍 Phase 1: Abduction Implementation (Diagnostic & Hypothesis Generation)
**Goal:** When backward-chaining stalls due to missing facts, generate plausible hypotheses, rank them, and optionally inject as `HYPOTHETICAL` facts.
**Workstation Feasibility:** High (constraint solvers + bounded graph search + async LLM fallback).
**Timeline:** Weeks 1–4

### 1.1 Data Model & Port Contracts
- [x] Extend `FactSource` enum with `HYPOTHETICAL` and add confidence scoring
- [x] Define `AbductionPort` as an ABCMeta port with `propose_hypotheses()` plus Null, Mock, and Z3 adapters
- [x] Implement `Z3ConstraintAbductionAdapter` for rule-graph constraint solving *(bounded Z3 adapter exists over graph snapshots; dedicated Phase 5 acceptance passes)*
- [ ] Implement `LLMAbductionAdapter` for natural-language hypothesis generation + ontology validation

### 1.2 Engine Integration
- [~] Add `trigger_abduction_on_stall()` hook to `HybridReasoningEngine` convergence check *(ReasoningRouter + BackwardChainOrchestrator integration exists; full production acceptance pending)*
- [x] Bind abduction results to `HYPOTHETICAL` layer in `LayeredFactStore`
- [ ] Update `QuestionStrategy` to surface ranked hypotheses as alternative prompts
- [~] Ensure `HYPOTHETICAL` facts are excluded from final conclusions unless explicitly promoted *(layer precedence and isolation have acceptance proof; final promotion policy remains workflow-specific)*

### 1.3 API & UI
- [x] Create `POST /api/v1/reasoning/abduct` endpoint
- [~] Return ranked hypotheses with `confidence`, `dependency_path`, `ontology_consistency_score` *(endpoint returns confidence/path/ontology consistency; schema differs from this early blueprint)*
- [ ] Add Vite UI component for hypothesis review & manual promotion/rejection
- [~] Log abduction attempts to `InferenceContext.trace` with PROV-O mapping *(InferenceContext captures attempts/hypothesis trace; PROV-O mapping acceptance pending)*

### 1.4 Testing & Validation
- [x] Unit tests for Z3 constraint solver over graph snapshots
- [x] Integration tests for `HYPOTHETICAL` fact isolation & unified read view
- [~] E2E test: Convergence stall → abduction → hypothesis injection → resolution *(focused tri-modal test exists; convergence-resolution proof pending)*
- [~] Performance benchmark: <2s latency for rule sets ≤1000 nodes on standard workstation *(local k6 abduction p95 is below 2s; dedicated 1000-node benchmark pending)*

---

## 📈 Phase 2: Induction Implementation (Rule Discovery & Pattern Mining)
**Goal:** Mine historical PROV-O session traces to discover candidate rules, compile to INFERRA syntax, and validate in sandbox before promotion.
**Workstation Feasibility:** Medium (offline/async, CPU-bound trace mining, no GPU required for tree/ILP extraction).
**Timeline:** Weeks 5–10

### 2.1 Trace Extraction & Pattern Mining
- [ ] Build `TraceExtractor` to query Fuseki PROV-O triples + session logs
- [ ] Implement `PatternMiner` (frequent subgraph extraction + decision path clustering)
- [ ] Add feature engineering pipeline: input/output pairs, dependency paths, quantifier patterns
- [ ] Store extracted patterns in `CandidatePattern` repository with confidence metadata

### 2.2 Rule Compilation & Sandbox Validation
- [ ] Implement `NadiaCompiler` for pattern → INFERRA plain-text syntax conversion
- [~] Create `RuleValidationService` sandbox: syntax check, type consistency, DAG validation, ontology alignment *(validator and RuleSandbox exist; full induction-promotion proof pending)*
- [x] Add `InductionPort` as an ABCMeta port with `start_batch()`, `get_status()`, and `promote()`
- [ ] Store validated candidates with `inf:status: CANDIDATE` and `inf:confidence` score

### 2.3 Async Pipeline & Promotion Workflow
- [x] Configure Celery worker for batch induction jobs
- [x] Implement job scheduling, progress tracking, and failure retry logic *(Celery task, retries, status, DLQ hook, circuit breaker, and idempotency proof exist)*
- [x] Add `POST /api/v1/reasoning/induce/start` and `GET /api/v1/reasoning/induce/status/{job_id}`
- [ ] Build human-in-the-loop review UI for candidate promotion/rejection
- [~] On promotion: trigger `RuleUpdated` event → async RDF sync → `ModuleRegistry` cache refresh *(promotion adapter/sandbox exists; full RDF/cache workflow proof pending)*

### 2.4 Testing & Validation
- [ ] Unit tests for trace extraction, pattern clustering, and syntax compilation
- [~] Integration tests for sandbox validation gate & async job queue *(focused RuleSandbox, Celery adapter, and eager induction task tests exist; full Fuseki/Celery workflow pending)*
- [ ] E2E test: 100 historical sessions → induction job → candidate rules → sandbox validation → promotion
- [ ] Accuracy benchmark: ≥85% syntactic validity, ≤10% ontology mismatch rate

---

## 🔄 Phase 3: Hybrid Reasoning Router & Dynamic Routing
**Goal:** Seamlessly route inference sessions between deduction, abduction, and induction based on context, confidence, and system state.
**Timeline:** Weeks 11–14

### 3.1 Routing Logic & Context Tracking
- [~] Add `ReasoningMode` enum to `InferenceContext` (`DEDUCTION`, `ABDUCTION`, `INDUCTION`, `HYBRID`) *(context fields exist as strings; enum type not introduced)*
- [x] Implement `ReasoningRouter` with fallback triggers (e.g., stall → abduction, trace backlog → induction)
- [x] Add confidence thresholds & iteration caps to prevent reasoning loops *(environment, per-rule, and per-session router thresholds plus warmup/caps exist)*
- [x] Update `InferenceContext.trace` to log mode switches, triggers, and outcomes

### 3.2 Unified Response & API Updates
- [~] Extend `/next-question` and `/summary` responses with `reasoning_mode`, `confidence`, `status` *(`/summary` and `/trace` are enriched; `/next-question` proof pending)*
- [ ] Add `POST /api/v1/reasoning/mode` to override routing per session (expert/debug mode)
- [ ] Ensure `QuestionStrategy` adapts prompt style based on active reasoning mode
- [x] Add rate limiting & concurrency controls for abduction/induction endpoints through shared HTTP middleware and Celery worker controls

### 3.3 Testing & Validation
- [x] Unit tests for router decision matrix & fallback triggers
- [ ] Integration tests for mode switching mid-session with state preservation
- [~] Load test: 50 concurrent sessions with mixed deduction/abduction routing *(500-VU local production gate covers abduction endpoint behavior; dedicated mixed session lifecycle load pending)*
- [ ] Validate trace completeness across mode transitions in PROV-O output

---

## 🧪 Phase 4: Advanced Exploration & Production Hardening
**Goal:** Explore graph ML, neuro-symbolic LLM integration, caching, observability, and enterprise-grade monitoring.
**Timeline:** Weeks 15–20

### 4.1 Advanced Reasoning Extensions
- [ ] Prototype `GraphMLEmbbeddingAdapter` for fast hypothesis ranking via node embeddings
- [ ] Implement `NeuroSymbolicLLMAdapter` for LLM-generated hypotheses + Z3 constraint validation
- [ ] Add self-updating rule cache with TTL & drift detection
- [ ] Experiment with confidence calibration (Platt scaling / isotonic regression)

### 4.2 Observability & Monitoring
- [x] Instrument OpenTelemetry traces for abduction/induction spans
- [~] Add metrics: `abduction_latency_ms`, `induction_job_duration_sec`, `hypothesis_confidence_dist`, `candidate_promotion_rate` *(Prometheus counters/histograms for abduction, induction, routing, and LLM confidence exist; exact blueprint metric names differ)*
- [~] Configure alerts: abduction timeout, induction job failure, confidence threshold breach *(Prometheus alert rules exist for abduction/induction/LLM/cache/Fuseki/API; staging threshold tuning pending)*
- [~] Add Grafana dashboard for reasoning mode distribution & pipeline health *(operational dashboard exists; dedicated reasoning-mode distribution dashboard pending)*

### 4.3 Production Readiness
- [x] Implement circuit breakers for LLM/induction worker dependencies
- [x] Add graceful degradation: fallback to deduction if abduction/induction services unavailable
- [~] Document runbooks for hypothesis explosion, trace backlog, and candidate validation failures *(production readiness docs identify these risks; dedicated runbooks pending)*
- [~] Conduct security review: trace data anonymization, sandbox isolation, prompt injection guards *(prompt sanitization and sandbox validation exist; formal review pending)*

### 4.4 Testing & Validation
- [~] Chaos testing: kill abduction/induction workers mid-session → verify fallback to deduction *(local Phase 4 worker restart chaos passes; dedicated tri-modal mid-session chaos pending)*
- [ ] Soak test: 72h continuous routing with mixed reasoning modes
- [ ] Final E2E validation: PROV-O audit trail spans all three reasoning modes
- [ ] Sign-off checklist complete & release candidate tagged

---

## 🌐 7. Data Model, PROV-O & API Extensions

### 7.1 `FactSource` & `InferenceContext` Updates
```python
class FactSource(Enum):
    ASSERTED = "ASSERTED"
    INFERRED = "INFERRED"
    SEMANTIC = "SEMANTIC"
    HYPOTHETICAL = "HYPOTHETICAL"  # Abduction
    LEARNED = "LEARNED"            # Induction

@dataclass
class InferenceContext:
    # ... existing fields ...
    reasoning_mode: ReasoningMode = ReasoningMode.DEDUCTION
    confidence: float = 1.0
    hypothesis_count: int = 0
    induction_job_id: Optional[str] = None
```

### 7.2 PROV-O Trace Schema Extensions
```turtle
<conclusion:xyz789> a inf:Conclusion, prov:Entity ;
    prov:wasGeneratedBy <session:abc123> ;
    inf:reasoningMode inf:ABDUCTION ;
    inf:confidence "0.82"^^xsd:decimal ;
    inf:status "HYPOTHETICAL" ;
    inf:dependedOn <fact:service_period_valid>, <fact:disability_rating> .

<rule:candidate_001> a inf:RuleNode ;
    inf:reasoningMode inf:INDUCTION ;
    inf:status "CANDIDATE" ;
    inf:confidence "0.91"^^xsd:decimal ;
    inf:extractedFrom <trace:batch_2025_q1> .
```

### 7.3 API Contract Extensions
- [x] Implement `POST /api/v1/reasoning/abduct` with hypothesis ranking payload
- [x] Implement `POST /api/v1/reasoning/induce/start` + `GET /api/v1/reasoning/induce/status/{job_id}`
- [x] Extend `/summary` & `/trace` with `reasoning_mode`, `confidence`, `status`, `origin_job_id`
- [ ] Add `POST /api/v1/reasoning/mode` for session-level routing override
- [ ] Document OpenAPI spec updates & version bump (`v1.1`)

---

## 🛠️ 8. Testing, Observability & Rollout Strategy

### 8.1 Testing Strategy
- [x] Unit tests: `AbductionPort`, `InductionPort`, `ReasoningRouter`, `FactSource` extensions
- [~] Integration tests: Async job queue, sandbox validation, PROV-O triple generation *(dedicated Phase 5 acceptance passes for queue/sandbox; full PROV-O trace-mining workflow pending)*
- [ ] Property-based tests: Hypothesis ranking stability, induction candidate syntax validity
- [~] E2E tests: Full session lifecycle across all three reasoning modes *(focused tri-modal tests exist; full lifecycle acceptance pending)*

### 8.2 Observability & Monitoring
- [x] Add OpenTelemetry instrumentation for abduction/induction spans
- [~] Configure metrics collection: latency, job duration, confidence distribution, promotion rate *(core Prometheus metrics exist; exact future-plan metric suite pending)*
- [~] Set up alerts: timeout, failure, confidence breach, trace backlog *(Prometheus alert rules exist; staging threshold tuning pending)*
- [~] Build Grafana dashboard: reasoning mode distribution, pipeline health, hypothesis explosion rate *(operational dashboard exists; dedicated reasoning dashboard pending)*

### 8.3 Rollout Plan
- [ ] Phase 1 (Abduction): Feature flag `ABDUCTION_ENABLED=true`, canary deployment, manual review UI
- [ ] Phase 2 (Induction): Async worker pool, trace extraction backlog processor, candidate review queue
- [ ] Phase 3 (Router): Gradual traffic shift, fallback verification, confidence threshold tuning
- [~] Phase 4 (Hardening): Circuit breakers, chaos testing, documentation finalization, v2.0 release

---

## ⚠️ 9. Risk Mitigation Checklist

| Risk | Mitigation Task | Status |
|------|----------------|--------|
| **Hypothesis Explosion** | Cap `max_hypotheses`, prune by `ontology_consistency_score` | [~] Router caps hypotheses and filters ontology consistency; dedicated stress proof pending |
| **Computational Overload** | Async workers, workstation thread pools, timeout guards | [~] Celery worker, rate limit, retries, induction circuit/idempotency, LLM circuit, and Z3 timeout exist; full pool/backpressure tuning pending |
| **Trace Quality Degradation** | Schema validation, missing fact imputation, outlier filtering | [ ] Implement trace QA pipeline |
| **Candidate Rule Drift** | Sandbox validation gate, version pinning, human review step | [~] Sandbox/promotion adapter exists; human review audit workflow pending |
| **LLM Hallucination** | Z3 constraint validation, ontology type checking, confidence floor | [ ] Add neuro-symbolic validation adapter |
| **Routing Loop / Stall** | `iteration_count` cap, fallback to pure deduction, alert on hit | [~] Router warmup, threshold precedence, and fallback logic exist; dedicated alert proof pending |
| **PROV-O Bloat** | TTL policies, trace archiving, aggregated summary export | [ ] Configure retention & archival jobs |

---

## 🏁 10. Final Assessment & Next Steps

**Strategic Value:**
Abduction unlocks diagnostic reasoning, missing-data recovery, and alternative path exploration. Induction enables continuous policy refinement, automated rule discovery, and self-improving rule sets. Together, they transform INFERRA from a deterministic executor into a **living reasoning platform**.

**Architectural Alignment:**
- ✅ Preserves backward-chaining as the primary driver
- ✅ Extends existing `Port` contracts & layered memory
- ✅ Leverages async pipeline & PROV-O traceability
- ✅ Workstation-optimized sequencing (abduction → induction → router)

**Immediate Next Steps:**
- [x] Approve extension blueprint & assign Phase 1 sprint backlog
- [~] Provision dev environment with Z3, Celery, and PROV-O query templates *(local compose stack exists; staging provisioning pending)*
- [x] Implement `FactSource.HYPOTHETICAL` + `AbductionPort` skeleton
- [x] Draft unit test suite for constraint-based hypothesis generation
- [ ] Schedule architecture review gate before Phase 2 kickoff

> **INFERRA does not just execute rules.**
> It diagnoses gaps, discovers patterns, and evolves with the knowledge it processes.

---
*Document generated for INFERRA future extension planning. Aligns with Python backend, Fuseki RDF store, async workers, LLM orchestration, and Vite frontend stack. Ready for sprint allocation, stakeholder sign-off, and phased execution.*
