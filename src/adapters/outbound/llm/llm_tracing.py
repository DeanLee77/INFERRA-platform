import re
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

_PII_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
)


def _sanitize_pii(text: str) -> str:
    sanitized = str(text)
    for pattern in _PII_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


@dataclass(frozen=True)
class LLMTraceRecord:
    trace_id: str
    operation: str
    model: str
    provider: str
    prompt: str
    response: str
    latency_ms: float
    status: str
    timestamp: float = field(default_factory=time.time)


class LLMTracer:
    """Short-retention, PII-sanitized LLM prompt/response trace store."""

    def __init__(self, max_traces: int = 1000, retention_seconds: int = 3600) -> None:
        self._traces: List[LLMTraceRecord] = []
        self._lock = threading.Lock()
        self._max_traces = max_traces
        self._retention_seconds = retention_seconds

    def record(
        self,
        *,
        trace_id: str,
        operation: str,
        model: str,
        provider: str,
        prompt: str,
        response: str,
        latency_ms: float,
        status: str = "success",
    ) -> None:
        record = LLMTraceRecord(
            trace_id=trace_id,
            operation=operation,
            model=model,
            provider=provider,
            prompt=_sanitize_pii(prompt),
            response=_sanitize_pii(response),
            latency_ms=latency_ms,
            status=status,
        )
        with self._lock:
            self._purge_expired_locked()
            self._traces.append(record)
            if len(self._traces) > self._max_traces:
                self._traces = self._traces[-self._max_traces:]

    def get_traces(self, operation: Optional[str] = None, limit: int = 100) -> List[dict]:
        with self._lock:
            self._purge_expired_locked()
            traces = list(self._traces)
        if operation:
            traces = [trace for trace in traces if trace.operation == operation]
        return [
            {
                "trace_id": trace.trace_id,
                "operation": trace.operation,
                "model": trace.model,
                "provider": trace.provider,
                "prompt": trace.prompt,
                "response": trace.response,
                "latency_ms": trace.latency_ms,
                "status": trace.status,
                "timestamp": trace.timestamp,
            }
            for trace in traces[-limit:]
        ]

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()

    def _purge_expired_locked(self) -> None:
        cutoff = time.time() - self._retention_seconds
        self._traces = [trace for trace in self._traces if trace.timestamp >= cutoff]


llm_tracer = LLMTracer()
