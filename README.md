# INFERRA Platform

INFERRA is an explainable, graph-native rule reasoning platform for turning
policies, regulations, procedures, and domain rules into executable decisions.
It combines a deterministic inference engine, a FastAPI service layer, typed
graph dependencies, optional semantic/RDF integration, background reasoning
workers, and prototype frontend tools for rule authoring and AI harness testing.

The current repository is the Python REST backend plus lightweight frontend
prototypes for Rule Studio and AI Harness.

## What INFERRA Is

INFERRA is a hybrid reasoning system. Its core is deterministic: rules are
parsed into nodes, dependencies, fact stores, and graph traversal paths so that
every answer can be traced. Around that deterministic core, INFERRA adds
optional capabilities for semantic synchronization, abduction, induction,
LLM-assisted goal mapping, and observability.

| Layer | What It Does | Current Implementation |
| --- | --- | --- |
| Rule engine | Parses INFERRA rule text and evaluates facts against goals | Python domain engine |
| Graph runtime | Represents rule dependencies and topological execution order | `HyperAdjacencyGraph`, with matrix compatibility paths |
| API layer | Exposes rule, inference, validation, file, metrics, and reasoning endpoints | FastAPI |
| Session state | Stores answers, fact layers, overrides, trace state, and history | In-memory or Redis-backed session store |
| Semantic layer | Publishes or caches rule knowledge as RDF/SPARQL data | rdflib and Apache Jena Fuseki integration |
| Async layer | Runs slow sync and induction work outside the request path | Celery with Redis |
| Observability | Reports health, Prometheus metrics, and OpenTelemetry traces | Prometheus client and OTel collector |
| Frontend prototypes | Provides visual rule graph and AI harness demos | Static HTML/CSS/JavaScript |

## What INFERRA Is For

INFERRA is designed for situations where an answer must be calculated from
explicit rules, and where the path to that answer matters as much as the answer.

Good INFERRA workloads usually have these properties:

| Workload Trait | Why INFERRA Fits |
| --- | --- |
| Rules are explicit | The engine can parse, validate, execute, and trace them |
| Decisions need auditability | Fact sources, graph dependencies, and PROV-O style traces can explain outcomes |
| Missing evidence matters | Abduction can propose what fact is needed next |
| Regulations change over time | Rule versions, import trees, and semantic sync support controlled evolution |
| Human review is part of the process | The API can ask the next best question rather than forcing a black-box result |
| AI needs guardrails | The deterministic rule engine can constrain LLM-assisted workflows |

INFERRA is not a replacement for human legal, medical, financial, or compliance
judgment. It is an engineering substrate for encoding, testing, tracing, and
operating decision logic.

## Where INFERRA Can Be Used

INFERRA can support products and internal systems across policy-heavy,
risk-sensitive, and audit-sensitive domains.

| Area | Example Use |
| --- | --- |
| Government eligibility | Benefits, grants, licensing, immigration, veterans affairs, permits |
| Insurance | Claims triage, coverage checks, policy exclusion reasoning |
| Banking and lending | KYC, credit policy pre-checks, hardship workflows, document evidence checks |
| Healthcare administration | Eligibility, prior authorization, care-pathway rule support |
| Legal operations | Contract clause compliance, regulatory rule extraction, controlled decision support |
| Enterprise compliance | Controls testing, internal policy enforcement, audit evidence workflows |
| Software compliance | Codebase policy checks, dependency governance, secure SDLC rule evaluation |
| AI governance | Prompt-risk gates, tool-use policies, model output review, traceable AI harnesses |
| GraphRAG systems | Retrieval grounded by RDF, provenance, and executable rule constraints |
| Workflow automation | Human-in-the-loop forms that ask only necessary questions |

## Key Capabilities

