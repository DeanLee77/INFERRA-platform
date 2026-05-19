"""
Question Resolver Module.
Decides whether a node should be surfaced as a user question in INFERRA analysis.
Implements access levels and strong typing where appropriate.
"""

from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Set
from src.domain.fact_values import FactValue
from src.domain.nodes.line_type import LineType
from src.domain.nodes.meta_type import MetaType
from src.domain.nodes.node import Node
from src.domain.nodes.metadata_line import MetadataLine


class QuestionResolver:
    """
    QuestionResolver decides whether a node should be surfaced as a user question.
    The resolver is intentionally conservative: it only marks node types that
    INFERRA currently asks directly and leaves derived nodes alone.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, ask_callback: Callable[[Node], Optional[FactValue]]):
        """
        Public Constructor: Initializes QuestionResolver with callback.
        
        Args:
            ask_callback: Function to call when asking user for input
        """
        self.__ask_callback: Callable[[Node], Optional[FactValue]] = ask_callback

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    def find_next_question_node(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        visited: Optional[Set[str]] = None,
        has_children: bool = False,
    ) -> Optional[Node]:
        """
        Public API: Returns the node when it still requires direct user input, else None.
        
        Args:
            node: The node to evaluate
            working_memory: Current working memory dictionary
            visited: Set of already visited node names
            has_children: Whether the node has child nodes
            
        Returns:
            Node if it requires user input, None otherwise
        """
        if visited is None:
            visited = set()

        node_name = node.get_node_name()
        if node_name in visited:
            return None
        visited.add(node_name)

        if self._requires_user_input(node, working_memory, has_children):
            return node

        return None

    def resolve_answer(self, node: Node) -> Optional[FactValue]:
        """
        Public API: Call the injected asker (UI, session, or test double).
        
        Args:
            node: The node to resolve answer for
            
        Returns:
            FactValue from the callback or None
        """
        return self.__ask_callback(node)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _requires_user_input(
        self,
        node: Node,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        """
        Protected Helper: Core decision logic for whether a node should prompt the user.
        
        Args:
            node: The node to evaluate
            working_memory: Current working memory dictionary
            has_children: Whether the node has child nodes
            
        Returns:
            True if user input is required, False otherwise
        """
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
