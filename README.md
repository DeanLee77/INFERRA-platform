# INFERRA Platform

INFERRA is an explainable, graph-native rule reasoning platform for turning
policies, regulations, procedures, and domain rules into executable decisions.
It combines a deterministic inference engine, a FastAPI service runtime, typed
graph dependencies, a critical versioned semantic/RDF audit projection,
optional decision-affecting ontology reasoning, background workers, and
separately released AXIOM and AEGIS user experiences.

The current repository contains the Python REST runtime plus legacy lightweight
frontend prototypes. The accepted target extracts the deterministic kernel into
an internal `inferra-core` Python distribution while retaining this Platform as
the official authoritative multi-user service. P0.1 and P0.2a-P0.2b are
complete: an internal `inferra-core==0.1.1` distribution owns its leaf contracts
and a private executable graph/node/token/parser/validation layer, and its
parser passes clean installed-wheel proof. State/import/inference/provenance
extraction and Platform application-service rewiring remain pending, and no
public package is published. See
[`docs/INFERRA_Core_Package_and_Runtime_Architecture.md`](docs/INFERRA_Core_Package_and_Runtime_Architecture.md)
and
[`docs/INFERRA_Cross_Project_Technical_Direction.md`](docs/INFERRA_Cross_Project_Technical_Direction.md).
Account/case hierarchy, immutable RDF topology, provenance authority, retention,
and AXIOM/AEGIS semantic behavior are controlled by
[`docs/INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md`](docs/INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md).
The completed freeze is recorded in
[`docs/INFERRA_Core_Extraction_P0_1_Baseline.md`](docs/INFERRA_Core_Extraction_P0_1_Baseline.md).
Current extraction evidence is in
[`docs/INFERRA_Core_Extraction_P0_2_Distribution.md`](docs/INFERRA_Core_Extraction_P0_2_Distribution.md).

## What INFERRA Is

INFERRA is a hybrid reasoning system. Its core is deterministic: rules are
parsed into nodes, dependencies, fact stores, and graph traversal paths so that
every answer can be traced. Around that deterministic core, INFERRA adds
optional capabilities for semantic synchronization, abduction, induction,
LLM-assisted goal mapping, and observability.

| Layer | What It Does | Current Implementation |
| --- | --- | --- |
| Rule engine | Parses INFERRA rule text and evaluates facts against goals | Private Core parser/graph/validation extracted; Platform compatibility parser and inference remain pending facade rewiring/extraction |
| Graph runtime | Represents rule dependencies and topological execution order | `HyperAdjacencyGraph`, with matrix compatibility paths |
| API layer | Exposes rule, inference, validation, file, metrics, and reasoning endpoints | FastAPI |
| Session state | Stores answers, fact layers, overrides, trace state, and history | In-memory or Redis-backed session store |
| Semantic layer | Publishes or caches rule knowledge as RDF/SPARQL data | rdflib and Apache Jena Fuseki integration |
| Async layer | Runs slow sync and induction work outside the request path | Celery with Redis |
| Observability | Reports health, Prometheus metrics, and OpenTelemetry traces | Prometheus client and OTel collector |
| First-party products | Provides general authoring/audit and specialist autonomous-governance experiences | Separate Svelte repositories: `inferra-axiom` and `inferra-aegis`; independently gated |

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
| First-party clients | Separate AXIOM and AEGIS Svelte products, independently gated |
| Legacy frontend prototypes | Embedded Rule Studio and AI Harness demos for local experimentation only |

## Architecture

INFERRA follows a port/adapters architecture. Domain logic sits in the center.
Inbound adapters call into the domain through application services. Outbound
adapters connect the domain to databases, Redis, Fuseki, LLM clients, and worker
queues.

