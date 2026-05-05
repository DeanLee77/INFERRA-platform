from abc import ABCMeta, abstractmethod
from typing import Any, Dict, Iterable


class InductionPort(metaclass=ABCMeta):
    """Port contract for trace-driven rule discovery workflows."""

    @abstractmethod
    def start_batch(self, session_ids: Iterable[str], rule_name: str) -> Dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def get_status(self, job_id: str) -> Dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def promote(self, job_id: str, candidate_rule: str) -> Dict[str, Any]:
        pass  # pragma: no cover
