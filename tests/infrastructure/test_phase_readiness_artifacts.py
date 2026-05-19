from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_production_readiness_doc_records_stack_and_remaining_work():
    content = read_text("docs/INFERRA_Production_Readiness_and_Tech_Stack.md")

    assert "| Area | Recommendation |" in content
    assert "| Option | Strengths | Weaknesses | INFERRA fit | Recommendation |" in content
    assert "HyperAdjacencyGraph as canonical" in content
    assert "ABCMeta ports" in content
    assert "Remaining Work Matrix" in content
    assert "Load smoke" in content
    assert "Grafana, Prometheus, Loki, Promtail" in content


def test_phase_and_future_docs_are_archived_not_root_backlog():
    root_files = {path.name for path in (ROOT / "docs").glob("*.md")}

    assert "INFERRA_Phase1_Implementation_Plan.md" not in root_files
    assert "INFERRA_Phase5_Implementation_Plan.md" not in root_files
    assert "future INFERRA GraphRAG Integration Plan.md" not in root_files
    assert "suggested_enhancement_for_phase5_implementation.md" not in root_files
    assert (ROOT / "docs/archive/phase-plans/INFERRA_Phase5_Implementation_Plan.md").exists()
    assert (ROOT / "docs/archive/future-and-enhancements/future INFERRA GraphRAG Integration Plan.md").exists()
    assert (ROOT / "docs/archive/operations-notes/INFERRA Redis run in container.md").exists()


def test_docs_index_and_reference_comparison_capture_current_truth():
    index = read_text("docs/README.md")
    report = read_text("docs/INFERRA_vs_PALOS_PyRest_Comparison_Report.md")
    implementation = read_text("docs/IMPLEMENTATION_STATUS.md")
    roadmap = read_text("docs/ROADMAP.md")
    operations = read_text("docs/OPERATIONS.md")
    archive = read_text("docs/archive/README.md")

    assert "CURRENT_SCHEMA_VERSION = 5" in index
    assert "IMPLEMENTATION_STATUS.md" in index
    assert "ROADMAP.md" in index
    assert "OPERATIONS.md" in index
    assert "INFERRA_vs_PALOS_PyRest_Comparison_Report.md" in index
    assert "archive/phase-plans/" in index
    assert "graph-first runtime" in report
    assert "not the architectural north star" in report
    assert "CI `load-gate`" in report
    assert "2447 passed, 66 skipped" in implementation
    assert "Benchmark gate" in implementation
    assert "OpenAPI release artifact" in implementation
    assert "Generate `openapi.json` in CI" in roadmap
    assert "production overlay requires non-default secret material" in operations
    assert "not the current implementation backlog" in archive


def test_k6_smoke_has_thresholds_and_reasoning_coverage():
    content = read_text("tests/load/k6_api_smoke.js")

    assert "thresholds" in content
    assert "http_req_failed" in content
    assert "/api/v1/live" in content
    assert "/api/v1/health" in content
    assert "/api/v1/reasoning/abduct" in content
    assert "/api/v1/reasoning/goal" in content
    assert "inferra_abduction_total" in content
    assert "endpoint:readiness" in content


def test_k6_production_gate_separates_user_load_from_metrics_scrapes():
    content = read_text("tests/load/k6_production_gate.js")

    assert "constant-vus" in content
    assert "user_sessions" in content
    assert "metrics_scrape" in content
    assert "liveness_probe" in content
    assert "constant-arrival-rate" in content
    assert "METRICS_RATE" in content
    assert "LIVE_RATE" in content
    assert "USER_SLEEP_SECONDS" in content
    assert "/api/v1/reasoning/abduct" in content
    assert "/metrics" in content


def test_dockerized_k6_runner_is_available_for_local_machines_without_k6():
    content = read_text("tests/load/run_k6_docker.ps1")
    production_content = read_text("tests/load/run_k6_production_gate.ps1")

    assert "grafana/k6" in content
    assert "host.docker.internal" in content
    assert "k6_api_smoke.js" in content
    assert "--network" in content
    assert "k6_production_gate.js" in production_content
    assert "http://api:8000" in production_content
    assert "inferra_default" in production_content
    assert "Dockerized k6 smoke failed" in content


def test_phase_readiness_script_runs_backend_frontend_and_live_smoke():
    content = read_text("scripts/verify_phase_readiness.ps1")

    assert "pytest --cov=src --cov-fail-under=97" in content
    assert "npm.cmd test" in content
    assert "npm.cmd run check" in content
    assert "/api/v1/health" in content
    assert "/metrics" in content
    assert "/api/v1/reasoning/abduct" in content
    assert "-UseBasicParsing" in content
    assert "Assert-LastExitCode" in content
    assert "http://localhost:3000/api/health" in content


def test_release_candidate_script_collects_production_gates():
    content = read_text("scripts/verify_release_candidate.ps1")

    assert "pytest --cov=src --cov-fail-under=97" in content
    assert "test_phase5_acceptance.py -q --run-integration" in content
    assert "pytest tests/benchmarks/ -q" in content
    assert "lint-imports --config .importlinter" in content
    assert "legacy_retirement_report" in content
    assert "run_k6_production_gate.ps1 -Vus 500 -Duration 1m" in content
    assert "run_phase4_chaos_suite.ps1" in content


