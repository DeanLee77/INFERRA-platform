import structlog
from dataclasses import asdict
from typing import Any, Dict, Optional

from src.domain.llm.goal_mapping import GoalMapping
from src.ports.llm_orchestrator_port import LLMOrchestratorPort

log = structlog.get_logger(__name__)


class NullLLMOrchestrator(LLMOrchestratorPort):
    """No-network fallback used when LLM enhancements are disabled."""

    def map_nl_to_goal(self, user_query: str, rule_name: str) -> Dict[str, Any]:
        log.info(
            "llm_goal_mapping_fallback",
            rule_name=rule_name,
            session_id="",
            node_id="",
            fact_source="",
            correlation_id="",
        )
        return asdict(GoalMapping(
            node_name=None,
            confidence=0.0,
            fallback=True,
            message="LLM enhancements are disabled",
        ))

    def enhance_question_prompt(
        self,
        node_name: str,
        variable_name: str,
        ontology_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        return variable_name or node_name

    def generate_explanation(
        self,
        trace_content: str,
        trace_format: str = "turtle",
        session_id: str = "",
    ) -> str:
        return trace_content
