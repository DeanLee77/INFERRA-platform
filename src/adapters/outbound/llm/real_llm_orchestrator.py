import json
from typing import Any, Dict, Optional

import structlog

from src.adapters.outbound.llm.client import LLMClient
from src.adapters.outbound.llm.llm_prompt_sanitizer import LLMPromptSanitizer
from src.ports.llm_orchestrator_port import LLMOrchestratorPort

log = structlog.get_logger(__name__)


class RealLLMOrchestrator(LLMOrchestratorPort):
    """OpenAI-compatible LLM orchestrator with sanitization and safe fallback."""

    PROMPT_VERSION = "llm-orchestrator-v1"

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client if llm_client is not None else LLMClient()

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
            content = self._complete(prompt)
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
            return self._complete(prompt).strip() or (variable_name or node_name)
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
            return self._complete(prompt).strip() or trace_content
        except Exception:
            return trace_content

    @property
    def _configured(self) -> bool:
        return self._llm.client is not None and bool(self._llm.model)

    def _complete(self, prompt: str) -> str:
        response = self._llm.client.chat.completions.create(
            model=self._llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            timeout=self._llm.timeout,
        )
        return response.choices[0].message.content or ""

    def _fallback_goal(self, message: str) -> Dict[str, Any]:
        return {
            "node_name": None,
            "confidence": 0.0,
            "fallback": True,
            "message": message,
            "prompt_version": self.PROMPT_VERSION,
        }
