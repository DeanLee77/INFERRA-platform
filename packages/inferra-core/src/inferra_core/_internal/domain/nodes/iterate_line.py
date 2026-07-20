"""Deterministic iterate syntax and quantifier node.

The Platform compatibility class still owns nested-engine orchestration while
fact-store/iteration extraction is pending.  This Core class intentionally
contains only parsing, explicit progress ingestion, and pure quantifier
evaluation.  An already-constructed ``IterationPort`` can be supplied by a
host; Core never constructs a Platform iteration engine or reads feature flags.
"""

import asyncio
import re
from typing import Any, Dict, Optional, Tuple

from inferra_core.ports import IterationPort
from inferra_core.values import FactValue, FactValueType

from inferra_core._internal.domain.nodes.iterate_context import IterateContext
from inferra_core._internal.domain.nodes.line_type import LineType
from inferra_core._internal.domain.nodes.meta_data import MetaData
from inferra_core._internal.domain.nodes.node import Node
from inferra_core._internal.domain.rule_parser.iterate_syntax import parse_iterate
from inferra_core._internal.domain.tokens import Token


class IterateLine(Node):
    """An iterate node whose state transitions depend only on explicit input."""

    def __init__(
        self,
        id: Optional[int] = None,
        parent_text: Optional[str] = None,
        tokens: Optional[Token] = None,
        meta_data: Optional[MetaData] = None,
        iteration_engine: Optional[IterationPort] = None,
    ) -> None:
        self.__number_of_target: Optional[str] = None
        self.__given_list_name: Optional[str] = None
        self.__context: Optional[IterateContext] = None
        self._iteration_engine = iteration_engine
        self._lock: Optional[asyncio.Lock] = None
        super().__init__(
            id=id,
            parent_text=parent_text,
            tokens=tokens,
            meta_data=meta_data,
        )
        self._line_type = LineType.ITERATE

    def get_given_list_name(self) -> Optional[str]:
        return self.__given_list_name

    def get_number_of_target(self) -> Optional[str]:
        return self.__number_of_target

    def get_iterate_node_set(self) -> None:
        """Return no nested NodeSet; nested execution is a Platform adapter."""
        return None

    def get_line_type(self) -> LineType:
        return LineType.ITERATE

    def set_iteration_engine(self, engine: Optional[IterationPort]) -> None:
        """Supply an explicit host-owned iteration collaborator."""
        self._iteration_engine = engine

    def initialise_progress(self, list_size: int) -> None:
        if list_size < 0:
            raise ValueError("list_size must be non-negative")
        self.__context = IterateContext(
            list_name=self.__given_list_name or "",
            list_size=list_size,
            quantifier=self.__number_of_target or "ALL",
            is_initialised=True,
        )

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def feed_iterate_answer(
        self,
        question_name: str,
        node_value: Any,
        node_value_type: FactValueType,
        *,
        iteration_engine: Optional[IterationPort] = None,
    ) -> bool:
        """Record an answer using explicit progress or an injected engine."""
        engine = iteration_engine or self._iteration_engine
        if engine is not None:
            return await engine.record_answer(
                self._extract_ordinal_index(question_name),
                question_name,
                node_value,
                node_value_type,
            )
        if self.__context is None:
            raise RuntimeError("initialise_progress() must be called first")

        async with self._get_lock():
            index = self._extract_ordinal_index(question_name)
            self.__context.progress[index] = self._truth_value(
                node_value,
                node_value_type,
            )
            return len(self.__context.progress) == self.__context.list_size

    def get_progress(self) -> Tuple[int, int]:
        if self._iteration_engine is not None:
            return self._iteration_engine.get_progress()
        if self.__context is None:
            return (0, 0)
        return (len(self.__context.progress), self.__context.list_size)

    def can_be_self_evaluated(self, working_memory: Dict[str, Any]) -> bool:
        del working_memory
        answered, total = self.get_progress()
        return answered == total and total > 0

    def self_evaluate(self, working_memory: Dict[str, Any]) -> FactValue:
        del working_memory
        if self._iteration_engine is not None:
            return self._iteration_engine.evaluate()
        if self.__context is None:
            return FactValue(False)
        true_count = sum(self.__context.progress.values())
        return self._evaluate_quantifier(true_count, self.__context.list_size)

    def _evaluate_quantifier(self, true_count: int, list_size: int) -> FactValue:
        quantifier = (self.__number_of_target or "ALL").strip().upper()
        if quantifier == "ALL":
            return FactValue(true_count == list_size)
        if quantifier == "NOT ALL":
            return FactValue(true_count != list_size)
        if quantifier == "NONE":
            return FactValue(true_count == 0)
        if quantifier in {"NOT NONE", "SOME"}:
            return FactValue(true_count > 0)

        exact = re.match(r"^EXACT(?:LY)?\s+(\d+)$", quantifier)
        if exact:
            return FactValue(true_count == int(exact.group(1)))
        at_least = re.match(r"^AT\s+LEAST\s+(\d+)$", quantifier)
        if at_least:
            return FactValue(true_count >= int(at_least.group(1)))
        at_most = re.match(r"^AT\s+MOST\s+(\d+)$", quantifier)
        if at_most:
            return FactValue(true_count <= int(at_most.group(1)))
        try:
            return FactValue(true_count >= int(quantifier))
        except ValueError:
            return FactValue(False)

    def _extract_ordinal_index(self, question_name: str) -> int:
        match = re.match(r"(\d+)", question_name.strip())
        if match:
            return int(match.group(1))
        if self.__context is not None:
            return len(self.__context.progress) + 1
        return 1

    @staticmethod
    def _truth_value(value: Any, value_type: FactValueType) -> bool:
        if value_type == FactValueType.BOOLEAN:
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return bool(value)

    def initialisation(self, parent_text: str, tokens: Token) -> None:
        self._node_name = parent_text
        parsed = parse_iterate(parent_text)
        if parsed is not None:
            quantifier, alias, list_name = parsed
            self.__number_of_target = quantifier
            self._variable_name = alias
            self.set_value("L", list_name)
            self.__given_list_name = list_name
            return

        token_values = tokens.get_tokens_list()
        token_types = tokens.get_tokens_string_list()
        if len(token_values) < 2:
            raise ValueError(f"Invalid iterate expression: {parent_text!r}")
        self.__number_of_target = token_values[0]
        self._variable_name = token_values[1]
        last_value = token_values[-1]
        last_type = token_types[-1] if token_types else "L"
        self.set_value(last_type, last_value)
        self.__given_list_name = last_value