def test_production_decision_and_legacy_registers_exist():
    decision = read_text("docs/INFERRA_Production_Decision_Register.md")
    legacy = read_text("docs/INFERRA_Legacy_Retirement_Register.md")

    assert "Secret manager" in decision
    assert "Auth policy" in decision
    assert "LLM provider/model" in decision
    assert "Release sign-off" in decision
    assert "FeatureFlags().legacy_retirement_report()" in decision
    assert "INFERRA_USE_HYPERGRAPH" in legacy
    assert "INFERRA_LEGACY_ITERATE" in legacy
    assert "DependencyMatrix" in legacy
    assert "MLTopologicalSortStrategy" in legacy


def test_ci_workflow_keeps_backend_frontend_and_docker_gates():
    content = read_text(".github/workflows/ci.yml")

    assert "pytest --cov=src --cov-fail-under=97" in content
    assert "lint-imports --config .importlinter" in content
    assert "npm test" in content
    assert "npm run check" in content
    assert "docker compose build api worker" in content
    assert "load-gate:" in content
    assert "grafana/k6:0.51.0" in content
    assert "k6_production_gate.js" in content
    assert "--network inferra_default" in content


def test_chaos_script_is_reversible_and_compose_scoped():
    content = read_text("tests/chaos/docker_chaos_smoke.ps1")
    suite = read_text("tests/chaos/run_phase4_chaos_suite.ps1")

    assert "ValidateSet" in content
    assert "pause" in content
    assert "unpause" in content
    assert "restart" in content
    assert "docker compose" in content
    assert "Wait-Healthy" in content
    assert "RecoveryTimeoutSeconds" in content
    assert "Remove-Item" not in content
    assert "docker_chaos_smoke.ps1" in suite
    assert '"redis", "fuseki", "worker"' in suite
    assert "-Action restart" in suite


def test_secret_template_and_compose_secret_substitution_exist():
    compose = read_text("docker-compose.yml")
    env_example = read_text(".env.example")

    assert "INFERRA_AUTH_ENABLED: ${INFERRA_AUTH_ENABLED:-false}" in compose
    assert "INFERRA_JWT_SECRET: ${INFERRA_JWT_SECRET:-}" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-inferra}" in compose
    assert "GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}" in compose
    assert "FUSEKI_PASSWORD: ${FUSEKI_PASSWORD:-admin}" in compose
    assert "replace-with-random-api-key" in env_example
    assert "replace-with-postgres-password" in env_example


def test_local_production_compose_overlay_and_secret_scripts_exist():
    compose = read_text("docker-compose.prod.yml")
    init_sh = read_text("secrets/init-secrets.sh")
    init_ps1 = read_text("secrets/init-secrets.ps1")

    assert "Local production overlay" in compose
    assert "restart: unless-stopped" in compose
    assert "deploy:" in compose
    assert "INFERRA_API_KEY_FILE" in compose
    assert "POSTGRES_PASSWORD: \"\"" in compose
    assert "POSTGRES_PASSWORD_FILE" in compose
    assert "POSTGRES_PASSWORD required" in compose
    assert "GF_SECURITY_ADMIN_PASSWORD__FILE" in compose
    assert "GF_SECURITY_ADMIN_PASSWORD: \"\"" in compose
    assert "redis_password" in compose
    assert "REDIS_PASSWORD_FILE" in compose
    assert "redis-cli -a" in compose
    assert "FUSEKI_PASSWORD required" in compose
    assert "zai_api_key" in compose
    assert ".env.prod.local" in init_sh
    assert "inferra_jwt_secret" in init_sh
    assert 'generate_secret "redis_password"' in init_sh
    assert ".env.prod.local" in init_ps1
    assert "New-SecretFile" in init_ps1
    assert 'New-SecretFile "redis_password"' in init_ps1


def test_container_hardening_artifacts_are_enforced():
    dockerfile = read_text("Dockerfile")
    compose = read_text("docker-compose.yml")

    assert "FROM python:3.10-slim AS builder" in dockerfile
    assert "USER inferra" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert 'max-size: "10m"' in compose
    assert "127.0.0.1:6379:6379" in compose
    assert "app.control.inspect(timeout=2).ping()" in compose


def test_k6_multi_profile_runner_is_available():
    script = read_text("tests/load/k6_profiles.js")
    runner = read_text("tests/load/run_k6_profiles.ps1")
    docker_runner = read_text("tests/load/run_k6_docker.ps1")

    assert "PROFILE" in script
    assert "smoke" in script
    assert "load" in script
    assert "stress" in script
    assert "spike" in script
    assert "soak" in script
    assert "/api/v1/reasoning/abduct" in script
    assert 'ValidateSet("smoke", "load", "stress", "spike", "soak", "all")' in runner
    assert "-Profile $current" in runner
    assert "-e\", \"PROFILE=$Profile" in docker_runner


def test_import_linter_config_is_present_and_ci_enforced():
    config = read_text(".importlinter")
    pyproject = read_text("pyproject.toml")

    assert "root_package = src" in config
    assert "Domain layer must not import adapters" in config
    assert "Ports must not import adapters" in config
    assert "src.adapters" in config
    assert "import-linter" in pyproject