```mermaid
flowchart LR
    User[User or Frontend] --> API[FastAPI Inbound Routes]
    API --> Services[Application Services]
    Services --> Domain[inferra-core Python package]
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

The diagram is the accepted target boundary. Core 0.1.1 now owns values,
diagnostics, evaluation history, five deterministic ports, and a private
executable graph/node/token/parser/validation layer. Platform still ships
compatibility parsing/iterate/matrix paths and the remaining state, import,
inference and provenance layers. Continued extraction must preserve behavior
through the unchanged golden vectors and installed-wheel tests.

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
| Package/runtime split | Core computes deterministically; Platform owns identity, persistence, transactions, audit/outbox, ontology publication, and operations |
| Consumer integration | TypeScript products use generated service clients; Python embedders may use the library under host-owned operational guarantees |

### Package and deployment modes

| Mode | Intended use | Responsibility boundary |
| --- | --- | --- |
| Platform service | Official multi-user production | Platform owns authoritative rules, identity, concurrency, durable audit and recovery |
| Bundled/sidecar Platform service | Single-tenant or edge network deployment | Same service contracts and evidence, deployed close to the consumer |
| Embedded `inferra-core` | Internal 0.1.1 still exposes only the small supported leaf facade; private parser/graph code is not yet a stable embedding contract | Host owns persistence, security, migrations, audit, concurrency and recovery; not automatically Platform-certified |

AXIOM and AEGIS are TypeScript products and therefore use generated API clients,
not the Python package. A generated Python service SDK is also different from
the package: the SDK calls Platform remotely; `inferra-core` computes locally.

## Main Components

| Path | Component | Purpose |
| --- | --- | --- |
| `packages/inferra-core/` | Internal pre-release package, present as 0.1.1 | Independently built leaf plus private parser/graph/validation kernel and bounded IS CALC interpreter; no third-party runtime dependencies; deeper deterministic layers remain |
| `src/domain/` | Domain core | Inference, graph, nodes, parser, state, reasoning models |
| `src/ports/` | Port contracts | Abstract interfaces for session stores, graph, LLM, reasoning, repositories |
| `src/adapters/inbound/http/` | HTTP adapter | FastAPI routers, schemas, and dependency wiring |
| `src/adapters/outbound/` | Outbound adapters | Persistence, session stores, ontology, LLM, and reasoning adapters |
| `src/services/` | Application services | Rule service, validation, sandboxing, file conversion |
| `src/tasks/` | Worker tasks | Celery app, induction tasks, rule sync tasks |
| `src/infrastructure/` | Cross-cutting infrastructure | Auth, rate limit, correlation IDs, logging, observability |
| `tests/` | Test suite | Unit, integration, contract, regression, load, and chaos tests |
| `frontends/` | Legacy Platform prototypes | Development/demo tools only; not the accepted production frontend direction |
| sibling `inferra-axiom` repository | AXIOM | General rule authoring, execution, and audit UI with a thin BFF |
| sibling `inferra-aegis` repository | AEGIS | Specialist workflow/autonomy governance UI and eventual application backend/BFF |
| `docs/` | Active implementation docs and references | `IMPLEMENTATION_STATUS.md`, `ROADMAP.md`, `OPERATIONS.md`, production registers, rule syntax, and archived historical plans |

## Technology Stack

| Area | Current Stack | Recommended Direction |
| --- | --- | --- |
| Deterministic kernel | Internal `inferra-core` first slice plus remaining Python modules inside Platform | Complete the dependency-layer extraction before Core 1.0; publish publicly only after stability/licensing gates |
| Backend API | FastAPI, Pydantic, Uvicorn | Keep |
| Domain language | Python 3.10+ | Keep Python core deterministic and highly tested |
| Persistence | SQLAlchemy, PostgreSQL | Keep PostgreSQL as durable source |
| Hot state and jobs | Redis, Celery | Keep for current async workflows |
| Semantic graph | rdflib, Apache Jena Fuseki | Keep for RDF, SPARQL, PROV-O, audit graph |
| Solver support | z3-solver | Keep for formal reasoning extensions |
| Observability | Prometheus, Grafana, Loki, Promtail, OpenTelemetry | Add alert rules |
| First-party frontends | Svelte 5/SvelteKit AXIOM and AEGIS repositories | Keep Svelte; harden their BFFs, generate clients, and pass independent quality/security gates |
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
pip install -e "packages/inferra-core"
pip install -e ".[dev,async,semantic,reasoning,observability]"
```

Run the API locally:

```powershell
$env:INFERRA_ENV_FILE = ".env"
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

`src.main` loads that file at the API process boundary before constructing the
effective feature-flag snapshot. Exported environment variables take
precedence. The Celery entry point applies the same policy; tests disable root
`.env` loading and use isolated temporary files.

### Option 2: Docker Compose

Use this when you want the full local stack: API, worker, Redis, Fuseki,
PostgreSQL, and OpenTelemetry collector.

```powershell
docker compose up -d --build
```

The graph explorer is optional and excluded from the default rebuild because it
uses the adjacent `../graph-explorer` checkout. Start it only when needed:

```powershell
docker compose --profile explorer up -d --build explorer
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

These credentials, along with the local Redis, PostgreSQL, and Fuseki defaults,
are for the loopback-bound developer stack only. Run `secrets/init-secrets.*`
and `docker-compose.prod.yml` before any shared-network or production rehearsal.

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

