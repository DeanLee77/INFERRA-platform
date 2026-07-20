# INFERRA Platform — Complete Implementation Guide

> **Version:** 2026-07-17
> **Status:** Broad development-profile implementation reference; Core 1.0 remains blocked
> **Repository:** `inferra-platform`

> **Accepted architecture amendment.** The deterministic kernel will be
> extracted into an internal, independently buildable `inferra-core` Python
> distribution before Core 1.0. `inferra-platform` will import that artifact and
> remain the official authoritative service for API, identity, persistence,
> transactions, audit/outbox, ontology publication, workers, and operations.
> P0.1 and P0.2a-P0.2b are complete: internal `inferra-core==0.1.1` owns its
> leaf contracts plus private graph/node/token/parser/validation layers and
> passes independent build and clean installed-wheel parser checks. The P0
> security correction replaces string-to-SymPy evaluation with a bounded
> INFERRA AST, fails declaration validation closed, and makes cycles typed;
> Core now has no third-party runtime dependencies. A public compile/validation
> facade and Platform rewiring must precede remaining state/import/inference/
> provenance extraction, and the package is not publicly published. Evidence is in
> `docs/INFERRA_Core_Extraction_P0_1_Baseline.md` and
> `docs/INFERRA_Core_Extraction_P0_2_Distribution.md`. The controlling design is
> `docs/INFERRA_Core_Package_and_Runtime_Architecture.md`; the
> cross-product release direction is
> `docs/INFERRA_Cross_Project_Technical_Direction.md`. This guide describes the
> current broad development surface unless a section explicitly says otherwise.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Phases & Feature Flags](#2-phases--feature-flags)
3. [API Reference](#3-api-reference)
4. [Core Domain Capabilities](#4-core-domain-capabilities)
5. [Use Cases](#5-use-cases)
6. [Implementation Status](#6-implementation-status)
7. [Gap Analysis](#7-gap-analysis)
8. [Deployment Guide](#8-deployment-guide)
9. [Test Coverage](#9-test-coverage)
10. [Ontology Integration Examples](#10-ontology-integration-examples)
11. [Quick Start](#11-quick-start)

---

## 1. Architecture Overview

The INFERRA platform is a **FastAPI** application built with hexagonal/ports-and-adapters architecture:

The accepted target adds a physical package boundary inside that architecture:

```text
AXIOM/AEGIS/generated SDKs -> Platform API/application services
                                      |
                                      v
                            inferra-core package

Platform owns: HTTP, identity, SQLAlchemy, migrations, transactions, sessions,
               outbox/audit persistence, workers, Fuseki and operations.
Core owns:     pure parsing, graph, fact store, inference, imports, provenance,
               deterministic hashes, diagnostics and audit-event construction.
```

The package must not import FastAPI, SQLAlchemy, Redis, Celery, Fuseki, LLM
providers, environment/secrets, AEGIS, AXIOM, or other extensions. Python hosts
may eventually embed it directly for offline/single-process use, but those hosts
then own durability, identity, concurrency, migration, audit, and recovery. The
official multi-user authority remains the Platform service.

```
src/
├── adapters/
│   ├── inbound/http/          ← 14 REST API routers
│   └── outbound/
│       ├── llm/               ← LLM orchestrator, provider registry, streaming
│       ├── ontology/          ← Fuseki SPARQL adapter, RDF compiler
│       ├── persistence/       ← SQLAlchemy repositories
│       ├── reasoning/         ← Abduction/induction adapters
│       └── session/           ← In-memory + Redis session stores
├── domain/                    ← Core business logic
│   ├── aegis/                 ← Workflow authoring, trigger policies, Phase 3 runtime
│   ├── graph/                 ← Dependency graph, topological sort
│   ├── imports/               ← Modular IMPORT: / RULE SET: resolution
│   ├── inference/             ← Backward-chain engine, sessions, question flow
│   ├── iterate/               ← Iteration engine (loop quantifiers)
│   ├── reasoning/             ← Reasoning router, ontology reasoner
│   ├── rule_parser/           ← Scanner, parser, tokenizer
│   ├── state/                 ← Layered fact store, feature flags
│   └── trace/                 ← PROV-O trace generation
├── ports/                     ← Abstract interfaces (contracts)
├── services/                  ← Application services
└── tasks/                     ← Celery async pipeline
```

### Key Design Patterns

- **Ports & Adapters:** Every external dependency has an abstract port
- **Null/Mock implementations:** System runs fully without LLM, Fuseki, or Redis
- **Feature flags:** All advanced capabilities gated; conservative defaults
- **Session-scoped flag freezing:** Flags captured at session creation, immutable thereafter
- **Idempotency:** Feed-answer keys, induction deduplication, Fuseki versioned writes
- **Circuit breaker:** LLM orchestrator with failure threshold + recovery timeout
- **Layered fact store:** Provenance-preserving working memory with truth-maintenance

---

## 2. Phases & Feature Flags

The system is organized into 5 phases with granular feature flags and typed
feature settings. The values in this section are **code defaults** from
`FEATURE_FLAG_SPECS` in `src/domain/state/feature_flags.py`. That immutable
registry contains each snapshot key, primary environment name, type, default,
phase, description, numeric constraints, compatibility aliases, and
session-stickiness policy.
`get_feature_flag_specs()` exposes it for read-only introspection. Exported
`INFERRA_*` variables, Compose, and permitted per-session ontology inputs can
override the code defaults. Effective values are available through
`get_effective_feature_flag_snapshot()` and are snapshotted and frozen when an
inference session starts.

### Phase 1 (Core — ✅ Default ON)

| Flag | Default | Purpose |
|------|---------|---------|
| `USE_HYPERGRAPH` | `true` | `HyperAdjacencyGraph` as canonical dependency graph |
| `LAYERED_MEMORY` | `true` | `LayeredFactStore` with provenance tagging |
| `LEGACY_ITERATE` | `true` | Nested inference engine for iterate (compatibility) |
| `ML_OPTIMIZED_DFS` | `false` | History-aware DFS ordering |

### Phase 2 (Async + Modular — ⚙️ Default OFF)

| Flag | Default | Purpose |
|------|---------|---------|
| `ASYNC_SYNC_ENABLED` | `false` | Rule → Celery → Fuseki RDF projection pipeline |
| `MODULAR_IMPORTS` | `false` | `IMPORT:` / `RULE SET:` resolution |

### Phase 3 (Hybrid + Ontology — ⚙️ Default OFF)

| Flag | Default | Purpose |
|------|---------|---------|
| `HYBRID_ORCHESTRATOR` | `false` | Async convergence loop |
| `ASYNC_POST_REASONING` | `false` | Ontology post-reasoning events |
| `GENERATE_POST_REASONING_TTL` | `false` | Post-reasoning TTL artifact generation |
| `PROV_O_TRACE` | `false` | W3C PROV-O trace generation |
| `ENRICHED_API` | `false` | Provenance-enriched API responses |
| `ONTOLOGY_ADVISORY_ENABLED` | `false` | Ontology advisory suggestions |
| `ONTOLOGY_AUTO_ANSWER_ENABLED` | `false` | Auto-answer from ontology defaults |
| `ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD` | `0.85` | Minimum auto-answer confidence |
| `ONTOLOGY_REASONING_ENABLED` | `false` | Materialized ontology reasoning |
| `ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD` | `0.85` | Minimum materialization confidence |
| `ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH` | `1` | Minimum hierarchy depth |
| `ONTOLOGY_REASONING_MAX_CLOSURE_DEPTH` | `10` | Maximum ontology closure depth |
| `ONTOLOGY_QUESTION_STRATEGY_ENABLED` | `false` | Semantic question ordering/pruning |

### Phase 4 (Redis + Auth — ⚙️ Default OFF)

| Flag | Default | Purpose |
|------|---------|---------|
| `REDIS_SESSION_STORE` | `false` | Redis-backed session persistence |
| `LLM_ENHANCEMENTS` | `false` | LLM goal mapping/explanation |
| `STRICT_PORT_CONTRACTS` | `true` | Strict port-contract enforcement |
| `OBSERVABILITY_ENABLED` | `false` | OpenTelemetry observability |
| `AUTH_ENABLED` | `false` | API key + owner-based auth |

### Phase 5 (Abduction + Induction — ⚙️ Default OFF)

| Flag | Default | Purpose |
|------|---------|---------|
| `ABDUCTION_ENABLED` | `false` | LLM/Z3 hypothesis generation |
| `INDUCTION_PIPELINE` | `false` | Celery batch pattern discovery |
| `REASONING_ROUTER` | `true` | Deduction-first routing |
| `CONFIDENCE_THRESHOLDS` | `true` | Hypothesis confidence gating |

### Code Defaults vs Overrides

| Source | Meaning | Current flag differences from code defaults |
| --- | --- | --- |
| `src/domain/state/feature_flags.py` | Canonical library defaults used when no higher-priority value exists | None; this is the baseline |
| Exported process environment | Operator or launcher overrides read when `FeatureFlags` is constructed | Any supported `INFERRA_*` value may override its corresponding default; API and worker entry points load `.env` first without replacing exported values, while the domain registry remains filesystem-independent |
| Base Compose API service | Feature-rich, loopback-only local deployment profile | Receives one operator-substitutable 28-entry profile; Redis sessions, async sync, both post-reasoning gates, PROV-O, enriched API responses, abduction, induction, observability, and auth default to enabled |
| Base Compose worker | Same feature-rich local deployment profile | Receives the identical 28-entry mapping as the API so cross-process workflows resolve the same session-relevant values |
| Production Compose overlay | Production safety overlay used with the base file | Requires the production environment and defaults auth to enabled; otherwise inherits base-service flag values |
| Per-session ontology input | Request-level override applied after the global snapshot | May select an ontology profile or override advisory, auto-answer, reasoning, and question-strategy Booleans only |

Compose and environment values are deployment choices, not alternative
definitions of the code defaults. Effective per-session values are frozen when
the session is created.

`src.main` and `src.tasks.celery_app` call
`load_process_environment()` before application imports. It reads `.env` by
default, supports `INFERRA_ENV_FILE`, and can be disabled with
`INFERRA_LOAD_DOTENV=false`. Invalid numeric flag values fail fast in both
processes rather than silently falling back. Compose uses `.env` for host-side
interpolation, exports the resolved values, and disables container-side dotenv
loading.

Runtime wiring is enforced as follows:

- `USE_HYPERGRAPH`, `LAYERED_MEMORY`, and `STRICT_PORT_CONTRACTS` are
  required-true compatibility invariants at API/worker startup and session
  creation. Direct construction remains available for migration tests only.
- `ASYNC_POST_REASONING` and `GENERATE_POST_REASONING_TTL` must be enabled or
  disabled together.
- `ML_OPTIMIZED_DFS` controls whether stored history reaches
  `MLTopologicalSortStrategy`.
- stalled inference sessions construct the legacy or hybrid orchestrator and
  real or null reasoning router from their frozen snapshot; abduction,
  induction, and confidence gates are propagated into that router.
- `PROV_O_TRACE` gates trace export and `ENRICHED_API` gates provenance and
  reasoning enrichment without changing the response schema.
- request `enabled` fields can opt out of globally enabled reasoning features,
  but cannot bypass a disabled process flag.

### Ontology Assistance Profiles

Pre-built profiles toggling ontology flags together:

| Profile | Advisory | Auto-Answer | Reasoning | Question Strategy |
|---------|----------|-------------|-----------|-------------------|
| `off` | ❌ | ❌ | ❌ | ❌ |
| `advisory` | ✅ | ❌ | ❌ | ❌ |
| `auto_answer` | ✅ | ✅ | ❌ | ❌ |
| `reasoning` | ✅ | ✅ | ✅ | ❌ |
| `full_semantic_pilot` | ✅ | ✅ | ✅ | ✅ |

---

## 3. API Reference

The endpoint inventory below is the current broad development profile. It is not
the Core 1.0 production contract. The package-backed `core` profile will exclude
AEGIS, LLM, files, experimental reasoning, ontology authoring/sync, private demo,
and legacy routes; disabled capabilities must be absent from generated OpenAPI.

### `/api/v1/rules` — Rule Set CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/rules` | List all rule sets |
| `POST` | `/api/v1/rules` | Create rule set |
| `GET` | `/api/v1/rules/{name}` | Get rule set detail + text |
| `POST` | `/api/v1/rules/{name}/versions` | Create new version |
| `GET` | `/api/v1/rules/{name}/graph` | Get dependency graph |
| `GET` | `/api/v1/rules/{name}/ontology` | Get RDF projection triples |
| `GET` | `/api/v1/rules/{name}/ontology/artifact` | Get full ontology artifact |
| `GET` | `/api/v1/rules/{name}/ontology/artifact/download` | Download TTL file |
| `POST` | `/api/v1/rules/{name}/ontology/sync` | Trigger async sync to Fuseki |
| `POST` | `/api/v1/rules/{name}/ontology/sync-collection` | Sync rule + imports |
| `POST` | `/api/v1/rules/ontology/sync-all` | Sync all rules |
| `GET` | `/api/v1/rules/{name}/targets` | List reachable target nodes |

### `/api/v1/inference` — Session-Based Inference

#### Session Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/inference/sessions` | Create session |
| `GET` | `/api/v1/inference/sessions` | List sessions |
| `DELETE` | `/api/v1/inference/sessions/{id}` | Delete session |
| `POST` | `/api/v1/inference/sessions/ml` | Create ML-enhanced session |

#### Question/Answer Flow
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/inference/next-question?session_id=` | Get next question(s) |
| `POST` | `/api/v1/inference/feed-answer?session_id=` | Feed answer |
| `POST` | `/api/v1/inference/defer-question` | Defer semantic-completion question |
| `POST` | `/api/v1/inference/reset-answer` | Edit/undo answered question |

#### Result & Trace
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/inference/summary?session_id=` | Working memory summary |
| `GET` | `/api/v1/inference/trace?session_id=&format=` | PROV-O trace (turtle/json-ld) |
| `POST` | `/api/v1/inference/history` | Persist session as ML history |

#### Case-Run Ontology Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/inference/ontology-artifact` | Generate case-run ontology |
| `GET` | `/api/v1/inference/ontology-artifact/download` | Download as Turtle |
| `GET` | `/api/v1/inference/ontology-artifact/collision-check` | Check Fuseki named graph |
| `POST` | `/api/v1/inference/ontology-artifact/sync` | Push case-run to Fuseki |

### `/api/v1/validation` — Rule Validation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/validation/validate` | Validate rule text |

### `/api/v1/sync` — Async Pipeline Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/sync/status` | Celery task status |
| `GET` | `/api/v1/rules/{name}/imports` | Import tree |
| `GET` | `/api/v1/rules/{name}/validate` | Import-aware validation |

### `/api/v1/ontology` — Fuseki Graph Query & Path Resolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/ontology/fuseki/graphs` | List Fuseki named graphs |
| `GET` | `/api/v1/ontology/fuseki/graph` | Get triples from named graph |
| `POST` | `/api/v1/ontology/chat/query` | Natural language → SPARQL |
| `POST` | `/api/v1/ontology/path/resolve` | Resolve decision path |

### `/api/v1/aegis` — AEGIS Workflow Runtime

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/POST` | `/api/v1/aegis/autonomy-levels` | Read/update autonomy scale |
| `GET` | `/api/v1/aegis/agents/risk-heatmap` | Agent risk heatmap |
| `GET/POST` | `/api/v1/aegis/workflows` | List/create workflows |
| `POST` | `/api/v1/aegis/workflows/{id}/validate` | Validate workflow |
| `POST` | `/api/v1/aegis/workflows/{id}/generate` | LLM-assisted generation |
| `POST` | `/api/v1/aegis/workflows/{id}/activate` | Activate workflow |
| `GET/POST` | `/api/v1/aegis/trigger-policies` | Trigger policy management |

### `/api/v1/aegis/rules` — AEGIS Rule Store

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/POST` | `/api/v1/aegis/rules` | List/query AEGIS rules |
| `POST` | `/api/v1/aegis/rules/{name}/policy-integrity` | Policy integrity hash |
| `POST` | `/api/v1/aegis/rules/{name}/import-tree` | Import tree |

### `/api/v1/files` — Document Conversion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/files/to-text` | Convert PDF/DOCX → text |
| `POST` | `/api/v1/files/to-rule` | Convert document → rule text |
| `POST` | `/api/v1/files/download-rule` | Download converted rule |

### `/api/v1/metrics` — Prometheus Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/metrics` | Export metrics |

### `/api/v1/llm` — LLM Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/llm/providers` | List providers + models |
| `POST` | `/api/v1/llm/resolve` | Resolve provider+model config |
| `POST` | `/api/v1/llm/test` | Test LLM connectivity |
| `GET/POST` | `/api/v1/llm/product-configuration/{id}` | Per-product config |

### `/api/v1/reasoning` — Abduction, Induction, Goal Mapping

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/reasoning/abduction` | Propose hypotheses |
| `POST` | `/api/v1/reasoning/induction/start` | Start batch discovery |
| `GET` | `/api/v1/reasoning/induction/{job_id}` | Check job status |
| `POST` | `/api/v1/reasoning/induction/promote` | Promote candidate rule |
| `POST` | `/api/v1/reasoning/map-goal` | NL → rule targets |

### `/api/v1/system` — System Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/system/health` | Database + Fuseki health |
| `GET` | `/api/v1/system/feature-flags` | Flag snapshot |

---

## 4. Core Domain Capabilities

### Rule Parsing Pipeline

1. **`RuleSetReader`** — Reads rule from path, binary, or text
2. **`RuleSetScanner`** — Scans lines, builds 4-space indentation hierarchy
3. **`RuleSetParser`** — Classifies lines via tokenizer + regex matchers
4. **Dependency Graph** → `HyperAdjacencyGraph` from parsed dependencies
5. **Topological Sort** → `MLTopologicalSortStrategy` (history-aware) or DFS

### Modular Imports (Phase 2)

- `RULE SET: <name>` — File self-identification
- `IMPORT: <name>` — Pull another rule set's declarations + rules
- `RuleSetImportResolver` — DFS with cycle detection, depth limit (100), timeout guard
- Both directives stripped from parser input by `_strip_modular_directives`

### Backward-Chaining Inference Engine

- **Goal-driven:** Evaluate from target node backward through dependency graph
- **Question flow:** `get_next_question_with_goal_name()` → `feed_answer_to_node()` → convergence
- **Fact value types:** BOOLEAN, NUMBER, DATE, TEXT, LIST, COLLECTION
- **Dependency types:** AND, OR, NOT, KNOWN, MANDATORY, OPTIONALLY, POSSIBLY, NEEDS, WANTS
- **Iterate:** `ITERATE: <quantifier> LIST OF <list_name>` with ALL/NONE/SOME/AT LEAST N/etc.
- **`IterationEngine`** — Port-compliant, thread-safe, `FactSource.INFERRED` tagging

### Layered Fact Store

```
Unified read view: SEMANTIC < HYPOTHETICAL < LEARNED < INFERRED < ASSERTED
```

- Each write tagged with `FactSource`
- `_overrides` set tracks ASSERTED-over-INFERRED for truth-maintenance
- Timestamps per fact for staleness checks

### Ontology Integration (Phase 3)

- **`InferraToRdfCompiler`** — Compiles INFERRA rules → RDF triples (`inf:` namespace)
- **`FusekiAdapter`** — Idempotent SPARQL INSERT (DELETE + INSERT by `source_hash`)
- **`SemanticFactEnricher` / `OntologyIndex`** — Ontology binding maps, value suggestions
- **`OntologyReasoner`** — Materialized reasoning: hierarchy closure, confidence-gated inference
- **`SemanticQuestionStrategy`** — Ranks questions by ontology evidence (advisory only)
- **Full Semantic Pilot** — Post-decision semantic completion, TTL export, `/latest` pointer resolution

### Reasoning Router (Phase 5)

- Deduction-first loop (minimum 2 iterations before escalation)
- Abduction: LLM-based or Z3 constraint-based hypothesis generation
- Induction: Celery batch jobs for pattern discovery from traces
- Confidence thresholds per rule, per session, with hierarchical fallback

### AEGIS Workflow Runtime

- **Workflow Authoring:** Deterministic action firewall templates
- **Phase 3 Runtime:** Event ledger (`REQUEST → RECEIPT_SEAL`)
- **Autonomy levels:** manual → assisted → supervised_autonomy → certified_autonomy (threshold 0.85)
- **Trigger Policies:** Outcome-triggered downstream rule execution

### LLM Integration

- **Provider Registry:** Modal Research (GLM-5/5.1), Z.AI, NVIDIA
- **Orchestrator:** `RealLLMOrchestrator` with circuit breaker (3 failures/30s recovery)
- **Streamer:** SSE-based streaming for chat
- **Product-scoped configuration:** Per-product enable/disable, budget, allowed operations

### PROV-O Trace Generation

- W3C PROV-O ontology traces for session runs
- TTL and JSON-LD serialization
- Captures session provenance: goal, working memory, reasoning mode

---

## 5. Use Cases

### Use Case 1: Legislative Eligibility Determination (Core)

A policy officer encodes legislation as INFERRA rules. A caseworker runs an inference session:

1. Create rule: `POST /api/v1/rules` with legislative text
2. Create session: `POST /api/v1/inference/sessions` with rule_name + target
3. Question loop: `GET /next-question` → `POST /feed-answer` until convergence
4. Get summary: `GET /inference/summary` with fact sources
5. Persist history: `POST /inference/history` for ML ordering

### Use Case 2: Modular Policy Libraries (Phase 2)

Shared definitions (rates, thresholds) in separate rule sets:

- `RULE SET: dva_rate_thresholds` — central rate constants
- Other rule sets: `IMPORT: dva_rate_thresholds` — pull in declarations
- Transient merge for parsing; files independently editable

### Use Case 3: Ontology-Enhanced Decision Support (Phase 3)

Same as Use Case 1, but with `ontology_profile: "advisory"`:

- Ontology suggestions appear alongside each question
- Auto-answer fills defaults from ontology
- Reasoning materializes inferred facts from hierarchy
- Question strategy reorders/prunes based on semantic evidence

### Use Case 4: Full Semantic Pilot with Fuseki Export (Phase 3)

Interactive post-decision semantic completion:

1. Create session with `ontology_profile: "full_semantic_pilot"`
2. Complete normal question flow to convergence
3. Continue with `answer_context: "FULL_SEMANTIC_COMPLETION"` to answer/defer remaining questions
4. Export: `GET /inference/ontology-artifact/download` → Turtle file
5. Sync: `POST /inference/ontology-artifact/sync` → Fuseki named graph
6. Query later: `POST /ontology/chat/query` with natural language

### Use Case 5: Decision Path Forensics (Phase 3)

Given a case outcome in Fuseki, trace why:

1. `POST /ontology/path/resolve` with selected row + graph URIs
2. Returns CaseRun → CaseFact edges + structural dependency path
3. Shows semantic traces alongside rule dependencies

### Use Case 6: ML-Enhanced Inference Ordering (Phase 1 WS-1)

History accumulates from past sessions:

- `POST /inference/sessions/ml` uses `MLTopologicalSortStrategy`
- Most-frequently-true nodes asked first → fewer questions

### Use Case 7: Multi-Step AEGIS Workflow Automation (Phase 3)

Insurance fraud detection orchestration:

1. Author workflow: `POST /aegis/workflows`
2. Validate: `POST /aegis/workflows/{id}/validate`
3. Activate: `POST /aegis/workflows/{id}/activate`
4. Progress: `REQUEST → RULE_GATE → OPTION_SET → ACTUATION → RECEIPT_SEAL`
5. Trigger policy: "if fraud detected, auto-run investigation rule set"

### Use Case 8: Abduction for Stuck Inference (Phase 5)

When deduction can't reach a goal:

1. `POST /reasoning/abduction` → LLM proposes hypotheses
2. Best hypothesis injected as `FactSource.HYPOTHETICAL`
3. New facts may unlock remaining nodes → convergence

### Use Case 9: Induction — Rule Discovery from Traces (Phase 5)

After many sessions generate trace corpus:

1. Start batch: `POST /reasoning/induction/start` → Celery analyzes traces
2. Check status: `GET /reasoning/induction/{job_id}` → candidate rules
3. Promote: `POST /reasoning/induction/promote` → draft rule set

### Use Case 10: Document-to-Rule Conversion (LLM-assisted)

1. Upload PDF/DOCX: `POST /files/to-text`
2. Convert to rule: `POST /files/to-rule` → LLM generates INFERRA text
3. Download or save to rule store

### Use Case 11: Natural Language Ontology Querying (Phase 3)

1. Sync rules: `POST /rules/{name}/ontology/sync`
2. Query: `POST /ontology/chat/query` with natural language
3. Returns structured bindings + graph overlay targets

### Use Case 12: Multi-Tenant LLM Governance (Phase 4)

1. Configure per-product LLM: `POST /llm/product-configuration/aegis`
2. Different products get different providers/models
3. Evaluation gate status persisted for audit

---

## 6. Implementation Status

Implementation presence is not production approval. The independent Core
package, narrow API profile, migrations/immutable revisions, durable ontology
audit, identity decisions, and release evidence described in the active
governance documents remain P0 gates. Statements below that use
"production-ready" describe local implementation maturity at the time they were
written, not current release authorization.

### ✅ Fully Implemented & Production-Ready

#### Core Inference Engine (Phase 1)
- ✅ Backward-chaining inference with goal-driven evaluation
- ✅ `HyperAdjacencyGraph` with WS-3/WS-4/WS-7 topology support
- ✅ `LayeredFactStore` with provenance tagging and truth-maintenance
- ✅ Full question flow API (next-question, feed-answer, defer, reset-answer)
- ✅ Iterate quantifiers (ALL/NONE/SOME/AT LEAST N/etc.)
- ✅ All fact value types (BOOLEAN, NUMBER, DATE, TEXT, LIST, COLLECTION)
- ✅ All dependency types (AND/OR/NOT/KNOWN/MANDATORY/etc.)
- ✅ History-aware topological sort
- ✅ Session management (in-memory + Redis-backed)

#### Rule Parsing & Validation
- ✅ Full parser pipeline (Reader → Scanner → Parser → Graph)
- ✅ All line type detection (Metadata, ValueConclusion, ExprConclusion, Comparison, Iterate)
- ✅ 4-space indentation hierarchy
- ✅ Comment metadata preservation
- ✅ Declaration validator with waiver system

#### HTTP API (14 Routers)
- ✅ All routes implemented and tested

#### AEGIS Workflow Runtime
- ✅ Workflow authoring with deterministic action firewalls
- ✅ Phase 3 runtime with full event ledger lifecycle
- ✅ 4-level autonomy scale with confidence thresholds
- ✅ Trigger policies (direct + outcome-triggered)
- ✅ Synthetic fixtures (insurance fraud, robot fleet planner)
- ✅ Risk heatmap from event ledger

#### Ontology Integration
- ✅ `InferraToRdfCompiler` (INFERRA → RDF)
- ✅ `FusekiAdapter` (idempotent SPARQL, named graphs)
- ✅ Full Semantic Pilot (post-decision completion, TTL export, `/latest` pointers)
- ✅ Ontology chat (NL → SPARQL with guardrails)
- ✅ Path resolution (semantic + structural graph traversal)
- ✅ Semantic question strategy (advisory ranking)

#### LLM Integration
- ✅ Provider registry (Modal Research, Z.AI, NVIDIA)
- ✅ `RealLLMOrchestrator` with circuit breaker, retry, cost tracking, tracing
- ✅ SSE streaming for chat
- ✅ Prompt sanitizer, text splitter
- ✅ Product-scoped configuration
- ✅ Null/Mock orchestrators for LLM-disabled operation

#### Infrastructure
- ✅ FastAPI app with middleware stack (auth, correlation ID, rate limiting, CORS, logging)
- ✅ OpenTelemetry observability
- ✅ API key auth with per-route scope enforcement
- ✅ Rate limiter (per-IP throttling)
- ✅ Secrets management (env vars + AWS Secrets Manager)
- ✅ SQLAlchemy repositories

#### Celery Async Pipeline
- ✅ Rule sync tasks (Celery → Fuseki)
- ✅ Dead letter queue
- ✅ Projection metadata in Redis
- ✅ Idempotency with inflight task registry
- ✅ Circuit breaker for Fuseki
- ✅ Post-reasoning tasks
- ✅ Induction batch jobs

#### Testing
- ✅ 137 test files covering all major components

---

## 7. Gap Analysis

### 🟡 Partially Implemented (Mock/Null Adapters Exist)

#### Abduction (Phase 5)
- ✅ Port contract defined
- ✅ `LLMAbductionAdapter` and `Z3AbductionAdapter` exist
- ✅ `ReasoningRouter` escalation logic
- ⚠️ **Gap:** No production tuning of confidence thresholds
- ⚠️ **Gap:** Z3 adapter needs constraint library expansion
- ⚠️ **Gap:** Hypotheses not persisted as first-class objects

#### Induction (Phase 5)
- ✅ Port contract defined
- ✅ `CeleryInductionAdapter` orchestration
- ✅ `start_batch`, `get_status`, `promote` endpoints
- ⚠️ **Gap:** Pattern mining algorithm is basic frequency analysis only
- ⚠️ **Gap:** No statistical significance testing
- ⚠️ **Gap:** Candidate rule promotion creates draft but no auto-validation

#### LLM Enhancements (Phase 4)
- ✅ `LLMOrchestratorPort` contract
- ✅ `RealLLMOrchestrator` methods implemented
- ⚠️ **Gap:** `enhance_question_prompt` returns basic template
- ⚠️ **Gap:** `generate_explanation` produces generic summary
- ⚠️ **Gap:** No A/B testing framework

#### PROV-O Trace (Phase 3)
- ✅ Trace extraction and serialization
- ✅ `GET /trace` endpoint
- ⚠️ **Gap:** No UI visualization component
- ⚠️ **Gap:** No export to external PROV-O tools (ProvViz, etc.)
- ⚠️ **Gap:** Trace URL not included in summary by default

#### Ontology Auto-Answer (Phase 3)
- ✅ `OntologyReasoner` materialization logic
- ✅ `ONTOLOGY_AUTO_ANSWER_ENABLED` flag
- ⚠️ **Gap:** No per-fact confidence threshold (all-or-nothing)
- ⚠️ **Gap:** Auto-answered facts not distinguished in UI
- ⚠️ **Gap:** No user override mechanism mid-session

### 🔴 Not Implemented (Interfaces Only or Design-Only)

#### Certified Autonomy (AEGIS Phase 3+)
- ✅ Autonomy levels enum up to `certified_autonomy`
- ✅ Confidence threshold constant (0.85)
- 🔴 **Gap:** No template certification workflow
- 🔴 **Gap:** No evidence hash validation gate
- 🔴 **Gap:** No policy hash expiration checking
- 🔴 **Gap:** Fallback readiness check not implemented

#### GraphRAG Retrieval (Phase 3.5)
- ✅ Evaluation harness exists
- 🔴 **Gap:** No production GraphRAG retriever
- 🔴 **Gap:** No embedding generation
- 🔴 **Gap:** No vector store integration

#### Neuro-Symbolic Golden Cases (Phase 5)
- ✅ Acceptance test exists
- 🔴 **Gap:** No golden case repository
- 🔴 **Gap:** No automatic regression testing
- 🔴 **Gap:** No confidence fusion algorithm

#### Multi-Tenant Owner Scoping (Phase 4)
- ✅ Auth middleware extracts owner_id
- ✅ Repositories accept owner filter
- 🔴 **Gap:** No tenant/organization concept in data model
- 🔴 **Gap:** No cross-tenant access control rules
- 🔴 **Gap:** No tenant-scoped rule visibility filtering

#### Real-Time Collaboration
- 🔴 **Gap:** No WebSocket endpoints
- 🔴 **Gap:** No operational transform
- 🔴 **Gap:** No presence indicators

---

## 8. Deployment Guide

### Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Runtime |
| PostgreSQL | 14+ | Rule storage, session metadata, AEGIS ledger |
| Redis | 6+ | Session store, Celery broker, idempotency cache |
| Apache Jena Fuseki | 4.9+ | RDF ontology store |
| Celery | 5.3+ | Async task pipeline |
| Apache Z3 | 4.12+ | Constraint-based abduction |

### Environment Variables

Create `.env` file:

```bash
# Application
INFERRA_ENV=development
INFERRA_DEBUG=true
INFERRA_LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://inferra:inferra_secret@localhost:5432/inferra

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Fuseki
FUSEKI_URL=http://localhost:3030
FUSEKI_DATASET=inferra
FUSEKI_USERNAME=admin
FUSEKI_PASSWORD=fuseki_secret

# LLM Providers
MODALRESEARCH_API_KEY=your_modal_key
ZAI_API_KEY=your_zai_key
NVIDIA_API_KEY=your_nvidia_key

# Feature Flags (defaults shown)
INFERRA_USE_HYPERGRAPH=true
INFERRA_LEGACY_ITERATE=true
INFERRA_LAYERED_MEMORY=true
INFERRA_ML_OPTIMIZED_DFS=false
INFERRA_ASYNC_SYNC_ENABLED=false
INFERRA_MODULAR_IMPORTS=false
INFERRA_HYBRID_ORCHESTRATOR=false
INFERRA_ASYNC_POST_REASONING=false
INFERRA_GENERATE_POST_REASONING_TTL=false
INFERRA_PROV_O_TRACE=false
INFERRA_ENRICHED_API=false
INFERRA_ONTOLOGY_ADVISORY_ENABLED=false
INFERRA_ONTOLOGY_AUTO_ANSWER_ENABLED=false
INFERRA_ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD=0.85
INFERRA_ONTOLOGY_REASONING_ENABLED=false
INFERRA_ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD=0.85
INFERRA_ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH=1
INFERRA_ONTOLOGY_REASONING_MAX_CLOSURE_DEPTH=10
INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED=false
INFERRA_REDIS_SESSION_STORE=false
INFERRA_LLM_ENHANCEMENTS=false
INFERRA_STRICT_PORT_CONTRACTS=true
INFERRA_OBSERVABILITY_ENABLED=false
INFERRA_AUTH_ENABLED=false
INFERRA_ABDUCTION_ENABLED=false
INFERRA_INDUCTION_PIPELINE=false
INFERRA_REASONING_ROUTER=true
INFERRA_CONFIDENCE_THRESHOLDS=true

# Security (when AUTH_ENABLED=true)
INFERRA_API_KEY_HEADER=X-API-Key
INFERRA_OWNER_ID_HEADER=X-Owner-ID

# Observability
OTEL_SERVICE_NAME=inferra-platform
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Circuit Breaker
INFERRA_LLM_CIRCUIT_FAILURE_THRESHOLD=3
INFERRA_LLM_CIRCUIT_RECOVERY_TIMEOUT_SECONDS=30

# Rate Limiting
INFERRA_RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### Database Setup

```bash
psql -U postgres <<EOF
CREATE DATABASE inferra;
CREATE USER inferra WITH PASSWORD 'inferra_secret';
GRANT ALL PRIVILEGES ON DATABASE inferra TO inferra;
EOF

cd inferra-platform
alembic upgrade head  # If using Alembic
```

### Fuseki Setup

```bash
# With Docker
docker run -d --name fuseki -p 3030:3030 \
  -e ADMIN_PASSWORD=fuseki_secret \
  staincom/apache-jena-fuseki

# Or download manually
wget https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-4.9.0.tar.gz
tar -xzf apache-jena-fuseki-4.9.0.tar.gz
cd apache-jena-fuseki-4.9.0
./fuseki-server --mem /inferra &
```

### Redis Setup

```bash
docker run -d --name inferra-redis -p 6379:6379 redis:7
```

### Running the Application

#### Development Mode

```bash
cd inferra-platform
python -m pip install -e packages/inferra-core
python -m pip install -e ".[async,semantic,reasoning,observability]"
INFERRA_ENV_FILE=.env uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

#### Production Mode

```bash
INFERRA_LOAD_DOTENV=false gunicorn src.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

#### With Celery Workers

Terminal 1 — API:
```bash
INFERRA_ENV_FILE=.env uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Terminal 2 — Worker:
```bash
INFERRA_ENV_FILE=.env celery -A src.tasks.celery_app worker --loglevel=info
```

### Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://inferra:inferra_secret@db:5432/inferra
      - REDIS_URL=redis://redis:6379/0
      - FUSEKI_URL=http://fuseki:3030
      - INFERRA_ASYNC_SYNC_ENABLED=true
    depends_on:
      - db
      - redis
      - fuseki

  celery-worker:
    build: .
    environment:
      - DATABASE_URL=postgresql://inferra:inferra_secret@db:5432/inferra
      - REDIS_URL=redis://redis:6379/0
      - CELERY_BROKER_URL=redis://redis:6379/0
      - FUSEKI_URL=http://fuseki:3030
    depends_on:
      - db
      - redis
      - fuseki

  db:
    image: postgres:14
    environment:
      - POSTGRES_DB=inferra
      - POSTGRES_USER=inferra
      - POSTGRES_PASSWORD=inferra_secret
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

  fuseki:
    image: staincom/apache-jena-fuseki
    environment:
      - ADMIN_PASSWORD=fuseki_secret
    volumes:
      - fuseki_data:/var/lib/fuseki/databases

volumes:
  postgres_data:
  redis_data:
  fuseki_data:
```

Run:
```bash
docker-compose up -d
```

### Health Checks

```bash
curl http://localhost:8000/api/v1/system/health
curl http://localhost:8000/api/v1/system/feature-flags
curl http://localhost:8000/api/v1/metrics
```

---

## 9. Test Coverage

### Test File Distribution

| Category | Files | Focus |
|----------|-------|-------|
| HTTP Routes | 19 | All 14 routers + integration |
| Domain Logic | 45 | Parser, inference, fact store, iteration, ontology |
| Adapters | 20 | Fuseki, LLM, session stores, repositories |
| Infrastructure | 14 | Auth, rate limiter, observability, middleware |
| Contracts/Ports | 9 | All 8 port compliance tests |
| Benchmarks | 6 | Performance baselines |
| Integration | 8 | E2E session lifecycle, reasoning |
| Services | 9 | RuleService, validation, ontology services |
| Tasks | 4 | Celery app, rule sync, induction |
| Evaluation | 3 | GraphRAG, neuro-symbolic cases |
| **Total** | **137** | |

### Coverage by Component

#### ✅ Well-Tested (>80%)
- Rule Parser (scanner, parser, tokenizer)
- Inference Engine (backward-chain, question strategy)
- Fact Store (layered memory, truth-maintenance)
- All HTTP Routes
- HyperAdjacencyGraph
- Ontology Compiler
- Fuseki Adapter
- Import Resolver
- Auth Middleware
- Rate Limiter

#### 🟡 Moderately Tested (50-80%)
- AEGIS Workflow Runtime (synthetic fixtures)
- Trigger Policies
- Semantic Question Strategy
- LLM Orchestrator
- Celery Tasks
- Ontology Chat
- Path Resolution
- History Persistence

#### 🔴 Lightly Tested (<50%)
- Abduction Adapters
- Induction Pipeline (pattern mining untested)
- GraphRAG Retrieval (eval harness only)
- Neuro-Symbolic Cases (acceptance test only)
- Certified Autonomy
- Multi-Tenant Scoping
- PROV-O Trace Visualization
- Observability/OTel
- Cost Tracking

### Notable Gaps

- ❌ No load/stress tests (1000+ concurrent sessions)
- ❌ No chaos testing (network partitions, service outages)
- ❌ No security penetration tests
- ❌ No backwards compatibility tests
- ❌ No migration tests
- ❌ No multi-region tests

### Test Execution

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# By category
pytest tests/domain/inference/ -v
pytest tests/adapters/inbound/http/routes/ -v
pytest tests/contracts/ -v

# Benchmarks
pytest tests/benchmarks/ -v --benchmark-only
```

---

## 10. Ontology Integration Examples

This section provides detailed, copy-paste-ready examples for using the ontology integration features.

### Example 10.1: Sync a Rule Set to Fuseki

**Prerequisites:**
- Fuseki running at `http://localhost:3030` with dataset `inferra`
- `FUSEKI_URL`, `FUSEKI_DATASET`, `FUSEKI_USERNAME`, `FUSEKI_PASSWORD` set in `.env`
- `INFERRA_ASYNC_SYNC_ENABLED=true` (for async) or manual sync works without it

**Step 1: Create a rule with rich type hierarchy**

```bash
curl -X POST http://localhost:8000/api/v1/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "medical_triage",
    "text": "RULE SET: medical_triage\n\n# Type hierarchy with inheritance\nTYPE: Person\nTYPE: Patient SUBTYPE OF Person\nTYPE: EmergencyPatient SUBTYPE OF Patient\n\n# Fields\nFIELD: Patient.age AS NUMBER\nFIELD: Patient.has_chest_pain AS BOOLEAN\nFIELD: Patient.has_shortness_of_breath AS BOOLEAN\nFIELD: Patient.blood_pressure_systolic AS NUMBER\nFIELD: Patient.blood_pressure_diastolic AS NUMBER\nFIELD: Patient.triage_category AS TEXT\n\n# Rules\n\"patient requires immediate attention\" IF\n  MANDATORY: Patient.has_chest_pain IS TRUE\n  OR: Patient.has_shortness_of_breath IS TRUE\n  OR: Patient.blood_pressure_systolic IS GREATER THAN 180\n\n\"patient triage category is RED\" IF\n  MANDATORY: patient requires immediate attention IS TRUE\n  AND: Patient.triage_category EQUALS \"RED\"\n\n\"patient requires urgent assessment\" IF\n  MANDATORY: Patient.age IS AT LEAST 65\n  AND OPTIONALLY: Patient.has_chest_pain IS TRUE\n",
    "category": "clinical",
    "description": "Emergency department triage decision support"
  }'
```

**Step 2: Preview the RDF projection**

```bash
curl http://localhost:8000/api/v1/rules/medical_triage/ontology
```

Response:
```json
{
  "rule_name": "medical_triage",
  "version": 1,
  "triple_count": 47,
  "triples": [
    {
      "subject": "inf:Patient",
      "predicate": "rdf:type",
      "object": "owl:Class"
    },
    {
      "subject": "inf:Patient",
      "predicate": "rdfs:subClassOf",
      "object": "inf:Person"
    },
    {
      "subject": "inf:has_chest_pain",
      "predicate": "rdf:type",
      "object": "owl:DatatypeProperty"
    },
    {
      "subject": "inf:has_chest_pain",
      "predicate": "rdfs:domain",
      "object": "inf:Patient"
    },
    {
      "subject": "inf:has_chest_pain",
      "predicate": "rdfs:range",
      "object": "xsd:boolean"
    }
    // ... more triples
  ]
}
```

**Step 3: Sync to Fuseki (manual, synchronous)**

```bash
curl -X POST http://localhost:8000/api/v1/rules/medical_triage/ontology/sync
```

Response:
```json
{
  "status": "synced",
  "rule_name": "medical_triage",
  "named_graph": "inferra:rule:medical_triage:v1",
  "triple_count": 47,
  "source_hash": "a3f2b8c9...",
  "synced_at": "2026-07-03T10:30:00Z"
}
```

**Step 4: Verify in Fuseki**

```bash
curl "http://localhost:8000/api/v1/ontology/fuseki/graphs"
```

Response:
```json
{
  "graphs": [
    {
      "name": "inferra:rule:medical_triage:v1",
      "triple_count": 47,
      "description": "Rule projection: medical_triage v1"
    }
  ]
}
```

---

### Example 10.2: Ontology-Enhanced Inference Session

**Step 1: Create session with advisory profile**

```bash
curl -X POST http://localhost:8000/api/v1/inference/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "medical_triage",
    "target_node": "patient requires immediate attention",
    "ontology_profile": "advisory"
  }'
```

Response:
```json
{
  "session_id": "sess_ont_456",
  "rule_name": "medical_triage",
  "target_node": "patient requires immediate attention",
  "ontology_profile": "advisory",
  "state": "in_progress",
  "flags": {
    "ONTOLOGY_ADVISORY_ENABLED": true,
    "ONTOLOGY_AUTO_ANSWER_ENABLED": false,
    "ONTOLOGY_REASONING_ENABLED": false,
    "ONTOLOGY_QUESTION_STRATEGY_ENABLED": false
  }
}
```

**Step 2: Get next question with ontology suggestions**

```bash
curl "http://localhost:8000/api/v1/inference/next-question?session_id=sess_ont_456"
```

Response (note the `ontology_suggestions` field):
```json
{
  "session_id": "sess_ont_456",
  "questions": [
    {
      "node_name": "Patient.has_chest_pain",
      "question_text": "Does the patient have chest pain?",
      "value_type": "BOOLEAN",
      "mandatory": true,
      "ontology_suggestions": {
        "advisory_value": null,
        "confidence": null,
        "derivation_path": [],
        "related_facts": [
          {
            "fact_name": "Patient.has_shortness_of_breath",
            "relationship": "clinically_correlated",
            "note": "Often co-occur in cardiac events"
          }
        ],
        "constraints": {
          "allowed_values": [true, false]
        },
        "default_value": null,
        "is_auto_answered": false
      }
    }
  ],
  "iterate_progress": null,
  "converged": false
}
```

**Step 3: Feed answer**

```bash
curl -X POST "http://localhost:8000/api/v1/inference/feed-answer?session_id=sess_ont_456" \
  -H "Content-Type: application/json" \
  -d '{
    "node_name": "Patient.has_chest_pain",
    "value": true,
    "value_type": "BOOLEAN"
  }'
```

---

### Example 10.3: Auto-Answer from Ontology Defaults

**Prerequisites:** Enable auto-answer flag or use `auto_answer` profile.

**Step 1: Create session with auto-answer profile**

```bash
curl -X POST http://localhost:8000/api/v1/inference/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "medical_triage",
    "target_node": "patient triage category is RED",
    "ontology_profile": "auto_answer"
  }'
```

**Step 2: Get next question**

If ontology has default values or can derive a fact from existing knowledge, the response includes pre-filled answers:

```json
{
  "session_id": "sess_auto_789",
  "questions": [
    {
      "node_name": "Patient.triage_category",
      "question_text": "What is the patient triage category?",
      "value_type": "TEXT",
      "mandatory": true,
      "ontology_suggestions": {
        "advisory_value": "RED",
        "confidence": 0.75,
        "derivation_path": [
          "inf:Patient rdfs:subClassOf inf:Person",
          "inf:triage_category rdfs:domain inf:Patient"
        ],
        "related_facts": [],
        "constraints": {
          "allowed_values": ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE"]
        },
        "default_value": "GREEN",
        "is_auto_answered": true,
        "auto_answer_cause": "ontology_default"
      }
    }
  ]
}
```

**Note:** With `ONTOLOGY_AUTO_ANSWER_ENABLED=true`, the system may automatically assert the default value without user input. Check session summary to see which facts were auto-answered.

---

### Example 10.4: Materialized Ontology Reasoning

**Prerequisites:** `ONTOLOGY_REASONING_ENABLED=true` or `ontology_profile: "reasoning"`.

When ontology reasoning is enabled, the system materializes inferred facts from subclass relationships and property characteristics.

**Step 1: Create session with reasoning profile**

```bash
curl -X POST http://localhost:8000/api/v1/inference/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "medical_triage",
    "target_node": "patient requires urgent assessment",
    "ontology_profile": "reasoning"
  }'
```

**Step 2: Feed an answer about a subclass**

```bash
curl -X POST "http://localhost:8000/api/v1/inference/feed-answer?session_id=sess_reason_101" \
  -H "Content-Type: application/json" \
  -d '{
    "node_name": "Patient.age",
    "value": 70,
    "value_type": "NUMBER"
  }'
```

**Step 3: Check summary for inferred facts**

```bash
curl "http://localhost:8000/api/v1/inference/summary?session_id=sess_reason_101"
```

Look for facts with `source: "INFERRED"` and `reasoning_mode: "ontology_materialization"`:

```json
{
  "facts": [
    {
      "fact_name": "Patient.age",
      "value": 70,
      "source": "ASSERTED",
      "reasoning_mode": null
    },
    {
      "fact_name": "Person.age",
      "value": 70,
      "source": "INFERRED",
      "reasoning_mode": "ontology_materialization",
      "derivation": "Patient SUBCLASS_OF Person → Patient.age → Person.age"
    }
  ]
}
```

The inferred `Person.age` fact can now satisfy rules that depend on the parent type.

---

### Example 10.5: Full Semantic Pilot — Post-Decision Export

This is the most advanced ontology integration, enabling complete case-run provenance export to Fuseki.

**Step 1: Create session with full semantic pilot profile**

```bash
curl -X POST http://localhost:8000/api/v1/inference/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "medical_triage",
    "target_node": "patient triage category is RED",
    "ontology_profile": "full_semantic_pilot"
  }'
```

**Step 2: Complete the normal question flow**

Loop through `next-question` → `feed-answer` until `converged: true`.

**Step 3: Continue with semantic completion**

After convergence, continue asking semantic questions to enrich the case-run ontology:

```bash
curl -X POST "http://localhost:8000/api/v1/inference/feed-answer?session_id=sess_full_202" \
  -H "Content-Type: application/json" \
  -d '{
    "node_name": "Patient.presenting_complaint",
    "value": "Severe chest pain radiating to left arm",
    "value_type": "TEXT",
    "answer_context": "FULL_SEMANTIC_COMPLETION"
  }'
```

You can also **defer** questions you don't have information for:

```bash
curl -X POST "http://localhost:8000/api/v1/inference/defer-question" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_full_202",
    "node_name": "Patient.ecg_findings"
  }'
```

Deferred questions are tracked but don't block export.

**Step 4: Generate ontology artifact**

```bash
curl "http://localhost:8000/api/v1/inference/ontology-artifact?session_id=sess_full_202"
```

Response:
```json
{
  "session_id": "sess_full_202",
  "rule_name": "medical_triage",
  "named_graph_uri": "inferra:case-run:medical_triage:sess_full_202",
  "version_ptr": "inferra:case-run:medical_triage:sess_full_202:latest",
  "ttl_content": "@prefix inf: <http://inferra.ai/ontology/> .\n@prefix prov: <http://www.w3.org/ns/prov#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\ninf:case-sess_full_202 a prov:Activity ;\n  prov:startedAtTime \"2026-07-03T11:00:00Z\"^^xsd:dateTime ;\n  prov:endedAtTime \"2026-07-03T11:05:00Z\"^^xsd:dateTime ;\n  prov:used inf:rule:medical_triage:v1 .\n\ninf:fact-Patient.has_chest_pain-sess_full_202 a inf:CaseFact ;\n  inf:factName \"Patient.has_chest_pain\" ;\n  inf:factValue \"true\"^^xsd:boolean ;\n  inf:source \"ASSERTED\" ;\n  prov:wasGeneratedBy inf:case-sess_full_202 .\n\n// ... more facts\n",
  "triple_count": 89,
  "includes_deferred": false
}
```

**Step 5: Check for collision (named graph already exists?)**

```bash
curl "http://localhost:8000/api/v1/inference/ontology-artifact/collision-check?session_id=sess_full_202"
```

Response:
```json
{
  "session_id": "sess_full_202",
  "named_graph_uri": "inferra:case-run:medical_triage:sess_full_202",
  "exists": false,
  "can_sync": true
}
```

**Step 6: Sync to Fuseki**

```bash
curl -X POST "http://localhost:8000/api/v1/inference/ontology-artifact/sync?session_id=sess_full_202"
```

Response:
```json
{
  "status": "synced",
  "session_id": "sess_full_202",
  "named_graph_uri": "inferra:case-run:medical_triage:sess_full_202",
  "version_ptr": "inferra:case-run:medical_triage:sess_full_202:latest",
  "triple_count": 89,
  "synced_at": "2026-07-03T11:06:00Z"
}
```

**Step 7: Query the case-run later**

```bash
curl -X POST http://localhost:8000/api/v1/ontology/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "natural_language_query": "Show me all RED triage cases with chest pain",
    "graph_uris": ["inferra:case-run:medical_triage:sess_full_202"],
    "row_limit": 100
  }'
```

Response:
```json
{
  "query_translated": "SELECT ?case ?patient ?chest_pain WHERE { ... }",
  "rows": [
    {
      "case": "inf:case-sess_full_202",
      "patient": "inf:Patient",
      "chest_pain": true,
      "triage_category": "RED"
    }
  ],
  "row_count": 1,
  "graph_scope": ["inferra:case-run:medical_triage:sess_full_202"],
  "guardrails_receipt": {
    "allowed_operations": ["SELECT"],
    "blocked_patterns": [],
    "timeout_ms": 5000,
    "max_retries": 3
  }
}
```

---

### Example 10.6: Decision Path Forensics

Given a case outcome, trace the decision path:

**Step 1: Run a query to get a binding**

```bash
curl -X POST http://localhost:8000/api/v1/ontology/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "natural_language_query": "Find the case where patient had chest pain and RED triage",
    "graph_uris": ["inferra:case-run:medical_triage:sess_full_202"],
    "row_limit": 10
  }'
```

Assume the first row has `case: "inf:case-sess_full_202"`.

**Step 2: Resolve the decision path**

```bash
curl -X POST http://localhost:8000/api/v1/ontology/path/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "selected_row": {
      "case": "inf:case-sess_full_202",
      "chest_pain": true,
      "triage_category": "RED"
    },
    "graph_uris": [
      "inferra:case-run:medical_triage:sess_full_202",
      "inferra:rule:medical_triage:v1"
    ],
    "target_label": "patient triage category is RED"
  }'
```

Response:
```json
{
  "selected_fact": {
    "label": "patient triage category is RED",
    "graph_uri": "inferra:case-run:medical_triage:sess_full_202",
    "is_case_run_root": true
  },
  "authoritative_graph": "inferra:case-run:medical_triage:sess_full_202",
  "structural_graph": "inferra:rule:medical_triage:v1",
  "path": {
    "nodes": [
      {
        "id": "node_chest_pain",
        "label": "Patient.has_chest_pain",
        "value": true,
        "source": "ASSERTED"
      },
      {
        "id": "node_immediate_attention",
        "label": "patient requires immediate attention",
        "value": true,
        "source": "INFERRED"
      },
      {
        "id": "node_triage_red",
        "label": "patient triage category is RED",
        "value": true,
        "source": "INFERRED"
      }
    ],
    "edges": [
      {
        "source": "node_chest_pain",
        "target": "node_immediate_attention",
        "relationship_type": "OR_branch",
        "dependency_type": "OR"
      },
      {
        "source": "node_immediate_attention",
        "target": "node_triage_red",
        "relationship_type": "MANDATORY_dependency",
        "dependency_type": "MANDATORY"
      }
    ]
  },
  "semantic_trace": {
    "auto_answered_facts": [],
    "materialized_facts": [],
    "deferred_facts": []
  },
  "path_length": 3,
  "max_depth_searched": 10
}
```

This shows the exact chain of reasoning from asserted fact to final outcome.

---

### Example 10.7: Natural Language Ontology Chat

Query across multiple synced rule projections and case-runs:

```bash
curl -X POST http://localhost:8000/api/v1/ontology/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "natural_language_query": "List all patients over 65 who required immediate attention",
    "graph_uris": [
      "inferra:rule:medical_triage:v1",
      "inferra:case-run:medical_triage:*"
    ],
    "row_limit": 50,
    "timeout_ms": 5000
  }'
```

The LLM-assisted planner translates this to SPARQL:

```sparql
PREFIX inf: <http://inferra.ai/ontology/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?case ?age ?immediate
WHERE {
  ?case a inf:CaseRun .
  ?age_fact inf:factName "Patient.age" .
  ?age_fact inf:factValue ?age .
  FILTER(?age > 65)
  ?imm_fact inf:factName "patient requires immediate attention" .
  ?imm_fact inf:factValue "true"^^xsd:boolean .
}
```

Response includes structured rows plus overlay targets for graph visualization:

```json
{
  "query_translated": "SELECT ?case ?age ?immediate WHERE { ... }",
  "rows": [
    { "case": "inf:case-sess_full_202", "age": 70, "immediate": true },
    { "case": "inf:case-sess_305", "age": 82, "immediate": true }
  ],
  "row_count": 2,
  "graph_overlay": {
    "nodes": [
      { "id": "case_202", "type": "CaseRun", "row_index": 0 },
      { "id": "case_305", "type": "CaseRun", "row_index": 1 }
    ],
    "edges": []
  }
}
```

---

## 11. Quick Start

### Minimal Setup (Core Only)

```bash
# Clone and install
git clone https://github.com/your-org/inferra-platform.git
cd inferra-platform
python -m pip install -e packages/inferra-core
python -m pip install -e ".[async,semantic,reasoning,observability]"

# Set minimal env vars
export DATABASE_URL=postgresql://inferra:inferra@localhost:5432/inferra
export INFERRA_DEBUG=true

# Start Postgres
docker run -d --name inferra-db \
  -e POSTGRES_DB=inferra \
  -e POSTGRES_USER=inferra \
  -e POSTGRES_PASSWORD=inferra \
  -p 5432:5432 postgres:14

# Run migrations
alembic upgrade head

# Start API
INFERRA_ENV_FILE=.env uvicorn src.main:app --reload
```

Visit `http://localhost:8000/docs` for Swagger UI.

### First Rule and Session

**Create rule:**
```bash
curl -X POST http://localhost:8000/api/v1/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hello_world",
    "text": "RULE SET: hello_world\n\nTYPE: Person\nFIELD: Person.name AS TEXT\nFIELD: Person.is_happy AS BOOLEAN\n\n\"person is content\" IF\n  MANDATORY: Person.is_happy IS TRUE\n",
    "category": "demo",
    "description": "Hello World rule"
  }'
```

**Create session:**
```bash
curl -X POST http://localhost:8000/api/v1/inference/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "hello_world",
    "target_node": "person is content"
  }'
```

**Get question:**
```bash
curl "http://localhost:8000/api/v1/inference/next-question?session_id=SESSION_ID"
```

**Feed answer:**
```bash
curl -X POST "http://localhost:8000/api/v1/inference/feed-answer?session_id=SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "node_name": "Person.is_happy",
    "value": true,
    "value_type": "BOOLEAN"
  }'
```

**Get result:**
```bash
curl "http://localhost:8000/api/v1/inference/summary?session_id=SESSION_ID"
```

---

## Appendix A: INFERRA Rule Syntax Quick Reference

```inferra
RULE SET: rule_name

# Type declarations
TYPE: TypeName
TYPE: SubType SUBTYPE OF ParentType

# Field declarations
FIELD: TypeName.fieldName AS TYPE
FIELD: TypeName.fieldName EQUALS value

# Rule blocks (text conclusions)
"conclusion text" IF
  MANDATORY: condition
  AND: condition
  OR: condition
  NOT: condition
  KNOWN: condition
  OPTIONALLY: condition
  POSSIBLY: condition

# Value conclusions
TypeName.fieldName IS value IF
  MANDATORY: condition

# Expression conclusions
TypeName.fieldName IS CALC expression IF
  MANDATORY: condition

# Comparison children
TypeName.fieldName IS GREATER THAN value
TypeName.fieldName IS LESS THAN value
TypeName.fieldName EQUALS value

# Iterate quantifiers
ITERATE: ALL LIST OF list_name
ITERATE: NONE LIST OF list_name
ITERATE: SOME LIST OF list_name
ITERATE: AT LEAST 3 LIST OF list_name
ITERATE: AT MOST 2 LIST OF list_name
ITERATE: EXACTLY 1 LIST OF list_name

# Metadata comments
# Reference: external_source
# Section: document_section
# Original: original_text
```

---

## Appendix B: Fact Sources and Reasoning Modes

| Source | Description |
|--------|-------------|
| `ASSERTED` | Directly asserted by user answer |
| `INFERRED` | Derived by backward-chaining inference |
| `LEARNED` | From induction/historical patterns |
| `HYPOTHETICAL` | Abducted hypothesis (LLM/Z3) |
| `SEMANTIC` | From ontology advisory/auto-answer |

| Reasoning Mode | Description |
|----------------|-------------|
| `deduction` | Standard backward-chaining |
| `abduction` | Hypothesis generation for stuck goals |
| `ontology_materialization` | Facts derived from ontology hierarchy |
| `semantic_advisory` | Ontology suggestions (not asserted) |

---

## Appendix C: Error Handling

### Common Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `400` | Bad Request | Check JSON schema, required fields |
| `403` | Forbidden | Missing scope (when auth enabled) |
| `404` | Not Found | Rule/session/workflow doesn't exist |
| `409` | Conflict | Duplicate answer without idempotency key |
| `422` | Validation Error | Rule validation failed (check `waived_error_ids`) |
| `503` | Service Unavailable | Fuseki/Redis/DB down |

### Idempotency for Feed-Answer

To safely retry answer submission:

```bash
curl -X POST "http://localhost:8000/api/v1/inference/feed-answer?session_id=SESSION_ID" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-key-12345" \
  -d '{
    "node_name": "Person.is_happy",
    "value": true,
    "value_type": "BOOLEAN"
  }'
```

Same key within TTL (300s) returns cached response instead of re-processing.

---

*End of Document*
