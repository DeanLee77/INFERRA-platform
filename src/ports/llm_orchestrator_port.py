from abc import ABCMeta, abstractmethod
from typing import Any, Dict, Optional


class LLMOrchestratorPort(metaclass=ABCMeta):
    """Port contract for optional LLM-assisted UX and explanation features."""

    @abstractmethod
    def map_nl_to_goal(self, user_query: str, rule_name: str) -> Dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def enhance_question_prompt(
        self,
        node_name: str,
        variable_name: str,
        ontology_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        pass  # pragma: no cover

    @abstractmethod
    def generate_explanation(
        self,
        trace_content: str,
        trace_format: str = "turtle",
        session_id: str = "",
    ) -> str:
        pass  # pragma: no cover
