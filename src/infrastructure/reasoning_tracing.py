from contextlib import contextmanager
from typing import Any, Dict, Iterator


@contextmanager
def reasoning_span(name: str, attributes: Dict[str, Any] | None = None) -> Iterator[None]:
    """Start a reasoning OTel span when tracing is installed; otherwise no-op."""
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("inferra.reasoning")
    except Exception:
        yield
        return

    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        yield
