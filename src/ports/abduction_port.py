from abc import ABCMeta, abstractmethod
from typing import Any, Dict, List


class AbductionPort(metaclass=ABCMeta):
    """Port contract for diagnostic hypothesis generation."""

    @abstractmethod
    def propose_hypotheses(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        pass  # pragma: no cover
