from typing import Any, Dict, List

from src.domain.reasoning.hypothesis import Hypothesis
from src.ports.abduction_port import AbductionPort


class MockAbductionAdapter(AbductionPort):
    """Deterministic abduction adapter for tests and demos."""

    def __init__(self, hypotheses: list[Hypothesis] | None = None) -> None:
        self._hypotheses = hypotheses or [
            Hypothesis(
                fact_name="mock_fact",
                suggested_value="true",
                confidence=0.85,
                dependency_path=["mock_fact"],
            )
        ]

    def propose_hypotheses(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return [hypothesis.to_dict() for hypothesis in self._hypotheses]