The API and worker entry points call
`src.infrastructure.environment.load_process_environment()` before importing
application modules. It reads `.env` by default, or the file selected by
`INFERRA_ENV_FILE`, without overriding exported variables. Set
`INFERRA_LOAD_DOTENV=false` for a launcher that already supplies the complete
environment. Domain modules never read dotenv files directly.

Invalid numeric feature settings fail process startup: confidence thresholds
must be within `0.0..1.0`, hierarchy depths cannot be negative, and maximum
closure depth cannot be below minimum hierarchy depth.

The graph-first runtime also fails fast unless `INFERRA_USE_HYPERGRAPH`,
`INFERRA_LAYERED_MEMORY`, and `INFERRA_STRICT_PORT_CONTRACTS` are `true`.
Those names remain in the compatibility snapshot while their obsolete off
ramps are retired. The two post-reasoning gates must have the same value.

| Variable | Purpose | Typical Local Value |
| --- | --- | --- |
| `SQLALCHEMY_DATABASE_URI` | PostgreSQL connection string | `postgresql://inferra:inferra@localhost:5432/inferra` |
| `AEGIS_SQLALCHEMY_DATABASE_URI` | AEGIS rule-store PostgreSQL connection string; must target a distinct database unless `AEGIS_ALLOW_SHARED_DATABASE=true` is set for explicit test/demo use | `postgresql://inferra:inferra@localhost:5432/inferra_aegis` |
| `REDIS_URL` | Redis connection for session store | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend | `redis://localhost:6379/1` |
| `FUSEKI_URL` | Fuseki dataset URL | `http://localhost:3030/inferra` |
| `FUSEKI_USER` | Fuseki write/admin username for worker sync and update paths | `admin` |
| `FUSEKI_PASSWORD` | Fuseki write/admin password; keep out of the API service in production rehearsal | `admin` |
| `FUSEKI_READ_USER` | Fuseki read-only username for ontology chat and graph query endpoints | `inferra_reader` |
| `FUSEKI_READ_PASSWORD` | Fuseki read-only password; must be distinct from `FUSEKI_PASSWORD` outside throwaway local dev | `inferra_read` |
| `INFERRA_AUTH_ENABLED` | Enable API key/JWT auth; required when `INFERRA_ENV=production` | `true` for Docker Compose and protected environments |
| `INFERRA_API_KEY` | API key when auth is enabled | Set to a secret value |
| `INFERRA_API_KEY_OWNER_ID` | Owner identity assigned to API-key requests | `api-key` or service account ID |
| `INFERRA_API_KEY_SCOPES` | Comma-separated API-key scopes; keep browser-facing proxy keys read-only for LLM configuration and reserve `llm:write` for a direct authenticated operator/admin path | `read,llm:read` |
| `INFERRA_JWT_SECRET` | HS256 JWT verification secret when bearer JWT auth is used | Set to a secret value |
| `INFERRA_CSRF_PROTECTION` | Require CSRF token on mutating authenticated requests | `false` locally; `true` for browser clients |
| `INFERRA_CSRF_TOKEN` | Static CSRF token alternative to double-submit cookie | Set to a secret value when enabled |
| `INFERRA_CORS_ALLOWED_ORIGINS` | Comma-separated browser origins allowed by CORS; wildcard is rejected in production | Explicit frontend origins |
| `INFERRA_CORS_ALLOW_CREDENTIALS` | Allow credentialed CORS only for explicit origins | `false` |
| `INFERRA_LLM_ENDPOINT_ALLOWLIST` | Optional comma-separated host/origin allowlist for sanctioned private/internal LLM gateways; unsafe loopback, link-local, metadata, and RFC1918/private targets are otherwise rejected | Empty for public HTTPS provider endpoints |
| `INFERRA_OBSERVABILITY_ENABLED` | Enable observability integrations | `true` in compose |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel collector endpoint | `http://localhost:4317` |

