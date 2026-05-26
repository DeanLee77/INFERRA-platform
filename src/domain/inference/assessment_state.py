"""
Assessment State Class.
Manages the state during rule assessment in INFERRA analysis.
Implements access levels and strong typing where appropriate.
"""

from typing import Dict, List, Optional, Set
from src.domain.fact_values import FactValue, FactValueType
from src.domain.state import FactSource, LayeredFactStore
from src.ports.fact_store_port import FactStorePort
from src.infrastructure.logging_config import get_logger
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet

# Protected Module-Level Logger (Access Level: Protected)
_logger = get_logger(__name__)


class AssessmentState:
    """
    AssessmentState manages working memory and rule lists during assessment.
    Delegates layered fact storage to a LayeredFactStore (FactStorePort)
    while owning the assessment-specific lists (mandatory/inclusive/exclusive/summary).

    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """

    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, fact_store: Optional[FactStorePort] = None):
        """
        Public Constructor: Initializes AssessmentState.

        Args:
            fact_store: Optional FactStorePort implementation. Defaults to a
                fresh LayeredFactStore — injected for tests / alternate backends.
        """
        self.__fact_store: FactStorePort = fact_store if fact_store is not None else LayeredFactStore()
        self.__inclusive_list: List[str] = []
        self.__exclusive_list: List[str] = []
        self.__summary_list: List[str] = []
        self.__mandatory_list: List[str] = []

        _logger.info("AssessmentState is generated")

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Fact Store Access)
    # -------------------------------------------------------------------------
    def get_fact_store(self) -> FactStorePort:
        """
        Public API: Returns the underlying FactStorePort instance.

        Returns:
            The FactStorePort backing this assessment's working memory
        """
        return self.__fact_store

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Working Memory)
    # -------------------------------------------------------------------------
    def get_working_memory(self) -> Dict[str, FactValue]:
        """
        Public API: Returns the unified working memory view across all layers.

        ASSERTED wins on collisions, then INFERRED, then SEMANTIC. The returned
        dict is a fresh merge — mutating it does not affect any layer.
        """
        return self.__fact_store.get_unified_view()

    def set_working_memory(self, working_memory: Dict[str, FactValue]) -> None:
        """
        Public API: Replaces working memory wholesale into the ASSERTED layer.

        Backward-compat shim for legacy callers. Clears INFERRED and SEMANTIC
        layers so the resulting unified view matches the supplied dict exactly.

        Args:
            working_memory: Working memory dictionary to set
        """
        self.__fact_store.invalidate_layer(FactSource.ASSERTED)
        self.__fact_store.invalidate_layer(FactSource.INFERRED)
        self.__fact_store.invalidate_layer(FactSource.LEARNED)
        self.__fact_store.invalidate_layer(FactSource.HYPOTHETICAL)
        self.__fact_store.invalidate_layer(FactSource.SEMANTIC)
        for name, value in working_memory.items():
            self.__fact_store.set_fact(name, value, FactSource.ASSERTED)

    def lookup_working_memory(self, key_name: str) -> Optional[FactValue]:
        """
        Public API: Looks up a value across all layers (ASSERTED→INFERRED→SEMANTIC).

        Args:
            key_name: Key to look up

        Returns:
            FactValue or None
        """
        if len(key_name) == 0:
            _logger.debug("key_name is None")
            return None
        for source in (
            FactSource.ASSERTED,
            FactSource.INFERRED,
            FactSource.LEARNED,
            FactSource.HYPOTHETICAL,
            FactSource.SEMANTIC,
        ):
            value = self.__fact_store.peek_in_layer(key_name, source)
            if value is not None:
                return value
        return None

    def set_fact(
        self,
        node_variable_name: str,
        value: FactValue,
        node: Optional[Node] = None,
        source: FactSource = FactSource.ASSERTED,
    ) -> None:
        """
        Public API: Sets a fact in the specified layer (defaults to ASSERTED).

        When the target layer already holds the same key, list-creation logic
        runs (existing list → append; otherwise convert to LIST if the node
        signals it should). Callers without a node still get plain overwrite
        semantics, which the LayeredFactStore handles internally.

        Args:
            node_variable_name: Variable name of the node
            value: FactValue to store
            node: Optional node object for list-creation context
            source: FactSource layer to write to
        """
        if len(node_variable_name) == 0:
            _logger.debug("node_variable_name is None")
            return

        existing = self.__fact_store.peek_in_layer(node_variable_name, source)
        if existing is not None:
            merged = self._merge_existing_fact(existing, value, node)
            if merged is None:
                return
            self.__fact_store.set_fact(node_variable_name, merged, source)
        else:
            self.__fact_store.set_fact(node_variable_name, value, source)

    def get_fact(self, name: str) -> Optional[FactValue]:
        """
        Public API: Gets a fact from the unified view (ASSERTED→INFERRED→SEMANTIC).

        Args:
            name: Name of the fact

        Returns:
            FactValue or None
        """
        return self.lookup_working_memory(name)

    def get_fact_sources(self, name: str) -> Set[FactSource]:
        """
        Public API: Returns the set of layers that hold this fact.

        Args:
            name: Name of the fact

        Returns:
            Set of FactSource values
        """
        return self.__fact_store.get_fact_sources(name)

    def remove_fact(self, name: str, source: Optional[FactSource] = None) -> None:
        """
        Public API: Removes a fact. Without a source, removes from every layer.

        Args:
            name: Name of the fact to remove
            source: Optional FactSource layer to target; if None, all layers
        """
        if len(name) == 0:
            _logger.info("name is None")
            return
        self.__fact_store.remove_fact(name, source)

    def invalidate_layer(self, source: FactSource) -> None:
        """
        Public API: Clears every fact in the specified layer.

        Args:
            source: FactSource layer to clear
        """
        self.__fact_store.invalidate_layer(source)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _merge_existing_fact(
        self,
        existing: FactValue,
        value: FactValue,
        node: Optional[Node],
    ) -> Optional[FactValue]:
        """
        Protected Helper: Decides how to combine an incoming write with an existing fact.

        - If the existing value is a LIST, append in place and signal "no rewrite needed".
        - If the node says a list should be created, return a new LIST FactValue.
        - Otherwise, fall through (return value as-is — overwrite).

        Args:
            existing: Current FactValue stored in the target layer
            value: Incoming FactValue
            node: Optional node providing context for list-creation

        Returns:
            FactValue to write, or None if the incoming write was absorbed
            into the existing LIST (no rewrite required)
        """
        if existing.get_value_type() == FactValueType.LIST:
            existing.get_value().append(value)
            return None
        if node is not None and self._should_create_list(node):
            return FactValue([existing, value], FactValueType.LIST)
        return value

    def _should_create_list(self, node: Node) -> bool:
        """
        Protected Helper: Determines if a list should be created.

        Args:
            node: Node to evaluate

        Returns:
            True if list should be created
        """
        has_is_token = len(list(filter(lambda token_string: token_string == 'IS',
                                        node.get_tokens().get_tokens_list()))) > 0
        is_comparison = (
            isinstance(node, ComparisonLine)
            and node.get_line_type() == LineType.COMPARISON
            and node.get_operator() == '=='
        )
        return has_is_token or is_comparison

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Inclusive List)
    # -------------------------------------------------------------------------
    def get_inclusive_list(self) -> List[str]:
        """
        Public API: Returns the inclusive list.
        """
        return self.__inclusive_list

    def set_inclusive_list(self, inclusive_list: List[str]) -> None:
        """
        Public API: Sets the inclusive list.
        """
        self.__inclusive_list = inclusive_list

    def is_in_inclusive_list(self, name: str) -> bool:
        """
        Public API: Checks if name is in inclusive list.
        """
        if len(name) == 0:
            _logger.debug("name is None")
            return False
        return name in self.__inclusive_list

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Summary List)
    # -------------------------------------------------------------------------
    def get_summary_list(self) -> List[str]:
        """
        Public API: Returns the summary list.
        """
        return self.__summary_list

    def set_summary_list(self, summary_list: List[str]) -> None:
        """
        Public API: Sets the summary list.
        """
        if len(summary_list) == 0:
            _logger.debug("summary_list is None")
        self.__summary_list = summary_list

    def add_item_to_summary_list(self, node: str) -> None:
        """
        Public API: Adds an item to the summary list.
        """
        if len(node) == 0:
            _logger.error("node is None")
            return
        if node not in self.__summary_list:
            self.__summary_list.append(node)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Exclusive List)
    # -------------------------------------------------------------------------
    def get_exclusive_list(self) -> List[str]:
        """
        Public API: Returns the exclusive list.
        """
        return self.__exclusive_list

    def set_exclusive_list(self, exclusive_list: List[str]) -> None:
        """
        Public API: Sets the exclusive list.
        """
        if len(exclusive_list) == 0:
            _logger.debug("exclusive_list is None")
        self.__exclusive_list = exclusive_list

    def is_in_exclusive_list(self, name: str) -> bool:
        """
        Public API: Checks if name is in exclusive list.
        """
        if len(name) == 0:
            _logger.debug("name is None")
            return False
        return name in self.__exclusive_list

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Mandatory List)
    # -------------------------------------------------------------------------
    def get_mandatory_list(self) -> List[str]:
        """
        Public API: Returns the mandatory list.
        """
        return self.__mandatory_list

    def set_mandatory_list(self, mandatory_list: List[str]) -> None:
        """
        Public API: Sets the mandatory list.
        """
        if len(mandatory_list) == 0:
            _logger.debug("mandatory_list is None")
        self.__mandatory_list = mandatory_list

    def add_item_to_mandatory_list(self, node_name: str) -> None:
        """
        Public API: Adds an item to the mandatory list.
        """
        if len(node_name) == 0:
            _logger.debug("node_name is None")
            return
        if node_name not in self.__mandatory_list:
            self.__mandatory_list.append(node_name)

    def is_in_mandatory_list(self, node_name: str) -> bool:
        """
        Public API: Checks if node is in mandatory list.
        """
        return node_name in self.__mandatory_list

    def all_mandatory_node_determined(self) -> bool:
        """
        Public API: Checks if all mandatory nodes are determined across any layer.
        """
        unified = self.__fact_store.get_unified_view()
        filtered_list = [name for name in self.__mandatory_list if name in unified]
        return len(filtered_list) == len(self.__mandatory_list)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (RuleSet Integration)
    # -------------------------------------------------------------------------
    def transfer_fact_map_to_working_memory(self, node_set: Optional[NodeSet]) -> None:
        """
        Public API: Loads pre-known FIXED facts from a NodeSet into the ASSERTED layer.

        Args:
            node_set: NodeSet containing facts
        """
        if node_set is None:
            _logger.debug("node_set is None")
            return
        fact_dictionary = node_set.get_fact_dictionary()
        if len(fact_dictionary) == 0:
            return
        for key, value in fact_dictionary.items():
            self.__fact_store.set_fact(key, value, FactSource.ASSERTED)

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        """
        import json
        return json.dumps({
            "working_memory": str(self.__fact_store.get_unified_view()),
            "asserted": str(self.__fact_store.get_layer_snapshot(FactSource.ASSERTED)),
            "inferred": str(self.__fact_store.get_layer_snapshot(FactSource.INFERRED)),
            "learned": str(self.__fact_store.get_layer_snapshot(FactSource.LEARNED)),
            "hypothetical": str(self.__fact_store.get_layer_snapshot(FactSource.HYPOTHETICAL)),
            "semantic": str(self.__fact_store.get_layer_snapshot(FactSource.SEMANTIC)),
            "overrides": list(self.__fact_store.get_overrides()),
            "inclusive_list": self.__inclusive_list,
            "exclusive_list": self.__exclusive_list,
            "summary_list": self.__summary_list,
            "mandatory_list": self.__mandatory_list,
        })
