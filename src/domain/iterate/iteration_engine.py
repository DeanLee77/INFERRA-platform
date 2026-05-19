"""
Iteration Engine Module.

Port-compliant iteration engine with thread-safety and truth-maintenance.
Replaces the nested InferenceEngine anti-pattern in IterateLine.

Concurrency model: sessions are single-threaded by design; asyncio.Lock
provides a safety net for async frameworks that may interleave coroutines.

Routes facts through the parent LayeredFactStore with FactSource.INFERRED
tagging. Respects truth-maintenance: ASSERTED wins over INFERRED.
"""

import asyncio
from typing import Any, Optional, Tuple

import structlog

from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes.iterate_context import IterateContext
from src.domain.state.fact_source import FactSource
from src.ports.fact_store_port import FactStorePort
from src.ports.iteration_port import IterationPort

log = structlog.get_logger()


class IterationEngine(IterationPort):
    """
    Port-compliant iteration engine with thread-safety and truth-maintenance.

    Implements the IterationPort lifecycle:
    initialise() → record_answer() → evaluate() → get_progress()

    Concurrency model: sessions are single-threaded by design; asyncio.Lock
    provides a safety net for async frameworks that may interleave coroutines.
    """

    def __init__(self, fact_store: FactStorePort):
        self._store = fact_store
        self._ctx: Optional[IterateContext] = None
        self._lock: asyncio.Lock = asyncio.Lock()

    def initialise(self, list_size: int, quantifier: str, list_name: str) -> None:
        """
        Initialise or reinitialise the iteration context.

        If a context already exists with the same list parameters, this is a no-op.

        Args:
            list_size: Number of items in the iterate list
            quantifier: Quantifier string (ALL / NONE / SOME / N)
            list_name: Name of the iterate list
        """
        if (
            self._ctx is not None
            and self._ctx.list_size == list_size
            and self._ctx.quantifier == quantifier
            and self._ctx.list_name == list_name
        ):
            return
        self._ctx = IterateContext(
            list_name=list_name,
            list_size=list_size,
            quantifier=quantifier,
        )
        log.info(
            "iterate_context_initialised",
            list_name=list_name,
            list_size=list_size,
            quantifier=quantifier,
        )

    async def record_answer(
        self,
        index: int,
        question_name: str,
        value: Any,
        node_value_type: FactValueType,
    ) -> bool:
        """
        Thread-safe answer recording.

        Uses per-engine lock to prevent data races. Routes through
        FactStorePort without metadata kwarg (Phase 1 contract compliance).

        Truth-maintenance: checks if fact is already ASSERTED — if so,
        the INFERRED write is skipped (ASSERTED wins).

        Args:
            index: Ordinal index of the item (1-based)
            question_name: Name of the question being answered
            value: Value from user
            node_value_type: Type of the value

        Returns:
            True if all list items have been answered, False otherwise
        """
        if self._ctx is None:
            raise RuntimeError("IterationEngine not initialised — call initialise() first")

        if len(self._ctx.progress) >= self._ctx.list_size:
            return True

        async with self._lock:
            sources = self._store.get_fact_sources(question_name)
            if FactSource.ASSERTED in sources:
                log.info(
                    "iterate_answer_asserted_override",
                    question_name=question_name,
                )
                is_true = self._coerce_bool(value, node_value_type)
                self._ctx.progress[index] = is_true
                return len(self._ctx.progress) == self._ctx.list_size

            is_true = self._coerce_bool(value, node_value_type)
            self._ctx.progress[index] = is_true
            self._store.set_fact(
                question_name, FactValue(is_true), source=FactSource.INFERRED
            )
            log.info(
                "iterate_answer_recorded",
                question_name=question_name,
                index=index,
                is_true=is_true,
            )
            return len(self._ctx.progress) == self._ctx.list_size

    def evaluate(self) -> FactValue:
        """
        Evaluate the iterate quantifier against current progress.

        Returns:
            FactValue result based on quantifier and progress

        Raises:
            RuntimeError: If called before context is initialised or
                before all items have been answered
        """
        if self._ctx is None:
            raise RuntimeError("IterationEngine not initialised — call initialise() first")
        if len(self._ctx.progress) < self._ctx.list_size:
            raise RuntimeError(
                f"Cannot evaluate — only {len(self._ctx.progress)}/{self._ctx.list_size} "
                f"items answered"
            )

        true_count = sum(1 for v in self._ctx.progress.values() if v)
        result = self._evaluate_quantifier(true_count, self._ctx.list_size, self._ctx.quantifier)
        log.info(
            "iterate_completed",
            quantifier=self._ctx.quantifier,
            true_count=true_count,
            list_size=self._ctx.list_size,
        )
        return result

    def get_progress(self) -> Tuple[int, int]:
        """
        Return iterate progress as (answered_count, total_list_size).

        Returns:
            Tuple of (number of items answered, total list size)
        """
        if self._ctx is None:
            return (0, 0)
        return (len(self._ctx.progress), self._ctx.list_size)

    def reset_iterate_context(self) -> None:
        """
        Reset iteration state for re-evaluation.

        Clears INFERRED facts via truth-maintenance (invalidate_layer)
        and reinitialises the IterateContext with the same parameters.
        No-op if no context exists.
        """
        if self._ctx is None:
            return
        self._store.invalidate_layer(FactSource.INFERRED)
        self._ctx = IterateContext(
            list_name=self._ctx.list_name,
            list_size=self._ctx.list_size,
            quantifier=self._ctx.quantifier,
        )
        log.info("iterate_context_reset", list_name=self._ctx.list_name)

    @staticmethod
    def _coerce_bool(value: Any, node_value_type: FactValueType) -> bool:
        """
        Coerce a value to boolean based on its declared type.

        Args:
            value: Raw value from user
            node_value_type: Declared type of the value

        Returns:
            Boolean interpretation of the value
        """
        if node_value_type == FactValueType.BOOLEAN:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() == "true"
            return bool(value)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return bool(value)

    @staticmethod
    def _evaluate_quantifier(
        true_count: int, list_size: int, quantifier: str
    ) -> FactValue:
        """
        Evaluate a quantifier against a true count and list size.

        Args:
            true_count: Number of items that evaluated to True
            list_size: Total number of items
            quantifier: Quantifier string (ALL / NONE / SOME / N)

        Returns:
            FactValue with the boolean result
        """
        if quantifier == "ALL":
            return FactValue(true_count == list_size)
        if quantifier == "NONE":
            return FactValue(true_count == 0)
        if quantifier == "SOME":
            return FactValue(true_count > 0)
        try:
            return FactValue(true_count == int(quantifier))
        except (ValueError, TypeError):
            return FactValue(False)
