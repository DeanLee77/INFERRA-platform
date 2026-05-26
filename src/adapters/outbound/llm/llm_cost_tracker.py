import threading
from dataclasses import dataclass
from typing import Dict, Optional

import structlog

log = structlog.get_logger(__name__)


MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-3.5-turbo": {"prompt_per_1k": 0.0005, "completion_per_1k": 0.0015},
    "gpt-4": {"prompt_per_1k": 0.03, "completion_per_1k": 0.06},
    "gpt-4-turbo": {"prompt_per_1k": 0.01, "completion_per_1k": 0.03},
    "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002},
}


@dataclass
class CostRecord:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost_usd: float = 0.0
    request_count: int = 0


class LLMCostTracker:
    """Thread-safe in-memory LLM cost tracker."""

    def __init__(self, budget_usd: Optional[float] = None) -> None:
        self._costs: Dict[str, CostRecord] = {}
        self._lock = threading.Lock()
        self._budget_usd = budget_usd
        self._total_cost_usd = 0.0

    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        session_id: str = "",
        operation: str = "",
        correlation_id: str = "",
    ) -> float:
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
        cost = (
            (max(prompt_tokens, 0) / 1000.0) * pricing["prompt_per_1k"]
            + (max(completion_tokens, 0) / 1000.0) * pricing["completion_per_1k"]
        )
        with self._lock:
            self._total_cost_usd += cost
            record = self._costs.setdefault(model, CostRecord())
            record.prompt_tokens += max(prompt_tokens, 0)
            record.completion_tokens += max(completion_tokens, 0)
            record.total_cost_usd += cost
            record.request_count += 1
            total_cost = self._total_cost_usd

        if self._budget_usd is not None and total_cost > self._budget_usd:
            log.warning(
                "llm_budget_exceeded",
                session_id=session_id,
                node_id="",
                fact_source="",
                correlation_id=correlation_id,
                operation=operation,
                total_cost_usd=round(total_cost, 6),
                budget_usd=self._budget_usd,
            )
        log.info(
            "llm_cost_recorded",
            session_id=session_id,
            node_id="",
            fact_source="",
            correlation_id=correlation_id,
            operation=operation,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(cost, 6),
        )
        return cost

    def get_cost_summary(self) -> dict:
        with self._lock:
            by_model = {
                model: {
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "total_cost_usd": round(record.total_cost_usd, 6),
                    "request_count": record.request_count,
                }
                for model, record in self._costs.items()
            }
            return {
                "total_cost_usd": round(self._total_cost_usd, 6),
                "budget_usd": self._budget_usd,
                "budget_remaining_usd": (
                    round(self._budget_usd - self._total_cost_usd, 6)
                    if self._budget_usd is not None
                    else None
                ),
                "budget_exceeded": (
                    self._budget_usd is not None and self._total_cost_usd > self._budget_usd
                ),
                "by_model": by_model,
            }

    def reset(self) -> None:
        with self._lock:
            self._costs.clear()
            self._total_cost_usd = 0.0


llm_cost_tracker = LLMCostTracker()
