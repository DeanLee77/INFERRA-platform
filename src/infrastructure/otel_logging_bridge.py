from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

log = structlog.get_logger(__name__)

try:
    from opentelemetry import trace

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    trace = None
    OTEL_AVAILABLE = False


def add_otel_context(
    logger: Any,
    method_name: str,
    event_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Structlog processor that attaches current OTel trace/span ids."""
    context = current_span_context()
    if context is None:
        return event_dict
    trace_id = _hex_id(getattr(context, "trace_id", 0), 32)
    span_id = _hex_id(getattr(context, "span_id", 0), 16)
    if trace_id and span_id:
        event_dict.setdefault("trace_id", trace_id)
        event_dict.setdefault("span_id", span_id)
        trace_flags = getattr(context, "trace_flags", None)
        if trace_flags is not None:
            event_dict.setdefault("trace_flags", _format_trace_flags(trace_flags))
    return event_dict


def current_span_context() -> Optional[Any]:
    if not OTEL_AVAILABLE or trace is None:
        return None
    try:
        span = trace.get_current_span()
        context = span.get_span_context()
    except Exception:
        return None
    if not _context_is_valid(context):
        return None
    return context


def _context_is_valid(context: Any) -> bool:
    is_valid = getattr(context, "is_valid", None)
    if isinstance(is_valid, bool):
        return is_valid
    try:
        return int(getattr(context, "trace_id", 0)) != 0 and int(getattr(context, "span_id", 0)) != 0
    except (TypeError, ValueError):
        return False


def _hex_id(value: Any, width: int) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return f"{number:0{width}x}"[-width:]


def _format_trace_flags(value: Any) -> str:
    try:
        return f"{int(value):02x}"
    except (TypeError, ValueError):
        return str(value)

