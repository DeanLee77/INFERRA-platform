from fastapi import FastAPI
from unittest.mock import Mock, patch

from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure import observability
from src.infrastructure.observability import configure_observability


def test_configure_observability_skips_when_disabled():
    app = FastAPI()

    with patch(
        "src.infrastructure.observability.get_feature_flags",
        return_value=FeatureFlags(observability_enabled=False),
    ):
        assert configure_observability(app) is False

    assert not getattr(app.state, "otel_instrumented", False)


def test_configure_observability_returns_false_when_dependency_missing():
    app = FastAPI()

    with patch("src.infrastructure.observability.OTEL_AVAILABLE", False):
        assert configure_observability(app, enabled=True) is False

    assert app.state.otel_instrumented is False


def test_configure_observability_instruments_app_once():
    app = FastAPI()
    provider = Mock()

    with patch("src.infrastructure.observability._ensure_tracer_provider", return_value=provider):
        with patch.object(observability.FastAPIInstrumentor, "instrument_app") as instrument_app:
            assert configure_observability(app, enabled=True) is True
            assert configure_observability(app, enabled=True) is True

    instrument_app.assert_called_once_with(app, tracer_provider=provider)
    assert app.state.otel_instrumented is True


def test_configure_observability_uses_feature_flag_when_enabled_argument_is_none():
    app = FastAPI()
    provider = Mock()

    with patch(
        "src.infrastructure.observability.get_feature_flags",
        return_value=FeatureFlags(observability_enabled=True),
    ):
        with patch("src.infrastructure.observability._ensure_tracer_provider", return_value=provider):
            with patch.object(observability.FastAPIInstrumentor, "instrument_app") as instrument_app:
                assert configure_observability(app) is True

    instrument_app.assert_called_once_with(app, tracer_provider=provider)


def test_configure_observability_returns_false_on_instrumentation_error():
    app = FastAPI()

    with patch("src.infrastructure.observability._ensure_tracer_provider", return_value=Mock()):
        with patch.object(observability.FastAPIInstrumentor, "instrument_app", side_effect=Exception("otel boom")):
            assert configure_observability(app, enabled=True) is False

    assert app.state.otel_instrumented is False


def test_build_span_exporter_uses_console_when_requested():
    with patch.dict("os.environ", {"INFERRA_OTEL_CONSOLE_EXPORTER": "true"}, clear=True):
        exporter = observability._build_span_exporter()

    assert exporter is not None


def test_build_span_exporter_returns_none_without_endpoint_or_console():
    with patch.dict("os.environ", {}, clear=True):
        assert observability._build_span_exporter() is None


def test_build_span_exporter_uses_otlp_endpoint():
    fake_exporter_cls = Mock(return_value=Mock(name="otlp-exporter"))

    with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4317", "OTEL_EXPORTER_OTLP_INSECURE": "false"}, clear=True):
        with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", fake_exporter_cls):
            exporter = observability._build_span_exporter()

    assert exporter is fake_exporter_cls.return_value
    fake_exporter_cls.assert_called_once_with(endpoint="http://otel:4317", insecure=False)


def test_ensure_tracer_provider_returns_existing_provider_when_configured():
    with patch("src.infrastructure.observability._PROVIDER_CONFIGURED", True):
        with patch.object(observability.trace, "get_tracer_provider", return_value="existing") as get_provider:
            assert observability._ensure_tracer_provider() == "existing"
            get_provider.assert_called_once()


def test_ensure_tracer_provider_builds_provider_once():
    provider = Mock()
    resource = Mock()

    with patch("src.infrastructure.observability._PROVIDER_CONFIGURED", False):
        with patch.object(observability.Resource, "create", return_value=resource) as create_resource:
            with patch.object(observability, "TracerProvider", return_value=provider) as provider_cls:
                with patch("src.infrastructure.observability._build_span_exporter", return_value=None):
                    with patch.object(observability.trace, "set_tracer_provider") as set_provider:
                        assert observability._ensure_tracer_provider() is provider

    create_resource.assert_called_once()
    provider_cls.assert_called_once_with(resource=resource)
    set_provider.assert_called_once_with(provider)


def test_ensure_tracer_provider_adds_batch_processor_when_exporter_exists():
    provider = Mock()
    resource = Mock()
    exporter = Mock()
    processor = Mock()

    with patch("src.infrastructure.observability._PROVIDER_CONFIGURED", False):
        with patch.object(observability.Resource, "create", return_value=resource):
            with patch.object(observability, "TracerProvider", return_value=provider):
                with patch("src.infrastructure.observability._build_span_exporter", return_value=exporter):
                    with patch.object(observability, "BatchSpanProcessor", return_value=processor) as processor_cls:
                        with patch.object(observability.trace, "set_tracer_provider"):
                            assert observability._ensure_tracer_provider() is provider

    processor_cls.assert_called_once_with(exporter)
    provider.add_span_processor.assert_called_once_with(processor)


def test_service_name_uses_environment_default_and_override():
    with patch.dict("os.environ", {}, clear=True):
        assert observability._service_name() == observability.DEFAULT_SERVICE_NAME

    with patch.dict("os.environ", {"OTEL_SERVICE_NAME": "custom"}, clear=True):
        assert observability._service_name() == "custom"
