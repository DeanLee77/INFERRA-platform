from dataclasses import asdict
from typing import Any, Dict, Optional

from src.domain.llm.goal_mapping import GoalMapping
from src.ports.llm_orchestrator_port import LLMOrchestratorPort


class MockLLMOrchestrator(LLMOrchestratorPort):
    """Deterministic test adapter for LLM-assisted flows."""

    def __init__(
        self,
        goal_mapping: GoalMapping | None = None,
        explanation: str = "Mock explanation",
    ) -> None:
        self._goal_mapping = goal_mapping or GoalMapping(
            node_name="mock_goal",
            confidence=0.95,
            fallback=False,
            prompt_version="mock",
        )
        self._explanation = explanation

    def map_nl_to_goal(self, user_query: str, rule_name: str) -> Dict[str, Any]:
        return asdict(self._goal_mapping)

    def enhance_question_prompt(
        self,
        node_name: str,
        variable_name: str,
        ontology_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        return f"Please provide {variable_name}"

    def generate_explanation(
        self,
        trace_content: str,
        trace_format: str = "turtle",
        session_id: str = "",
    ) -> str:
        return self._explanation