| Capability | Description |
| --- | --- |
| Rule validation | Validate rule text before persistence or execution |
| Interactive inference | Create a session, ask the next question, feed answers, and get a summary |
| Graph-native dependency model | Use typed dependency groups instead of relying on dense matrix scans |
| ML-optimized traversal hooks | Optional history-aware topological sort strategies |
| Layered working memory | Separate asserted, inferred, imported, and overridden facts |
| Rule imports | Resolve modular rule sets and import trees |
| RDF and semantic sync | Compile rule knowledge into semantic graph form |
| Abduction | Propose missing facts that could make a target true |
| Induction | Run background jobs that suggest candidate rules from sessions |
| LLM-assisted reasoning | Optional goal mapping, question wording, and trace explanation |
| Metrics and tracing | Health endpoints, Prometheus metrics, and OpenTelemetry support |
| Frontend prototypes | Rule Studio and AI Harness demos for UI experimentation |

## Architecture

INFERRA follows a port/adapters architecture. Domain logic sits in the center.
Inbound adapters call into the domain through application services. Outbound
adapters connect the domain to databases, Redis, Fuseki, LLM clients, and worker
queues.

```mermaid
flowchart LR
    User[User or Frontend] --> API[FastAPI Inbound Routes]
    API --> Services[Application Services]
    Services --> Domain[Domain Core]
    Domain --> Ports[ABCMeta Ports]
    Ports --> Persistence[Persistence Adapters]
    Ports --> SessionStore[Session Store]
    Ports --> Reasoning[Reasoning Adapters]
    Ports --> Semantic[Semantic Adapters]

    Persistence --> Postgres[(PostgreSQL)]
    SessionStore --> Redis[(Redis)]
    Reasoning --> Celery[Celery Worker]
    Celery --> Redis
    Semantic --> Fuseki[(Apache Jena Fuseki)]
    API --> Metrics[Prometheus Metrics]
    API --> OTel[OpenTelemetry]
```

### Architectural Principles

| Principle | INFERRA Decision |
| --- | --- |
| Port contracts | Use `ABCMeta` ports, not `Protocol`, for explicit implementation contracts |
| Graph runtime | Treat `HyperAdjacencyGraph` as the canonical graph direction |
| Matrix compatibility | Keep `DependencyMatrix` only where legacy compatibility still requires it |
| Node identity | Prefer stable node names/IDs for graph, RDF, trace, and history lookups |
| Dependency semantics | Preserve bitmask-style dependency composition for AND, OR, NOT, KNOWN, MANDATORY combinations |
| Session safety | Feature flags are start-of-session sticky |
| Slow work | Keep induction and semantic sync outside the request path |
| Observability | Treat traces and metrics as first-class product features |

## Main Components

| Path | Component | Purpose |
| --- | --- | --- |
| `src/domain/` | Domain core | Inference, graph, nodes, parser, state, reasoning models |
| `src/ports/` | Port contracts | Abstract interfaces for session stores, graph, LLM, reasoning, repositories |
| `src/adapters/inbound/http/` | HTTP adapter | FastAPI routers, schemas, and dependency wiring |
| `src/adapters/outbound/` | Outbound adapters | Persistence, session stores, ontology, LLM, and reasoning adapters |
| `src/services/` | Application services | Rule service, validation, sandboxing, file conversion |
| `src/tasks/` | Worker tasks | Celery app, induction tasks, rule sync tasks |
| `src/infrastructure/` | Cross-cutting infrastructure | Auth, rate limit, correlation IDs, logging, observability |
| `tests/` | Test suite | Unit, integration, contract, regression, load, and chaos tests |
| `frontends/inferra-rule-studio/` | Rule Studio prototype | Rule text, graph visualization, validation payloads |
| `frontends/inferra-ai-harness/` | AI Harness prototype | Prompt risk, gate simulation, PROV-O trace preview |
| `docs/` | Active implementation docs and references | `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`, `OPERATIONS.md`, production registers, rule syntax, and archived historical plans |

## Technology Stack

