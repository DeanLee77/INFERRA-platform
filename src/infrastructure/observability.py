import os
from typing import Any

import structlog
from fastapi import FastAPI

from src.domain.state.feature_flags import get_feature_flags

try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    trace = None
    FastAPIInstrumentor = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    ParentBased = None
    TraceIdRatioBased = None
    OTEL_AVAILABLE = False

logger = structlog.get_logger("inferra.observability")

DEFAULT_SERVICE_NAME = "inferra-api"
_PROVIDER_CONFIGURED = False


def configure_observability(app: FastAPI, enabled: bool | None = None) -> bool:
    """Optionally instrument FastAPI with OpenTelemetry."""
    is_enabled = get_feature_flags().observability_enabled if enabled is None else enabled
    if not is_enabled:
        return False
    if getattr(app.state, "otel_instrumented", False):
        return True
    if not OTEL_AVAILABLE:
        logger.warning("otel_dependencies_not_installed")
        app.state.otel_instrumented = False
        return False

    try:
        provider = _ensure_tracer_provider()
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        app.state.otel_instrumented = True
        logger.info("otel_fastapi_instrumented", service_name=_service_name())
        return True
    except Exception:
        logger.warning("otel_fastapi_instrumentation_failed", exc_info=True)
        app.state.otel_instrumented = False
        return False


def _ensure_tracer_provider() -> Any:
    global _PROVIDER_CONFIGURED
    if _PROVIDER_CONFIGURED:
        return trace.get_tracer_provider()

    resource = Resource.create({"service.name": _service_name()})
    sampler = _build_sampler()
    provider = (
        TracerProvider(resource=resource, sampler=sampler)
        if sampler is not None
        else TracerProvider(resource=resource)
    )
    exporter = _build_span_exporter()
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _PROVIDER_CONFIGURED = True
    return provider


def _build_span_exporter() -> Any:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() not in {"0", "false", "no"}
        return OTLPSpanExporter(endpoint=endpoint, insecure=insecure)

    if os.environ.get("INFERRA_OTEL_CONSOLE_EXPORTER", "").lower() in {"1", "true", "yes"}:
        return ConsoleSpanExporter()
    return None


def _build_sampler() -> Any:
    """Build an optional OTel sampler from INFERRA or standard OTel env vars."""
    raw_rate = os.environ.get("INFERRA_OTEL_SAMPLE_RATE")
    if raw_rate is None:
        sampler_name = os.environ.get("OTEL_TRACES_SAMPLER", "").lower()
        if sampler_name in {"traceidratio", "parentbased_traceidratio"}:
            raw_rate = os.environ.get("OTEL_TRACES_SAMPLER_ARG")
    if raw_rate is None:
        return None

    try:
        rate = float(raw_rate)
    except ValueError:
        logger.warning("otel_invalid_sample_rate", sample_rate=raw_rate)
        return None

    rate = max(0.0, min(rate, 1.0))
    return ParentBased(TraceIdRatioBased(rate))


def _service_name() -> str:
    return os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
