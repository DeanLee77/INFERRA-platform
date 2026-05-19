import json
import hashlib
import time
from typing import Any, Callable, Dict, Optional

import structlog

from src.adapters.outbound.llm.client import LLMClient
from src.adapters.outbound.llm.llm_cost_tracker import llm_cost_tracker
from src.adapters.outbound.llm.llm_metrics import llm_metrics
from src.adapters.outbound.llm.llm_prompt_sanitizer import LLMPromptSanitizer
from src.adapters.outbound.llm.llm_tracing import llm_tracer
from src.config import settings
from src.ports.llm_orchestrator_port import LLMOrchestratorPort

log = structlog.get_logger(__name__)


class LLMCircuitOpenError(RuntimeError):
    """Raised when LLM calls are temporarily blocked by the circuit breaker."""


class LLMCircuitBreaker:
    """Small in-process circuit breaker for the optional LLM dependency."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock if clock is not None else time.monotonic
        self.failure_count = 0
        self.opened_at: Optional[float] = None
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open" and self.opened_at is not None:
            if self._clock() - self.opened_at >= self.recovery_timeout:
                self._state = "half_open"
        return self._state

    def before_call(self) -> None:
        if self.state == "open":
            raise LLMCircuitOpenError("LLM circuit is open")

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None
        self._state = "closed"

    def record_failure(self) -> None:
        self.failure_count += 1
        if self._state == "half_open" or self.failure_count >= self.failure_threshold:
            self._state = "open"
            self.opened_at = self._clock()


_default_llm_circuit = LLMCircuitBreaker(
    failure_threshold=settings.LLM_CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=settings.LLM_CIRCUIT_RECOVERY_TIMEOUT_SECONDS,
)


def reset_default_llm_circuit() -> None:
    """Reset the shared LLM circuit breaker for tests and singleton resets."""
    global _default_llm_circuit
    _default_llm_circuit = LLMCircuitBreaker(
        failure_threshold=settings.LLM_CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout=settings.LLM_CIRCUIT_RECOVERY_TIMEOUT_SECONDS,
    )


class RealLLMOrchestrator(LLMOrchestratorPort):
    """OpenAI-compatible LLM orchestrator with sanitization and safe fallback."""

    PROMPT_VERSION = "llm-orchestrator-v1"

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        *,
        max_retries: Optional[int] = None,
        retry_backoff_seconds: Optional[float] = None,
        circuit_breaker: Optional[LLMCircuitBreaker] = None,
    ) -> None:
        self._llm = llm_client if llm_client is not None else LLMClient()
        self._max_retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
        self._retry_backoff_seconds = (
            settings.LLM_RETRY_BACKOFF_SECONDS
            if retry_backoff_seconds is None
            else retry_backoff_seconds
        )
        self._circuit = circuit_breaker if circuit_breaker is not None else _default_llm_circuit

    def map_nl_to_goal(self, user_query: str, rule_name: str) -> Dict[str, Any]:
        query = LLMPromptSanitizer.sanitize(user_query)
        if not self._configured:
            return self._fallback_goal("LLM client is not configured")
        prompt = (
            "Map the user query to one INFERRA goal node. "
            "Return compact JSON with node_name, confidence, fallback, message.\n"
            f"Rule: {rule_name}\nQuery: {query}"
        )
        try:
            content = self._complete(prompt, operation="goal_mapping", rule_name=rule_name)
            payload = json.loads(content)
            return {
                "node_name": payload.get("node_name"),
                "confidence": float(payload.get("confidence", 0.0)),
                "fallback": bool(payload.get("fallback", False)),
                "message": str(payload.get("message", "")),
                "prompt_version": self.PROMPT_VERSION,
            }
        except Exception as exc:
            log.warning(
                "llm_goal_mapping_fallback",
                session_id="",
                node_id="",
                fact_source="",
                correlation_id="",
                rule_name=rule_name,
                error=str(exc),
            )
            return self._fallback_goal("LLM goal mapping failed")

    def enhance_question_prompt(
        self,
        node_name: str,
        variable_name: str,
        ontology_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self._configured:
            return variable_name or node_name
        prompt = (
            "Rewrite this INFERRA question for an end user. "
            "Return only the question text.\n"
            f"Node: {node_name}\nVariable: {variable_name}\n"
            f"Ontology context: {json.dumps(ontology_context or {}, sort_keys=True)}"
        )
        try:
            return self._complete(
                prompt,
                operation="question_prompt",
                rule_name=node_name,
            ).strip() or (variable_name or node_name)
        except Exception:
            return variable_name or node_name

    def generate_explanation(
        self,
        trace_content: str,
        trace_format: str = "turtle",
        session_id: str = "",
    ) -> str:
        if not self._configured:
            return trace_content
        prompt = (
            "Explain this INFERRA PROV-O trace in plain language. "
            "Stay grounded in the trace.\n"
            f"Format: {trace_format}\nTrace:\n{trace_content[:6000]}"
        )
        try:
            return self._complete(
                prompt,
                operation="trace_explanation",
                session_id=session_id,
            ).strip() or trace_content
        except Exception:
            return trace_content

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        operation: str = "chat",
        session_id: str = "",
        rule_name: str = "",
    ) -> str:
        """Generic guarded chat call for adapter-level LLM features."""
        if not self._configured:
            return ""
        prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
        return self._complete(
            prompt,
            operation=operation,
            session_id=session_id,
            rule_name=rule_name,
        )

    @property
    def _configured(self) -> bool:
        return self._llm.client is not None and bool(self._llm.model)

    def _complete(
        self,
        prompt: str,
        *,
        operation: str = "unknown",
        session_id: str = "",
        rule_name: str = "",
    ) -> str:
        last_error: Optional[BaseException] = None
        attempts = max(0, self._max_retries) + 1
        for attempt in range(attempts):
            self._circuit.before_call()
            start = time.perf_counter()
            try:
                response = self._llm.client.chat.completions.create(
                    model=self._llm.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    timeout=self._llm.timeout,
                )
                content = response.choices[0].message.content or ""
                latency_ms = (time.perf_counter() - start) * 1000
                self._record_llm_success(
                    operation=operation,
                    session_id=session_id,
                    rule_name=rule_name,
                    prompt=prompt,
                    response=response,
                    content=content,
                    latency_ms=latency_ms,
                )
                self._circuit.record_success()
                return content
            except Exception as exc:
                last_error = exc
                self._circuit.record_failure()
                latency_ms = (time.perf_counter() - start) * 1000
                self._record_llm_failure(
                    operation=operation,
                    session_id=session_id,
                    rule_name=rule_name,
                    prompt=prompt,
                    error=str(exc),
                    latency_ms=latency_ms,
                )
                log.warning(
                    "llm_call_failed",
                    session_id=session_id,
                    node_id="",
                    fact_source="",
                    correlation_id=session_id,
                    rule_name=rule_name,
                    operation=operation,
                    attempt=attempt + 1,
                    max_attempts=attempts,
                    circuit_state=self._circuit.state,
                    error=str(exc),
                )
                if attempt + 1 >= attempts or self._circuit.state == "open":
                    break
                if self._retry_backoff_seconds > 0:
                    time.sleep(self._retry_backoff_seconds * (2**attempt))
        if last_error is not None:
            raise last_error
        raise LLMCircuitOpenError("LLM circuit is open")

    def _record_llm_success(
        self,
        *,
        operation: str,
        session_id: str,
        rule_name: str,
        prompt: str,
        response: Any,
        content: str,
        latency_ms: float,
    ) -> None:
        model = str(self._llm.model or "unknown")
        prompt_tokens, completion_tokens = self._usage_counts(response)
        cost = llm_cost_tracker.record(
            model,
            prompt_tokens,
            completion_tokens,
            session_id=session_id,
            operation=operation,
            correlation_id=session_id,
        )
        llm_metrics.record(
            operation=operation,
            model=model,
            provider=self._provider_name(),
            status="success",
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        )
        llm_tracer.record(
            trace_id=self._trace_id(operation, prompt, session_id),
            operation=operation,
            model=model,
            provider=self._provider_name(),
            prompt=prompt,
            response=content,
            latency_ms=latency_ms,
            status="success",
        )

    def _record_llm_failure(
        self,
        *,
        operation: str,
        session_id: str,
        rule_name: str,
        prompt: str,
        error: str,
        latency_ms: float,
    ) -> None:
        model = str(self._llm.model or "unknown")
        llm_metrics.record(
            operation=operation,
            model=model,
            provider=self._provider_name(),
            status="failure",
            latency_ms=latency_ms,
        )
        llm_tracer.record(
            trace_id=self._trace_id(operation, prompt, session_id),
            operation=operation,
            model=model,
            provider=self._provider_name(),
            prompt=prompt,
            response=error,
            latency_ms=latency_ms,
            status="failure",
        )

    @staticmethod
    def _usage_counts(response: Any) -> tuple[int, int]:
        usage = getattr(response, "usage", None)
        return (
            RealLLMOrchestrator._int_or_zero(getattr(usage, "prompt_tokens", 0)),
            RealLLMOrchestrator._int_or_zero(getattr(usage, "completion_tokens", 0)),
        )

    @staticmethod
    def _int_or_zero(value: Any) -> int:
        return value if isinstance(value, int) and value >= 0 else 0

    @staticmethod
    def _trace_id(operation: str, prompt: str, session_id: str) -> str:
        payload = f"{operation}:{session_id}:{prompt[:200]}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _provider_name(self) -> str:
        provider_id = getattr(self._llm, "provider_id", None)
        return str(provider_id or "openai-compatible")

    def _fallback_goal(self, message: str) -> Dict[str, Any]:
        return {
            "node_name": None,
            "confidence": 0.0,
            "fallback": True,
            "message": message,
            "prompt_version": self.PROMPT_VERSION,
        }