| Area | Current Stack | Recommended Direction |
| --- | --- | --- |
| Backend API | FastAPI, Pydantic, Uvicorn | Keep |
| Domain language | Python 3.10+ | Keep Python core deterministic and highly tested |
| Persistence | SQLAlchemy, PostgreSQL | Keep PostgreSQL as durable source |
| Hot state and jobs | Redis, Celery | Keep for current async workflows |
| Semantic graph | rdflib, Apache Jena Fuseki | Keep for RDF, SPARQL, PROV-O, audit graph |
| Solver support | z3-solver | Keep for formal reasoning extensions |
| Observability | Prometheus, Grafana, Loki, Promtail, OpenTelemetry | Add alert rules |
| Frontend prototypes | Static JS and canvas | Move production UI to Vite, TypeScript, React, React Flow |
| Load testing | k6 | Run in staging or CI |
| Containerization | Docker Compose | Keep for local/staging; consider Kubernetes or managed services later |

## Prerequisites

| Requirement | Version or Notes |
| --- | --- |
| Python | 3.10 or newer |
| pip | Recent version with editable install support |
| Docker Desktop or Docker Engine | Needed for Redis, Fuseki, PostgreSQL, OTel, API and worker containers |
| Node.js | 20 recommended for frontend prototype checks |
| PowerShell | Recommended on Windows for readiness scripts |
| k6 | Optional; needed only for local load smoke without Dockerized runner |
| Git | Needed to clone and manage the repository |

## Installation

### Option 1: Local Python Development

Use this when you are editing backend code and running tests locally.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,async,semantic,reasoning,observability]"
```

Run the API locally:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 2: Docker Compose

Use this when you want the full local stack: API, worker, Redis, Fuseki,
PostgreSQL, and OpenTelemetry collector.

```powershell
docker compose up -d --build
```

Check service health:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health | ConvertTo-Json -Depth 8
```

### Installation Mode Comparison

| Mode | Best For | Strengths | Tradeoffs |
| --- | --- | --- | --- |
| Local Python | Fast backend development | Quick edit/test cycle, easier debugging | External services need separate setup or feature fallbacks |
| Docker Compose | Full-system local testing | Runs API, worker, Redis, Fuseki, Postgres, OTel together | Heavier startup and Docker permissions required |
| Static frontend servers | UI prototype testing | No build tool needed | Prototype only; not production frontend architecture |

## Monitoring Dashboard

The Docker Compose stack provisions a local Grafana observability workspace.

| Tool | Local URL | Purpose |
| --- | --- | --- |
| Grafana | `http://localhost:3000` | Operational dashboard, logs, and rule/history table |
| Prometheus | `http://localhost:9090` | Scrapes INFERRA `/metrics` and monitoring components |
| Loki | `http://localhost:3100` | Stores compose service logs for audit/log exploration |

Default local Grafana login:

| Username | Password |
| --- | --- |
| `admin` | `admin` |

Provisioned dashboard:

| Dashboard | What It Shows |
| --- | --- |
| `INFERRA Operational Overview` | API scrape health, propagation latency, semantic cache hit rate, Fuseki sync latency, import cost, induction task health, reasoning routes, LLM fallback/error rates, rule history coverage, and audit/log exploration |

The sample `palos_*` metric names are not used because the current backend
exports `inferra_*` metrics. The rule coverage panel is backed by the current
PostgreSQL `rule` and `history` tables. A richer `execution_count` and
`avg_duration` table can be added later when per-rule execution metrics are
persisted.

## Configuration

INFERRA uses environment variables for runtime behavior. Important settings
include:

| Variable | Purpose | Typical Local Value |
| --- | --- | --- |
| `SQLALCHEMY_DATABASE_URI` | PostgreSQL connection string | `postgresql://inferra:inferra@localhost:5432/inferra` |
| `REDIS_URL` | Redis connection for session store | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend | `redis://localhost:6379/1` |
| `FUSEKI_URL` | Fuseki dataset URL | `http://localhost:3030/inferra` |
| `FUSEKI_USER` | Fuseki username | `admin` |
| `FUSEKI_PASSWORD` | Fuseki password | `admin` |
| `INFERRA_AUTH_ENABLED` | Enable API key auth | `false` for local, `true` for protected environments |
| `INFERRA_API_KEY` | API key when auth is enabled | Set to a secret value |
| `INFERRA_API_KEY_OWNER_ID` | Owner identity assigned to API-key requests | `api-key` or service account ID |
| `INFERRA_JWT_SECRET` | HS256 JWT verification secret when bearer JWT auth is used | Set to a secret value |
| `INFERRA_CSRF_PROTECTION` | Require CSRF token on mutating authenticated requests | `false` locally; `true` for browser clients |
| `INFERRA_CSRF_TOKEN` | Static CSRF token alternative to double-submit cookie | Set to a secret value when enabled |
| `INFERRA_OBSERVABILITY_ENABLED` | Enable observability integrations | `true` in compose |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel collector endpoint | `http://localhost:4317` |

