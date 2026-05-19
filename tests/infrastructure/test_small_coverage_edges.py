from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.inbound.http.dependencies import get_settings
from src.adapters.outbound.reasoning.factory import create_induction_adapter
from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.adapters.inbound.http.dependencies import get_rule_repository, reset_singletons
from src.domain.state import __getattr__ as state_getattr
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.reasoning_tracing import reasoning_span
from src.infrastructure.secrets import redis_client_from_env, redis_url_from_env, read_secret


def test_reasoning_span_sets_non_null_attributes():
    span = MagicMock()
    tracer = MagicMock()
    tracer.start_as_current_span.return_value.__enter__.return_value = span
    trace_module = MagicMock()
    trace_module.get_tracer.return_value = tracer
    opentelemetry_module = SimpleNamespace(trace=trace_module)

    with patch.dict("sys.modules", {"opentelemetry": opentelemetry_module}):
        with reasoning_span("reason", {"kept": "yes", "skipped": None}):
            pass

    tracer.start_as_current_span.assert_called_once_with("reason")
    span.set_attribute.assert_called_once_with("kept", "yes")


def test_reasoning_span_noops_when_tracing_import_fails():
    with patch.dict("sys.modules", {"opentelemetry": None}):
        with reasoning_span("reason", {"kept": "yes"}):
            pass


def test_create_induction_adapter_returns_celery_adapter_when_enabled():
    adapter = create_induction_adapter(FeatureFlags(induction_pipeline=True))

    assert isinstance(adapter, CeleryInductionAdapter)


def test_get_settings_returns_config_singleton():
    from src.config import settings

    assert get_settings() is settings


def test_get_rule_repository_wraps_database_session():
    db = MagicMock()
    with patch("src.adapters.inbound.http.dependencies.RuleRepositoryImpl", return_value="repo") as repo_cls:
        assert get_rule_repository(db) == "repo"

    repo_cls.assert_called_once_with(db)


def test_reset_singletons_clears_session_store_cache():
    with patch.object(__import__("src.adapters.inbound.http.dependencies", fromlist=["get_session_store"]).get_session_store, "cache_clear") as clear:
        reset_singletons()

    clear.assert_called_once()


def test_state_module_getattr_rejects_unknown_name():
    with pytest.raises(AttributeError):
        state_getattr("UnknownThing")


def test_read_secret_prefers_file_over_environment(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("from-file\n", encoding="utf-8")

    with patch.dict(
        "os.environ",
        {
            "INFERRA_TEST_SECRET": "from-env",
            "INFERRA_TEST_SECRET_FILE": str(secret_file),
        },
    ):
        assert read_secret("INFERRA_TEST_SECRET") == "from-file"


def test_read_secret_falls_back_to_env_or_default():
    with patch.dict("os.environ", {"INFERRA_TEST_SECRET": "from-env"}, clear=False):
        assert read_secret("INFERRA_TEST_SECRET") == "from-env"
    with patch.dict("os.environ", {}, clear=True):
        assert read_secret("INFERRA_TEST_SECRET", "fallback") == "fallback"


def test_redis_url_prefers_explicit_url():
    with patch.dict("os.environ", {"REDIS_URL": "redis://configured:6379/0"}, clear=True):
        assert redis_url_from_env("REDIS_URL", "redis://localhost:6379/0", 0) == "redis://configured:6379/0"


def test_redis_url_builds_from_secret_file(tmp_path):
    secret_file = tmp_path / "redis-password.txt"
    secret_file.write_text("p@ss word\n", encoding="utf-8")

    with patch.dict(
        "os.environ",
        {
            "REDIS_PASSWORD_FILE": str(secret_file),
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6380",
        },
        clear=True,
    ):
        assert redis_url_from_env("REDIS_URL", "redis://localhost:6379/0", 1) == "redis://:p%40ss%20word@redis:6380/1"


def test_redis_client_uses_secret_aware_url():
    fake_redis = MagicMock()
    with patch.dict("os.environ", {"REDIS_PASSWORD": "secret", "REDIS_HOST": "redis"}, clear=True):
        with patch.dict("sys.modules", {"redis": fake_redis}):
            redis_client_from_env("REDIS_URL", "redis://localhost:6379/0", 0)

    fake_redis.Redis.from_url.assert_called_once_with("redis://:secret@redis:6379/0")
