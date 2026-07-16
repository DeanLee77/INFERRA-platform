import os
from pathlib import Path

import pytest

from src.infrastructure.environment import load_process_environment
from src.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_process_environment_loads_selected_dotenv_file(monkeypatch, tmp_path):
    env_file = tmp_path / "inferra.env"
    env_file.write_text("INFERRA_USE_HYPERGRAPH=false\n", encoding="utf-8")
    monkeypatch.delenv("INFERRA_USE_HYPERGRAPH", raising=False)
    monkeypatch.setenv("INFERRA_LOAD_DOTENV", "true")

    try:
        assert load_process_environment(env_file) is True
        assert os.environ["INFERRA_USE_HYPERGRAPH"] == "false"
    finally:
        os.environ.pop("INFERRA_USE_HYPERGRAPH", None)


def test_exported_environment_precedes_dotenv_file(monkeypatch, tmp_path):
    env_file = tmp_path / "inferra.env"
    env_file.write_text("INFERRA_USE_HYPERGRAPH=false\n", encoding="utf-8")
    monkeypatch.setenv("INFERRA_LOAD_DOTENV", "true")
    monkeypatch.setenv("INFERRA_USE_HYPERGRAPH", "true")

    assert load_process_environment(env_file) is True
    assert os.environ["INFERRA_USE_HYPERGRAPH"] == "true"


def test_process_environment_uses_configured_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / "worker.env"
    env_file.write_text("INFERRA_ASYNC_SYNC_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setenv("INFERRA_LOAD_DOTENV", "true")
    monkeypatch.setenv("INFERRA_ENV_FILE", str(env_file))
    monkeypatch.delenv("INFERRA_ASYNC_SYNC_ENABLED", raising=False)

    try:
        assert load_process_environment() is True
        assert os.environ["INFERRA_ASYNC_SYNC_ENABLED"] == "true"
    finally:
        os.environ.pop("INFERRA_ASYNC_SYNC_ENABLED", None)


@pytest.mark.parametrize("disabled_value", ("false", "0", "no"))
def test_process_environment_loading_can_be_disabled(
    monkeypatch,
    tmp_path,
    disabled_value,
):
    env_file = tmp_path / "inferra.env"
    env_file.write_text("INFERRA_USE_HYPERGRAPH=false\n", encoding="utf-8")
    monkeypatch.setenv("INFERRA_LOAD_DOTENV", disabled_value)
    monkeypatch.delenv("INFERRA_USE_HYPERGRAPH", raising=False)

    assert load_process_environment(env_file) is False
    assert "INFERRA_USE_HYPERGRAPH" not in os.environ


def test_invalid_dotenv_loading_switch_fails_fast(monkeypatch):
    monkeypatch.setenv("INFERRA_LOAD_DOTENV", "sometimes")

    with pytest.raises(ValueError, match="INFERRA_LOAD_DOTENV must be one of"):
        load_process_environment()


def test_settings_consumes_only_process_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_TIMEOUT=99\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)

    assert Settings().LLM_TIMEOUT == 30.0

    monkeypatch.setenv("INFERRA_LOAD_DOTENV", "true")
    try:
        assert load_process_environment(env_file) is True
        assert Settings().LLM_TIMEOUT == 99.0
    finally:
        os.environ.pop("LLM_TIMEOUT", None)


def test_api_and_worker_load_environment_before_application_imports():
    main_source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "src" / "tasks" / "celery_app.py").read_text(
        encoding="utf-8"
    )

    assert main_source.index("load_process_environment()") < main_source.index(
        "from src.adapters.inbound.http import api_router"
    )
    assert worker_source.index("load_process_environment()") < worker_source.index(
        "from src.domain.state.feature_flags import ("
    )
    assert "validate_runtime_feature_flags(get_feature_flags())" in main_source
    assert "validate_runtime_feature_flags(get_feature_flags())" in worker_source
    assert "build_effective_feature_flag_report" in main_source
    assert '"feature_flag_snapshot"' in main_source
    assert "build_effective_feature_flag_report" in worker_source
    assert '"feature_flag_snapshot"' in worker_source
    assert "os.environ.setdefault(\"INFERRA_LOAD_DOTENV\", \"false\")" in (
        ROOT / "tests" / "conftest.py"
    ).read_text(encoding="utf-8")
