import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class LLMRequestMetric:
    operation: str
    model: str
    provider: str
    status: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)


class LLMMetricsCollector:
    """Bounded in-memory summary of recent LLM requests."""

    def __init__(self, max_history: int = 10000) -> None:
        self._metrics: List[LLMRequestMetric] = []
        self._lock = threading.Lock()
        self._max_history = max_history

    def record(
        self,
        *,
        operation: str,
        model: str,
        provider: str,
        status: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        metric = LLMRequestMetric(
            operation=operation,
            model=model,
            provider=provider,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        with self._lock:
            self._metrics.append(metric)
            if len(self._metrics) > self._max_history:
                self._metrics = self._metrics[-self._max_history:]

    def get_summary(self) -> dict:
        with self._lock:
            metrics = list(self._metrics)
        if not metrics:
            return {
                "total_requests": 0,
                "by_operation": {},
                "by_status": {},
                "avg_latency_ms": 0.0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_cost_usd": 0.0,
            }

        by_operation: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        total_latency = 0.0
        total_prompt = 0
        total_completion = 0
        total_cost = 0.0
        for metric in metrics:
            by_operation[metric.operation] = by_operation.get(metric.operation, 0) + 1
            by_status[metric.status] = by_status.get(metric.status, 0) + 1
            total_latency += metric.latency_ms
            total_prompt += metric.prompt_tokens
            total_completion += metric.completion_tokens
            total_cost += metric.cost_usd
        return {
            "total_requests": len(metrics),
            "by_operation": by_operation,
            "by_status": by_status,
            "avg_latency_ms": round(total_latency / len(metrics), 2),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_cost_usd": round(total_cost, 6),
        }

    def clear(self) -> None:
        with self._lock:
            self._metrics.clear()


llm_metrics = LLMMetricsCollector()
