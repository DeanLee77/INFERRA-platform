"""
I Scan Feeder Interface Module.
Abstract interface for feeding scanned rule data to the parser.
Implements access levels and strong typing where appropriate.
"""

from abc import ABCMeta, abstractmethod
from typing import Any, Optional
from src.domain.nodes.meta_data import MetaData
from src.domain.nodes.meta_type import MetaType
from src.domain.nodes.node_set import NodeSet
from src.ports.dependency_graph_port import DependencyGraphPort


class IScanFeeder(metaclass=ABCMeta):
    """
    IScanFeeder abstract interface for feeding scanned rule data.
    
    Access Levels:
    - Public: Abstract API methods for implementation
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Public Access Level: Abstract API Methods
    # -------------------------------------------------------------------------
    @abstractmethod
    def handle_parent(self, parent_text: str, line_number: int, meta_data: MetaData) -> None:
        """
        Public API: Handles parent rule text.
        
        Args:
            parent_text: Parent rule text
            line_number: Line number in source file
            meta_data: Metadata for the rule
        """
        pass  # pragma: no cover

    @abstractmethod
    def handle_child(self, parent_text: str, child_text: str, 
                    first_keywords_group: str, line_number: int) -> None:
        """
        Public API: Handles child rule text.
        
        Args:
            parent_text: Parent rule text
            child_text: Child rule text
            first_keywords_group: First keywords group (AND, OR, etc.)
            line_number: Line number in source file
        """
        pass  # pragma: no cover

    @abstractmethod
    def handle_list_item(self, parent_text: str, item_text: str, meta_type: MetaType) -> None:
        """
        Public API: Handles list item text.
        
        Args:
            parent_text: Parent rule text
            item_text: List item text
            meta_type: Metadata type (INPUT, FIXED, etc.)
        """
        pass  # pragma: no cover

    @abstractmethod
    def handle_warning(self, parent_text: str) -> str:
        """
        Public API: Handles warning messages.
        
        Args:
            parent_text: Rule text that caused warning
            
        Returns:
            Warning message string
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_node_set(self) -> NodeSet:
        """
        Public API: Returns the node set.
        
        Returns:
            NodeSet object
        """
        pass  # pragma: no cover

    @abstractmethod
    def set_node_set(self, ns: NodeSet) -> None:
        """
        Public API: Sets the node set.
        
        Args:
            ns: NodeSet object to set
        """
        pass  # pragma: no cover

    def create_dependency_graph(self) -> DependencyGraphPort:
        """
        Public API: Creates the canonical dependency graph.

        Default implementation returns the graph stored on the NodeSet.
        Graph-first feeders should override this when they can build a more
        specific graph directly.

        Returns:
            DependencyGraphPort object
        """
        from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph

        node_set = self.get_node_set()
        graph = node_set.get_graph()
        if graph is not None:
            return graph

        graph = HyperAdjacencyGraph()
        node_set.set_graph(graph)
        return graph

    @abstractmethod
    def create_dependency_matrix(self) -> Any:
        """
        Public API: Creates a legacy dependency matrix compatibility view.
        
        Returns:
            Matrix-like object
        """
        pass  # pragma: no cover