Feature flags use the `INFERRA_` prefix. Examples:

| Flag | Purpose |
| --- | --- |
| `INFERRA_USE_HYPERGRAPH` | Use graph-native dependency runtime; defaults to `true` |
| `INFERRA_LEGACY_ITERATE` | Keep legacy iterate behavior enabled |
| `INFERRA_LAYERED_MEMORY` | Use layered fact store |
| `INFERRA_ML_OPTIMIZED_DFS` | Enable history-aware DFS ordering |
| `INFERRA_ASYNC_SYNC_ENABLED` | Enable async rule sync pipeline |
| `INFERRA_MODULAR_IMPORTS` | Enable modular import resolution |
| `INFERRA_REDIS_SESSION_STORE` | Use Redis-backed sessions |
| `INFERRA_LLM_ENHANCEMENTS` | Enable LLM-assisted goal/explanation paths |
| `INFERRA_ABDUCTION_ENABLED` | Enable abduction adapters |
| `INFERRA_INDUCTION_PIPELINE` | Enable induction pipeline |
| `INFERRA_REASONING_ROUTER` | Enable hybrid reasoning router |

## How To Use INFERRA

### 1. Start the Backend

With Docker Compose:

```powershell
docker compose up -d --build
```

Or locally:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Open the API docs:

```text
http://localhost:8000/docs
```

