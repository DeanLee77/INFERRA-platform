from abc import ABCMeta, abstractmethod
from typing import Any, Dict, Iterable, Optional


class QuestionStrategyPort(metaclass=ABCMeta):
    """Port contract for pluggable question selection."""

    @abstractmethod
    def should_ask(
        self,
        node: Any,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def select_next(
        self,
        candidates: Iterable[Any],
        working_memory: Dict[str, Any],
        has_children_by_name: Optional[Dict[str, bool]] = None,
    ) -> Optional[Any]:
        pass  # pragma: no cover
