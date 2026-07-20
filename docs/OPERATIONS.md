# INFERRA Operations Runbook

Status: active operations guide
Last updated: 2026-07-20

This runbook replaces the older standalone Redis and Fuseki notes in `docs/archive/operations-notes/`.

This runbook operates the authoritative Platform **service**. The accepted
internal `inferra-core` package does not replace these operational
responsibilities. Direct embedded-library hosts own their own persistence,
identity, concurrency, migrations, durable audit, backup, and recovery and are
outside this runbook unless a supported embedded operations profile is added.
Internal `inferra-core==0.1.1` currently exposes only its small leaf facade; its
executable parser/graph/validation layer is private and state/inference layers
remain incomplete. It is not a complete supported embedded engine or a
publicly available package.

## Local Stack
Start the integrated local stack:

```powershell
docker compose up -d --build
docker compose ps
```

Important local endpoints:

| Service | URL |
| --- | --- |
| API | `http://localhost:8000` |
| Health | `http://localhost:8000/api/v1/health` |
| Liveness | `http://localhost:8000/api/v1/live` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| Loki | `http://localhost:3100` |
| Fuseki | `http://localhost:3030` |
| Redis | `localhost:6379` |

Infrastructure ports are bound to localhost except the API. Local defaults are intentionally ergonomic; production rehearsal is stricter.

### Environment and Feature Profile

The API (`src.main`) and worker (`src.tasks.celery_app`) load `.env` at their
process boundaries before the effective feature-flag snapshot is constructed.
Exported variables always win. Use `INFERRA_ENV_FILE` to select another file,
or set `INFERRA_LOAD_DOTENV=false` when the launcher or platform injects the
complete environment. Domain modules do not load files directly.

The base Compose stack is the feature-rich, loopback-only local profile. Its
single 28-entry feature mapping is merged into both API and worker. In
particular, `INFERRA_ASYNC_POST_REASONING` and
`INFERRA_GENERATE_POST_REASONING_TTL` are both enabled; override both together.
The commented canonical defaults and separately labelled local overrides are
listed in `.env.example`.

Compose treats the root `.env` as host-side interpolation input, exports the
resolved mapping, and sets `INFERRA_LOAD_DOTENV=false` inside both containers.
The file is not a second container-side configuration source.

Invalid numeric feature configuration fails API and worker startup. Confidence
thresholds must be within `0.0..1.0`, hierarchy depths must be non-negative,
and maximum closure depth must be at least minimum hierarchy depth.

Startup also rejects profiles that disable `INFERRA_USE_HYPERGRAPH`,
`INFERRA_LAYERED_MEMORY`, or `INFERRA_STRICT_PORT_CONTRACTS`, and rejects a
half-enabled post-reasoning pair. These required-true names remain temporarily
for compatibility and rollback evidence; they do not represent supported
production off ramps.

Inference sessions freeze their selected orchestration and reasoning profile.
When deduction has no askable question, the API invokes the selected legacy or
hybrid orchestrator; the hybrid path receives the real/null router plus the
abduction, induction, and confidence gates from that same snapshot. Reasoning
endpoint `enabled` fields may opt out, but never enable a process flag that is
off. PROV-O trace export requires the frozen `PROV_O_TRACE` gate, while
`ENRICHED_API` controls provenance and reasoning metadata in responses.

API and worker startup logs emit one redaction-safe `feature_flag_snapshot`
record containing the deployment profile, process role, effective values,
value sources, and a stable hash. With authentication enabled, inspect the API
process through `GET /api/v1/system/feature-flags` using credentials that have
the `system:read` scope.

Capture and compare the rendered API/worker profiles without starting the
stack:

```powershell
docker compose -f docker-compose.yml config --format json |
    python scripts/capture_feature_flag_evidence.py --compose-config - --output artifacts/release/feature-flag-snapshots.json
```

The command exits non-zero if the two snapshots differ. New rule-sync,
post-reasoning, and induction jobs also carry the publisher hash and are
rejected by a worker whose effective profile differs.

## Production Rehearsal

Production rehearsal must install/use the exact built `inferra-core` artifact
selected by the Platform release once whole-engine extraction and Platform
rewiring are complete. Do not
mount the repository source tree in a way that masks a missing or incompatible
wheel. Startup and release evidence must report the Core version and SHA-256.
Generate local secret files:

```powershell
powershell -ExecutionPolicy Bypass -File secrets/init-secrets.ps1
```

or on a POSIX shell:

```bash
bash secrets/init-secrets.sh
```

Start the production overlay:

