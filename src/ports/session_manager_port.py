from abc import ABCMeta, abstractmethod
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.session.inference_context import InferenceContext
    from src.domain.session.session_manager import ConvergenceResult


class SessionManagerPort(metaclass=ABCMeta):
    """Port contract for session lifecycle snapshots and convergence checks."""

    @abstractmethod
    def create_snapshot(self, session_id: str, ctx: "InferenceContext") -> None:
        pass  # pragma: no cover

    @abstractmethod
    def get_snapshot(self, session_id: str) -> Optional["InferenceContext"]:
        pass  # pragma: no cover

    @abstractmethod
    def check_convergence(
        self,
        session_id: str,
        goal: Optional[str] = None,
        mandatory: Optional[List[str]] = None,
    ) -> "ConvergenceResult":
        pass  # pragma: no cover

    @abstractmethod
    def get_wm_hash(self, session_id: str) -> str:
        pass  # pragma: no cover

    @abstractmethod
    def get_ontology_delta(self, session_id: str) -> int:
        pass  # pragma: no cover

    @abstractmethod
    def remove_snapshot(self, session_id: str) -> None:
        pass  # pragma: no cover
