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


def test_dockerized_k6_runner_is_available_for_local_machines_without_k6():
    content = read_text("tests/load/run_k6_docker.ps1")

    assert "grafana/k6" in content
    assert "host.docker.internal" in content
    assert "k6_api_smoke.js" in content
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


def test_ci_workflow_keeps_backend_frontend_and_docker_gates():
    content = read_text(".github/workflows/ci.yml")

    assert "pytest --cov=src --cov-fail-under=97" in content
    assert "npm test" in content
    assert "npm run check" in content
    assert "docker compose build api worker" in content


def test_chaos_script_is_reversible_and_compose_scoped():
    content = read_text("tests/chaos/docker_chaos_smoke.ps1")

    assert "ValidateSet" in content
    assert "pause" in content
    assert "unpause" in content
    assert "restart" in content
    assert "docker compose" in content
    assert "Wait-Healthy" in content
    assert "RecoveryTimeoutSeconds" in content
    assert "Remove-Item" not in content