```powershell
docker compose --env-file secrets/.env.prod.local -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production overlay requires non-default secret material and enables Redis password auth through Docker secrets. Application Redis clients must use `redis_url_from_env()` or `redis_client_from_env()` so `REDIS_PASSWORD_FILE` is honored.

## Readiness Checks
Run the local readiness script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_phase_readiness.ps1
```

Run the release-candidate aggregate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_release_candidate.ps1
```

Core manual checks:

```powershell
pytest --cov=src --cov-fail-under=97
lint-imports --config .importlinter
pytest tests/benchmarks/ -q
pytest tests/integration/test_phase5_acceptance.py -q --run-integration
```

## Load and Chaos
Dockerized k6 production profile:

```powershell
powershell -ExecutionPolicy Bypass -File tests/load/run_k6_production_gate.ps1 -Vus 500 -Duration 1m
```

Multi-profile k6 runner:

```powershell
powershell -ExecutionPolicy Bypass -File tests/load/run_k6_profiles.ps1 -Profile smoke
```

Reversible chaos smoke:

```powershell
powershell -ExecutionPolicy Bypass -File tests/chaos/docker_chaos_smoke.ps1 -Service redis -Action restart
```

Phase 4 restart suite:

```powershell
powershell -ExecutionPolicy Bypass -File tests/chaos/run_phase4_chaos_suite.ps1
```

## Data Authority and Graph Lifecycle

PostgreSQL is the authority for rules, decisions, provenance, graph catalogue,
outbox, reconciliation, and retention policy. Fuseki is a critical rebuildable
versioned RDF/PROV-O projection; it is not the only copy of a governed record.

The accepted target retains graph versions indefinitely by default and permits
only versioned, authorized retention-policy overrides. Do not manually overwrite
or delete a production rule/case named graph as a retention mechanism. A future
purge operation must coordinate PostgreSQL, outbox/audit, Fuseki, caches,
backups/exports, and any permitted tombstone.

The current code does not yet implement the complete account/case graph
catalogue, immutable normal-path case projection, retention engine, or proven
PostgreSQL-to-Fuseki rebuild. Until the release gates in
`INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md` pass, operators
must treat ontology lifecycle/recovery as incomplete and must not certify a
manual Fuseki graph as the durable audit record.

## Secrets
Local `.env` values are for development only. Production traffic must use the deployment platform secret manager.

Secret-aware environment variables currently supported:

| Secret | File env |
| --- | --- |
| `INFERRA_API_KEY` | `INFERRA_API_KEY_FILE` |
| `INFERRA_JWT_SECRET` | `INFERRA_JWT_SECRET_FILE` |
| `INFERRA_CSRF_TOKEN` | `INFERRA_CSRF_TOKEN_FILE` |
| `SQLALCHEMY_DATABASE_URI` | `SQLALCHEMY_DATABASE_URI_FILE` |
| `AEGIS_SQLALCHEMY_DATABASE_URI` | `AEGIS_SQLALCHEMY_DATABASE_URI_FILE` |
| `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD_FILE` |
| `REDIS_PASSWORD` | `REDIS_PASSWORD_FILE` |
| `FUSEKI_PASSWORD` | `FUSEKI_PASSWORD_FILE` |
| `ZAI_API_KEY` | `ZAI_API_KEY_FILE` |

## Troubleshooting
| Symptom | First checks |
| --- | --- |
| API unhealthy | `docker compose logs api worker redis postgres fuseki --no-color` |
| Redis auth failures in prod overlay | Confirm `REDIS_PASSWORD_FILE` is mounted and code path uses `redis_client_from_env()` |
| Worker healthcheck fails | Confirm Redis is healthy and `celery -A src.tasks.celery_app.app inspect ping` works inside the compose network |
| Fuseki unavailable | Check `FUSEKI_PASSWORD`/`FUSEKI_PASSWORD_FILE`, dataset volume, and `http://localhost:3030/$/ping` |
| Metrics slow under load | Check metrics cache TTL, Prometheus scrape interval, and k6 metrics scenario rate |

## Release Evidence
Attach these to release candidates:

- internal `inferra-core` wheel/source distribution hashes, dependency/SBOM
  metadata, installed-wheel test result, forbidden-import result, golden-vector
  comparison, and Platform-reported Core version/hash,
- backend coverage output,
- import-linter output,
- benchmark output,
- OpenAPI artifact,
- readiness script output,
- k6 smoke/production output,
- chaos output,
- `FeatureFlags().legacy_retirement_report()` for the target environment,
- production decision register status.
