from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.infrastructure import otel_logging_bridge
from src.infrastructure.otel_logging_bridge import (
    _format_trace_flags,
    _hex_id,
    add_otel_context,
    current_span_context,
)


def test_add_otel_context_noops_when_otel_unavailable():
    with patch.object(otel_logging_bridge, "OTEL_AVAILABLE", False):
        event = {"event": "x"}

        assert add_otel_context(None, "info", event) is event
        assert event == {"event": "x"}


def test_add_otel_context_attaches_current_span_ids():
    context = SimpleNamespace(
        trace_id=0x123,
        span_id=0x45,
        trace_flags=1,
        is_valid=True,
    )
    span = MagicMock()
    span.get_span_context.return_value = context
    trace_module = MagicMock()
    trace_module.get_current_span.return_value = span

    with patch.object(otel_logging_bridge, "OTEL_AVAILABLE", True):
        with patch.object(otel_logging_bridge, "trace", trace_module):
            event = add_otel_context(None, "info", {})

    assert event["trace_id"].endswith("123")
    assert event["span_id"].endswith("45")
    assert event["trace_flags"] == "01"


def test_current_span_context_rejects_invalid_or_failing_contexts():
    span = MagicMock()
    span.get_span_context.return_value = SimpleNamespace(trace_id=0, span_id=0, is_valid=False)
    trace_module = MagicMock()
    trace_module.get_current_span.return_value = span

    with patch.object(otel_logging_bridge, "OTEL_AVAILABLE", True):
        with patch.object(otel_logging_bridge, "trace", trace_module):
            assert current_span_context() is None

    trace_module.get_current_span.side_effect = RuntimeError("no context")
    with patch.object(otel_logging_bridge, "OTEL_AVAILABLE", True):
        with patch.object(otel_logging_bridge, "trace", trace_module):
            assert current_span_context() is None


def test_trace_id_format_helpers_are_defensive():
    assert _hex_id(1, 4) == "0001"
    assert _hex_id("bad", 4) == ""
    assert _format_trace_flags(1) == "01"
    assert _format_trace_flags("sampled") == "sampled"

