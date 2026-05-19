"""
Iteration Port Module.
Abstract interface for iteration evaluation.

Phase 2: Replaces the nested InferenceEngine anti-pattern in IterateLine
with a port-compliant IterationEngine that routes facts through the parent
LayeredFactStore with FactSource.INFERRED tagging and truth-maintenance.

Uses ABCMeta (not Protocol) consistent with DependencyGraphPort and
the project's port conventions.
"""

from abc import ABCMeta, abstractmethod
from typing import Any, Tuple

from src.domain.fact_values import FactValue, FactValueType


class IterationPort(metaclass=ABCMeta):
    """
    Abstract interface for iteration evaluation.

    Defines the contract for iterate lifecycle management:
    initialise → record_answer → evaluate → get_progress.

    Implementations must be thread-safe (asyncio.Lock) and respect
    truth-maintenance (ASSERTED wins over INFERRED).
    """

    @abstractmethod
    def initialise(self, list_size: int, quantifier: str, list_name: str) -> None:
        """
        Initialise or reinitialise the iteration context.

        If a context already exists with the same list_size, this is a no-op.

        Args:
            list_size: Number of items in the iterate list
            quantifier: Quantifier string (ALL / NONE / SOME / N)
            list_name: Name of the iterate list
        """
        pass  # pragma: no cover

    @abstractmethod
    async def record_answer(
        self,
        index: int,
        question_name: str,
        value: Any,
        node_value_type: FactValueType,
    ) -> bool:
        """
        Record an answer for an iterate item.

        Thread-safe: implementations must use an asyncio.Lock to prevent
        data races. Truth-maintenance: if the fact is already ASSERTED,
        the INFERRED write is skipped.

        Args:
            index: Ordinal index of the item (1-based)
            question_name: Name of the question being answered
            value: Value from user
            node_value_type: Type of the value

        Returns:
            True if all list items have been answered, False otherwise
        """
        pass  # pragma: no cover

    @abstractmethod
    def evaluate(self) -> FactValue:
        """
        Evaluate the iterate quantifier against current progress.

        Returns:
            FactValue result based on quantifier and progress

        Raises:
            RuntimeError: If called before context is initialised
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_progress(self) -> Tuple[int, int]:
        """
        Return iterate progress as (answered_count, total_list_size).

        Returns:
            Tuple of (number of items answered, total list size)
        """
        pass  # pragma: no cover

    @abstractmethod
    def reset_iterate_context(self) -> None:
        """
        Reset iteration state for re-evaluation.

        Clears INFERRED facts via truth-maintenance (invalidate_layer)
        and reinitialises the IterateContext with the same parameters.
        Must be a no-op if no context exists.
        """
        pass  # pragma: no cover
