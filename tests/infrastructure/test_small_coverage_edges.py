from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.inbound.http.dependencies import get_settings
from src.adapters.outbound.reasoning.factory import create_induction_adapter
from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.dependencies import get_rule_repository, reset_singletons
from src.domain.state import __getattr__ as state_getattr
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.reasoning_tracing import reasoning_span


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
    with patch("src.dependencies.RuleRepositoryImpl", return_value="repo") as repo_cls:
        assert get_rule_repository(db) == "repo"

    repo_cls.assert_called_once_with(db)


def test_reset_singletons_clears_session_store_cache():
    with patch.object(__import__("src.dependencies", fromlist=["get_session_store"]).get_session_store, "cache_clear") as clear:
        reset_singletons()

    clear.assert_called_once()


def test_state_module_getattr_rejects_unknown_name():
    with pytest.raises(AttributeError):
        state_getattr("UnknownThing")
