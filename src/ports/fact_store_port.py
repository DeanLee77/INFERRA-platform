"""
Fact Store Port Module.
Abstract interface (ABCMeta) for layered working-memory persistence.

Uses ABCMeta for runtime enforcement and explicit inheritance, consistent
with the project's port architecture convention. Converted from Protocol
in Phase 2.5 (WS-7) to align with all other ports.
"""

from abc import ABCMeta, abstractmethod
from typing import Dict, Optional, Set

from src.domain.fact_values import FactValue
from src.domain.state.fact_source import FactSource


class FactStorePort(metaclass=ABCMeta):
    """
    Abstract interface for a layered fact store.

    Defines the contract for working-memory persistence with provenance
    tagging via FactSource. Implementations should preserve a unified
    read view in which ASSERTED beats INFERRED beats SEMANTIC on collisions.

    All concrete implementations must inherit from this class and implement
    every abstract method.
    """

    @abstractmethod
    def get_unified_view(self) -> Dict[str, FactValue]:
        """
        Return a merged snapshot of all layers (ASSERTED > INFERRED > SEMANTIC).

        The returned dict is a fresh copy; mutations do not affect the store.
        """
        ...

    @abstractmethod
    def set_fact(
        self,
        name: str,
        value: FactValue,
        source: FactSource = FactSource.ASSERTED,
    ) -> None:
        """
        Write a fact into the specified layer.

        Args:
            name: Fact key
            value: FactValue to store
            source: Target FactSource layer (defaults to ASSERTED)
        """
        ...

    @abstractmethod
    def remove_fact(self, name: str, source: Optional[FactSource] = None) -> None:
        """
        Remove a fact. Without a source, removes from every layer.

        Args:
            name: Fact key
            source: Optional FactSource layer to target
        """
        ...

    @abstractmethod
    def invalidate_layer(self, source: FactSource) -> None:
        """
        Re-tract every fact in the specified layer.

        Args:
            source: FactSource layer to clear
        """
        ...

    @abstractmethod
    def get_fact_sources(self, name: str) -> Set[FactSource]:
        """
        Return the set of layers that hold this fact.

        Args:
            name: Fact key

        Returns:
            Set of FactSource values
        """
        ...

    @abstractmethod
    def get_layer_snapshot(self, source: FactSource) -> Dict[str, FactValue]:
        """
        Return a fresh dict copy of a single layer's contents.

        Args:
            source: FactSource layer to read

        Returns:
            Dict of fact name -> FactValue for that layer
        """
        ...

    @abstractmethod
    def peek_in_layer(self, name: str, source: FactSource) -> Optional[FactValue]:
        """
        Look up a single fact within a specific layer without copying the layer.

        Args:
            name: Fact key
            source: FactSource layer to search

        Returns:
            FactValue if present in that layer, None otherwise
        """
        ...

    @abstractmethod
    def get_changed_since(self, timestamp: float) -> Set[str]:
        """
        Return the set of fact names whose last-write timestamp is strictly greater than `timestamp`.

        Args:
            timestamp: Unix epoch seconds

        Returns:
            Set of fact names changed since that point
        """
        ...

    @abstractmethod
    def get_overrides(self) -> Set[str]:
        """
        Return the set of fact names where an ASSERTED entry currently overrides an INFERRED entry.

        Truth-maintenance helper exposing the override-tracking state.
        """
        ...