Feature flags use the `INFERRA_` prefix. The table below is a concise subset;
the [complete canonical inventory and code defaults](IMPLEMENTATION_GUIDE.md#2-phases--feature-flags)
are defined by `src/domain/state/feature_flags.py`. Compose and environment
values are deployment overrides, not changes to those code defaults.

The base Compose stack is a feature-rich, loopback-only local profile. A single
28-entry mapping is injected into both API and worker so cross-process
workflows use the same effective snapshot. In that profile both
`INFERRA_ASYNC_POST_REASONING` and
`INFERRA_GENERATE_POST_REASONING_TTL` are enabled; override them together.
Compose uses the root `.env` for host-side interpolation and exports the
resolved values into each container; container-side dotenv loading is disabled.

| Flag | Purpose |
| --- | --- |
| `INFERRA_USE_HYPERGRAPH` | Use graph-native dependency runtime; defaults to `true` |
| `INFERRA_LEGACY_ITERATE` | Keep legacy iterate behavior enabled |
| `INFERRA_LAYERED_MEMORY` | Use layered fact store |
| `INFERRA_ML_OPTIMIZED_DFS` | Enable history-aware DFS ordering; stored history is passed to the parser only when this flag is enabled |
| `INFERRA_ASYNC_SYNC_ENABLED` | Enable async rule sync pipeline |
| `INFERRA_MODULAR_IMPORTS` | Enable modular import resolution |
| `INFERRA_HYBRID_ORCHESTRATOR` | Run stalled sessions through the convergence orchestrator selected from the frozen session snapshot |
| `INFERRA_PROV_O_TRACE` | Permit explicit PROV-O trace generation for the session |
| `INFERRA_ENRICHED_API` | Include provenance sources, semantic suggestions, and reasoning metadata in inference responses |
| `INFERRA_REDIS_SESSION_STORE` | Use Redis-backed sessions |
| `INFERRA_LLM_ENHANCEMENTS` | Enable LLM-assisted goal/explanation paths |
| `INFERRA_STRICT_PORT_CONTRACTS` | Required compatibility invariant while port checks remain unconditional in CI |
| `INFERRA_ABDUCTION_ENABLED` | Enable abduction adapters |
| `INFERRA_INDUCTION_PIPELINE` | Enable induction pipeline |
| `INFERRA_REASONING_ROUTER` | Enable hybrid reasoning router |
| `INFERRA_CONFIDENCE_THRESHOLDS` | Apply configured confidence pruning in the reasoning router |

Reasoning API `enabled` fields are opt-out controls only: a request can disable
an enabled capability, but cannot turn on a process-level flag that is off.
Hybrid orchestration, routing, abduction, induction, and confidence decisions
use the frozen flag snapshot belonging to the inference session.

## How To Use INFERRA

### 1. Start the Backend

With Docker Compose:

```powershell
docker compose up -d --build
```

Or locally:

```powershell
$env:INFERRA_ENV_FILE = ".env"
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

### 5. Run the Legacy Frontend Prototypes

These embedded static tools are development aids, not the accepted production
frontends. AXIOM and AEGIS live in their own repositories and release against
generated profile-specific Platform clients.

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

The table below describes the current broad development application. Core 1.0
will expose a configuration-driven `core` profile only after the internal
package boundary and forbidden-route/OpenAPI gates are implemented.

| Endpoint Group | Base Path | Purpose |
| --- | --- | --- |
| System | `/`, `/api/v1/live`, `/api/v1/health` | Root, liveness, readiness |
| Rules | `/api/v1/rules/*` and legacy rule endpoints | Rule CRUD, lookup, validation, import tree |
| Inference | `/api/v1/inference/*` | Sessions, next question, answers, summary, trace |
| Files | `/api/v1/files/*` | Document-to-markdown and document-to-rule conversion |
| Reasoning | `/api/v1/reasoning/*` | Abduction, induction, LLM goal mapping, trace explanation |
| Metrics | `/metrics`, `/api/v1/metrics` | Prometheus metrics |

## Frontend Tools

| Tool | Current Purpose | Production Direction |
| --- | --- | --- |
| Platform Rule Studio/AI Harness prototypes | Local static demonstrations | Retain only as development/demo tools or retire after client migration |
| AXIOM | General rule authoring, execution, simulation, provenance and audit inspection | Keep Svelte 5; use an authenticated thin BFF and generated Core client; never become a second engine |
| AEGIS | Autonomous-action and workflow governance | Keep Svelte 5; evolve its BFF into a separately released application backend owning AEGIS data and consuming Core APIs/events |

## Testing and Verification

Run the backend suite with the current quality gate:

```powershell
pytest --cov=src --cov-fail-under=97
```

Run legacy embedded frontend checks:

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
| Internal `inferra-core` package | P0.1 and P0.2a-P0.2b plus the security correction complete as internal 0.1.1 with clean installed-wheel parser and adversarial-expression proof; public-facade rewiring and remaining state/import/inference/provenance extraction pending; not publicly published |
| Backend API | Implemented and test-covered |
| Backend coverage gate | 97 percent line coverage, latest local gate 97.01 percent |
| Docker Compose stack | API, worker, Redis, Fuseki, PostgreSQL, OTel collector |
| Monitoring stack | Grafana, Prometheus, Loki, Promtail |
| Platform Rule Studio/AI Harness | Legacy prototypes implemented and checked; excluded from production frontend decisions |
| AXIOM | Separate candidate repository; build/audit pass but type, unit, lint and formatting gates currently fail |
| AEGIS | Separate candidate repository; check/test/build pass but security, persistence, synthetic-state, licensing, lint and formatting gates remain |
| Load smoke | k6 scripts available; local 500-VU compose production gate passes |
| Chaos smoke | Compose-scoped reversible drill and Phase 4 restart suite available; local restart suite passes for Redis, Fuseki, and worker |
| Production frontend composition | AXIOM and AEGIS are independently gated Svelte products; neither is automatically included in Core 1.0 |
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
| Authentication | Production startup fails closed unless `INFERRA_AUTH_ENABLED=true` and either `INFERRA_API_KEY` or `INFERRA_JWT_SECRET` is configured |
| Authorization | Authentication only grants read identity; configure `rules:write`, `ontology:write`, `aegis:write`, `files:convert`, or `llm:read` scopes as needed |
| CORS | Configure explicit `INFERRA_CORS_ALLOWED_ORIGINS`; production rejects wildcard origins and credentialed wildcard behavior is disabled |
| Secrets | Use `.env.example` only as a template; place real secrets in a platform secret manager before production traffic |
| Redis | Treat Redis as operational state, not the durable source of truth |
| PostgreSQL | Use managed backups, migrations, and least-privilege credentials |
| Fuseki | Protect admin access and define dataset backup/restore procedures |
| LLM usage | Keep LLM features disabled until provider, model, budget, and evaluation policy are approved |
| Editable AEGIS LLM keys | Set `AEGIS_LLM_API_KEY_ENCRYPTION_KEY` or `_FILE`; keep old keys in `AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS` during rotation until stored rows have been reread or rewritten |
| File uploads | Keep size limits, file type validation, and sandboxing strict |
| Observability | Keep dashboards and Prometheus alert rules live; tune thresholds and notification routing before production traffic |
| Rule changes | Require validation, versioning, review, and rollback paths |

AEGIS runtime provider keys are encrypted before persistence and decrypted only
for runtime client resolution. Database backups and replicas remain sensitive;
after suspected storage exposure, rotate the provider key, rotate the encryption
key, retain the previous encryption key only for migration, and verify affected
rows have been rewritten before removing old-key access.

## Future Roadmap

The active roadmap is maintained in `docs/ROADMAP.md`; the table below is a short product-level summary.

| Phase | Roadmap Item | Outcome |
| --- | --- | --- |
| Completed | Graph-first runtime default | `HyperAdjacencyGraph` is the default runtime path, with matrix adapters retained for compatibility |
| Completed | Freeze the `inferra-core` extraction inventory and semantic baseline | 243 modules classified, 29 internal crossings and the third-party dependency set frozen, six golden vectors active |
| Completed | Establish the internal `inferra-core` distribution, P0.2a-P0.2b slices, and security correction | 0.1.1 wheel/source build, small facade, bounded expression AST, fail-closed validation, typed cycles, exact leaf re-exports, and clean installed-wheel evidence |
| Near term | Publish the narrow compile/validation facade and rewire Platform; then move fact-store/iteration/imports and inference/provenance | Prove one installed-artifact vertical slice before expanding the extraction boundary |
| Near term | Implement package-backed Core API profile | Narrow production service contract and generated clients |
| Near term | Harden production readiness scripts | Repeatable local and CI confidence |
| Near term | Add Playwright frontend tests | Real browser confidence for prototypes |
| Completed | Add Grafana dashboards | Operational visibility for API, worker, Redis, Fuseki, logs, and reasoning metrics |
| Mid term | Harden AXIOM and AEGIS integrations | Authenticated BFFs, generated clients, product-specific e2e and release gates |
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
| Keep package status honest | Internal 0.1.1 exists only as a partial pre-release package; do not imply the whole engine is extracted or that a public registry package is available |
| Keep frontend status honest | The embedded prototypes are development aids; AXIOM and AEGIS are separate release units with independent blockers |

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

Until INFERRA Legal/IP approves and publishes a `LICENSE` file or equivalent
written licensing terms, the code and documentation in this public repository
should be treated as proprietary INFERRA material with all rights reserved.
Viewing the public repository does not grant permission to copy, modify,
distribute, sublicense, or use it in another product.