### 2. Check Health

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/live
Invoke-RestMethod http://localhost:8000/api/v1/health | ConvertTo-Json -Depth 8
```

### 3. Validate Rule Text

```powershell
$payload = @{
  rule_name = "loan_rule"
  rule_text = @"
INPUT applicant.age AS NUMBER
INPUT service.days AS NUMBER
rule.isVeteran IS TRUE IF service.days >= 30
eligibility.homeLoanAssistance IS TRUE IF applicant.age >= 18 AND rule.isVeteran
"@
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://localhost:8000/api/v1/rules/validate `
  -Method Post `
  -ContentType "application/json" `
  -Body $payload
```

### 4. Use Reasoning Endpoints

Goal mapping with LLM disabled returns a deterministic fallback:

```powershell
$payload = @{
  user_query = "Can I claim this benefit?"
  rule_name = "benefit_rule"
  enabled = $false
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://localhost:8000/api/v1/reasoning/goal `
  -Method Post `
  -ContentType "application/json" `
  -Body $payload
```

Abduction can propose missing facts:

```powershell
$payload = @{
  target = "goal"
  working_memory = @{ known = $true }
  graph_snapshot = @{
    child_groups = @{
      goal = @(
        @(1, @("known", "missing"))
      )
    }
  }
  enabled = $true
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Uri http://localhost:8000/api/v1/reasoning/abduct `
  -Method Post `
  -ContentType "application/json" `
  -Body $payload
```

### 5. Run the Frontend Prototypes

Rule Studio:

```powershell
cd frontends/inferra-rule-studio
npm.cmd test
npm.cmd run check
python -m http.server 4173 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:4173
```

AI Harness:

```powershell
cd frontends/inferra-ai-harness
npm.cmd test
npm.cmd run check
python -m http.server 4174 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:4174
```

## API Surface

| Endpoint Group | Base Path | Purpose |
| --- | --- | --- |
| System | `/`, `/api/v1/live`, `/api/v1/health` | Root, liveness, readiness |
| Rules | `/api/v1/rules/*` and legacy rule endpoints | Rule CRUD, lookup, validation, import tree |
| Inference | `/api/v1/inference/*` | Sessions, next question, answers, summary, trace |
| Files | `/api/v1/files/*` | Document-to-markdown and document-to-rule conversion |
| Reasoning | `/api/v1/reasoning/*` | Abduction, induction, LLM goal mapping, trace explanation |
| Metrics | `/metrics`, `/api/v1/metrics` | Prometheus metrics |

## Frontend Tools

| Tool | Current Purpose | Production Recommendation |
| --- | --- | --- |
| Rule Studio | Edit sample INFERRA text, visualize a dependency graph, validate rule payloads | Rebuild with Vite, TypeScript, React, React Flow, TanStack Query, Zod, Playwright |
| AI Harness | Simulate prompt risk, gate actions, provenance traces, and reasoning API calls | Rebuild as an evaluation console with scenario datasets, model comparisons, and trace review |

## Testing and Verification

Run the backend suite with the current quality gate:

```powershell
pytest --cov=src --cov-fail-under=97
```

Run frontend checks:

```powershell
cd frontends/inferra-rule-studio
npm.cmd test
npm.cmd run check

cd ..\inferra-ai-harness
npm.cmd test
npm.cmd run check
```

Run full phase readiness verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_phase_readiness.ps1
```

Run load smoke:

```powershell
k6 run tests/load/k6_api_smoke.js
```

Or use the Dockerized k6 runner:

```powershell
powershell -ExecutionPolicy Bypass -File tests/load/run_k6_docker.ps1
```

Run a controlled Docker chaos smoke:

```powershell
powershell -ExecutionPolicy Bypass -File tests/chaos/docker_chaos_smoke.ps1 -Service redis -Action pause
powershell -ExecutionPolicy Bypass -File tests/chaos/docker_chaos_smoke.ps1 -Service redis -Action unpause
```

Run the broader Phase 4 restart chaos suite:

```powershell
powershell -ExecutionPolicy Bypass -File tests/chaos/run_phase4_chaos_suite.ps1
```

## Current Project Status

| Area | Status |
| --- | --- |
| Backend API | Implemented and test-covered |
| Backend coverage gate | 97 percent line coverage, latest local gate 97.01 percent |
| Docker Compose stack | API, worker, Redis, Fuseki, PostgreSQL, OTel collector |
| Monitoring stack | Grafana, Prometheus, Loki, Promtail |
| Rule Studio frontend | Prototype implemented and checked |
| AI Harness frontend | Prototype implemented and checked |
| Load smoke | k6 scripts available; local 500-VU compose production gate passes |
| Chaos smoke | Compose-scoped reversible drill and Phase 4 restart suite available; local restart suite passes for Redis, Fuseki, and worker |
| Production frontend | Recommended but not yet implemented |
| Production auth model | API key, HS256 JWT, session ownership, rate limiting, and opt-in CSRF implemented; OIDC/RBAC remains a future enterprise auth decision |
| GraphRAG product layer | Future roadmap item |

## Product and Business Positioning

INFERRA is strongest when positioned as decision intelligence infrastructure,
not as a generic chatbot or ordinary rules database.

| Product Direction | Why It Is Promising |
| --- | --- |
| Compliance-as-code platform | Organizations need auditable, executable policy checks |
| Regulation-to-decision engine | Public rules can become interactive eligibility flows |
| AI governance harness | Deterministic rules can gate prompts, tools, and model outputs |
| Explainable workflow engine | Human-in-the-loop workflows can ask only relevant questions |
| Semantic policy graph | RDF and provenance make rule knowledge reusable across systems |
| Codebase compliance auditor | Software rules can be expressed, tested, and traced like policy rules |

The commercial advantage is explainability. Many systems can produce an answer;
INFERRA is designed to show why the answer was produced, what evidence was used,
what evidence is missing, and which rule path was followed.

## Security and Production Notes

| Concern | Recommendation |
| --- | --- |
| Authentication | Enable `INFERRA_AUTH_ENABLED=true` and set `INFERRA_API_KEY` or `INFERRA_JWT_SECRET` before exposing non-health endpoints |
| Secrets | Use `.env.example` only as a template; place real secrets in a platform secret manager before production traffic |
| Redis | Treat Redis as operational state, not the durable source of truth |
| PostgreSQL | Use managed backups, migrations, and least-privilege credentials |
| Fuseki | Protect admin access and define dataset backup/restore procedures |
| LLM usage | Keep LLM features disabled until provider, model, budget, and evaluation policy are approved |
| File uploads | Keep size limits, file type validation, and sandboxing strict |
| Observability | Keep dashboards and Prometheus alert rules live; tune thresholds and notification routing before production traffic |
| Rule changes | Require validation, versioning, review, and rollback paths |

## Future Roadmap

The active roadmap is maintained in `docs/ROADMAP.md`; the table below is a short product-level summary.

| Phase | Roadmap Item | Outcome |
| --- | --- | --- |
| Completed | Graph-first runtime default | `HyperAdjacencyGraph` is the default runtime path, with matrix adapters retained for compatibility |
| Near term | Harden production readiness scripts | Repeatable local and CI confidence |
| Near term | Add Playwright frontend tests | Real browser confidence for prototypes |
| Completed | Add Grafana dashboards | Operational visibility for API, worker, Redis, Fuseki, logs, and reasoning metrics |
| Mid term | Rewrite production frontend | Typed Rule Studio and AI Harness with graph editing and e2e tests |
| Mid term | Strengthen semantic sync | Robust RDF publishing, import impact analysis, and namespace governance |
| Mid term | Build rule versioning workflows | Approval, promotion, rollback, audit history |
| Mid term | Add GraphRAG evaluation harness | Measure retrieval quality before using retrieved context in decisions |
| Long term | Enterprise workflow orchestration | Durable workflows for rule promotion, policy review, and incident recovery |
| Long term | Multi-tenant governance | Tenant isolation, RBAC, audit exports, deployment controls |
| Long term | Decision marketplace | Reusable rule modules for regulated domains |

## Expert Recommendations For The README And Project

This README intentionally includes more than installation instructions. For a
system like INFERRA, users need to understand its trust model, not only its API.

| Recommendation | Why It Matters |
| --- | --- |
| Keep product positioning clear | INFERRA should be seen as explainable decision infrastructure |
| Show concrete use cases | Policy and compliance buyers need recognizable workflows |
| Document the architecture | Engineers need to know where to add features safely |
| Document quality gates | High coverage and readiness scripts are part of the value proposition |
| Document security posture | Rule engines often sit near sensitive policy and applicant data |
| Document roadmap boundaries | Users should know what is production-ready, prototype, and future-facing |
| Keep frontend status honest | The prototypes are useful, but the production frontend should be typed and e2e tested |

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `npm.ps1 cannot be loaded` | PowerShell execution policy blocks unsigned scripts | Use `npm.cmd` instead of `npm` |
| `docker compose ps` permission denied | Docker Desktop or Docker config permission issue | Start Docker Desktop or fix user access to Docker |
| `/api/v1/health` reports Redis down | Redis container is not healthy or URL is wrong | Check `docker compose ps` and `REDIS_URL` |
| `/api/v1/health` reports Fuseki down | Fuseki container or dataset is unavailable | Check `FUSEKI_URL`, credentials, and container logs |
| LLM goal mapping falls back | LLM enhancements are disabled or provider config is missing | Set LLM feature flags and provider credentials after evaluation |
| Frontend page loads but API calls fail | Backend is down or served on another host/port | Check `http://localhost:8000/api/v1/health` |

## Useful Local URLs

| Service | URL |
| --- | --- |
| Backend API docs | `http://localhost:8000/docs` |
| Backend health | `http://localhost:8000/api/v1/health` |
| Backend metrics | `http://localhost:8000/metrics` |
| Grafana dashboard | `http://localhost:3000` |
| Prometheus | `http://localhost:9090` |
| Loki | `http://localhost:3100` |
| Rule Studio prototype | `http://127.0.0.1:4173` |
| AI Harness prototype | `http://127.0.0.1:4174` |
| Fuseki web UI | `http://localhost:3030` |

## License

No license file is currently included in this repository. Add a license before
publishing or distributing INFERRA outside the private development context.
