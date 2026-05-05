from typing import Any, Dict, Iterable, Optional

from src.domain.inference.question_resolver import QuestionResolver
from src.domain.nodes.node import Node
from src.ports.question_strategy_port import QuestionStrategyPort


def _noop_question_callback(_: object) -> None:
    return None


class ConservativeQuestionStrategy(QuestionStrategyPort):
    """
    Zero-behaviour-change question strategy.

    This wraps the existing QuestionResolver decision rules behind a port so
    ontology- or LLM-enhanced strategies can be introduced without touching the
    inference engine.
    """

    def __init__(self) -> None:
        self._resolver = QuestionResolver(_noop_question_callback)

    def should_ask(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        return self._resolver._requires_user_input(
            node,
            working_memory,
            has_children=has_children,
        )

    def select_next(
        self,
        candidates: Iterable[Node],
        working_memory: Dict[str, Any],
        has_children_by_name: Optional[Dict[str, bool]] = None,
    ) -> Optional[Node]:
        children_map = has_children_by_name or {}
        for node in candidates:
            has_children = children_map.get(node.get_node_name(), False)
            if self.should_ask(node, working_memory, has_children=has_children):
                return node
        return None
