from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set

from project.fact_values import FactValue
from project.nodes import LineType, MetaType
from project.nodes.node import Node
from project.nodes.metadata_line import MetadataLine


class QuestionResolver:
    """
    Decide whether a node should be surfaced as a user question.

    The resolver is intentionally conservative: it only marks node types that
    PALOS currently asks directly and leaves derived nodes alone.
    """

    def __init__(self, ask_callback: Callable[[Node], Optional[FactValue]]):
        self.ask_callback = ask_callback

    def find_next_question_node(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        visited: Set[int] | None = None,
        has_children: bool = False,
    ) -> Optional[Node]:
        """
        Return the node when it still requires direct user input, else ``None``.
        """
        if visited is None:
            visited = set()

        node_id = node.get_node_id()
        if node_id in visited:
            return None
        visited.add(node_id)

        if self._requires_user_input(node, working_memory, has_children):
            return node

        return None

    def resolve_answer(self, node: Node) -> Optional[FactValue]:
        """Call the injected asker (UI, session, or test double)."""
        return self.ask_callback(node)

    def _requires_user_input(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        """Core decision logic for whether a node should prompt the user."""
        var_name = node.get_variable_name()
        node_name = node.get_node_name()

        if var_name in working_memory or node_name in working_memory:
            return False

        line_type = node.get_line_type()

        if line_type == LineType.META:
            if isinstance(node, MetadataLine):
                return node.get_meta_type() == MetaType.INPUT
            return False

        if line_type == LineType.ITERATE:
            return True

        if line_type == LineType.VALUE_CONCLUSION:
            return not has_children

        return False
