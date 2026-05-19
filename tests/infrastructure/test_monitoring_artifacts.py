import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_grafana_dashboard_is_valid_json_and_uses_real_inferra_metrics():
    dashboard = json.loads(
        read_text("monitoring/grafana/dashboards/inferra-operational-overview.json")
    )
    content = json.dumps(dashboard)

    assert dashboard["uid"] == "inferra-operational-overview"
    assert "inferra_propagation_duration_seconds" in content
    assert "inferra_semantic_cache_hit_rate" in content
    assert "inferra_fuseki_sync_duration_seconds" in content
    assert "inferra_induction_total" in content
    assert "inferra_reasoning_route_total" in content
    assert "inferra_llm_call_total" in content
    assert "palos_" not in content


def test_grafana_datasources_are_provisioned():
    content = read_text("monitoring/grafana/provisioning/datasources/datasources.yml")

    assert "uid: prometheus" in content
    assert "url: http://prometheus:9090" in content
    assert "uid: loki" in content
    assert "url: http://loki:3100" in content
    assert "uid: postgres" in content
    assert "database: inferra" in content


def test_prometheus_scrapes_inferra_api_and_monitoring_stack():
    content = read_text("monitoring/prometheus/prometheus.yml")

    assert "rule_files:" in content
    assert "/etc/prometheus/rules/*.yml" in content
    assert "job_name: inferra-api" in content
    assert "metrics_path: /metrics" in content
    assert "api:8000" in content
    assert "job_name: grafana" in content
    assert "job_name: loki" in content
    assert "job_name: promtail" in content


def test_prometheus_alert_rules_cover_core_production_failure_modes():
    content = read_text("monitoring/prometheus/rules/inferra-alerts.yml")

    assert "InferraApiDown" in content
    assert "InferraFusekiSyncFailures" in content
    assert "InferraInductionFailures" in content
    assert "InferraAbductionErrorRateHigh" in content
    assert "InferraLlmErrorRatioHigh" in content
    assert "InferraSemanticCacheHitRateLow" in content
    assert "inferra_llm_call_total" in content
    assert "inferra_semantic_cache_hit_rate" in content


def test_docker_compose_includes_monitoring_services():
    content = read_text("docker-compose.yml")

    assert "name: inferra" in content
    assert "image: inferra-api:local" in content
    assert "image: inferra-worker:local" in content
    assert "prometheus:" in content
    assert "grafana:" in content
    assert "loki:" in content
    assert "promtail:" in content
    assert "postgres-data:" in content
    assert "fuseki-data:" in content
    assert "3000:3000" in content
    assert "9090:9090" in content
    assert "3100:3100" in content
    assert "./monitoring/prometheus/rules:/etc/prometheus/rules:ro" in content


def test_loki_and_promtail_are_configured_for_compose_log_explorer():
    loki = read_text("monitoring/loki/local-config.yaml")
    promtail = read_text("monitoring/promtail/config.yml")

    assert "auth_enabled: false" in loki
    assert "schema: v13" in loki
    assert "docker_sd_configs" in promtail
    assert "compose_service" in promtail
    assert "http://loki:3100/loki/api/v1/push" in promtail
