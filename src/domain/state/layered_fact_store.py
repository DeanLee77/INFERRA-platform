"""
Layered Fact Store.
Provenance-tagged working-memory store implementing FactStorePort.
"""

import time
from typing import Callable, Dict, Optional, Set

from src.domain.fact_values import FactValue
from src.domain.state.fact_source import FactSource
from src.ports.fact_store_port import FactStorePort

_OVERRIDE_TRACKED_SOURCES = frozenset(
    (FactSource.INFERRED, FactSource.LEARNED, FactSource.HYPOTHETICAL)
)


class LayeredFactStore(FactStorePort):
    """
    Layered fact store. Unified read view precedence:
    ASSERTED > INFERRED > LEARNED > HYPOTHETICAL > SEMANTIC.

    Carries an `_overrides` set as a truth-maintenance hook — when an ASSERTED
    write covers an existing INFERRED entry, the name is recorded so consumers
    can re-derive or invalidate downstream conclusions without dumpster-diving
    through the layer dicts.
    """

    def __init__(self, clock: Optional[Callable[[], float]] = None) -> None:
        self._asserted: Dict[str, FactValue] = {}
        self._inferred: Dict[str, FactValue] = {}
        self._learned: Dict[str, FactValue] = {}
        self._hypothetical: Dict[str, FactValue] = {}
        self._semantic: Dict[str, FactValue] = {}
        self._layers: Dict[FactSource, Dict[str, FactValue]] = {
            FactSource.ASSERTED: self._asserted,
            FactSource.INFERRED: self._inferred,
            FactSource.LEARNED: self._learned,
            FactSource.HYPOTHETICAL: self._hypothetical,
            FactSource.SEMANTIC: self._semantic,
        }
        self._timestamps: Dict[str, float] = {}
        self._overrides: Set[str] = set()
        self._clock: Callable[[], float] = clock if clock is not None else time.time

    def _get_layer(self, source: FactSource) -> Dict[str, FactValue]:
        return self._layers[source]

    def get_unified_view(self) -> Dict[str, FactValue]:
        return {
            **self._semantic,
            **self._hypothetical,
            **self._learned,
            **self._inferred,
            **self._asserted,
        }

    def set_fact(
        self,
        name: str,
        value: FactValue,
        source: FactSource = FactSource.ASSERTED,
    ) -> None:
        target = self._layers[source]
        target[name] = value
        self._timestamps[name] = self._clock()
        if source is FactSource.ASSERTED and (
            name in self._inferred
            or name in self._learned
            or name in self._hypothetical
        ):
            self._overrides.add(name)

    def remove_fact(self, name: str, source: Optional[FactSource] = None) -> None:
        if source is None:
            self._asserted.pop(name, None)
            self._inferred.pop(name, None)
            self._learned.pop(name, None)
            self._hypothetical.pop(name, None)
            self._semantic.pop(name, None)
            self._overrides.discard(name)
            self._timestamps.pop(name, None)
            return
        layer = self._get_layer(source)
        layer.pop(name, None)
        if source is FactSource.ASSERTED:
            self._overrides.discard(name)
        if (
            name not in self._asserted
            and name not in self._inferred
            and name not in self._learned
            and name not in self._hypothetical
            and name not in self._semantic
        ):
            self._timestamps.pop(name, None)

    def invalidate_layer(self, source: FactSource) -> None:
        layer = self._get_layer(source)
        cleared = set(layer.keys())
        layer.clear()
        if source in _OVERRIDE_TRACKED_SOURCES:
            self._overrides.clear()
            self._rebuild_overrides()
        elif source is FactSource.ASSERTED:
            self._overrides -= cleared
        for name in cleared:
            if (
                name not in self._asserted
                and name not in self._inferred
                and name not in self._learned
                and name not in self._hypothetical
                and name not in self._semantic
            ):
                self._timestamps.pop(name, None)

    def _rebuild_overrides(self) -> None:
        self._overrides = {
            name
            for name in self._asserted
            if name in self._inferred
            or name in self._learned
            or name in self._hypothetical
        }

    def get_fact_sources(self, name: str) -> Set[FactSource]:
        sources: Set[FactSource] = set()
        if name in self._asserted:
            sources.add(FactSource.ASSERTED)
        if name in self._inferred:
            sources.add(FactSource.INFERRED)
        if name in self._learned:
            sources.add(FactSource.LEARNED)
        if name in self._hypothetical:
            sources.add(FactSource.HYPOTHETICAL)
        if name in self._semantic:
            sources.add(FactSource.SEMANTIC)
        return sources

    def invalidate_hypotheses(self) -> None:
        self.invalidate_layer(FactSource.HYPOTHETICAL)

    def get_layer_snapshot(self, source: FactSource) -> Dict[str, FactValue]:
        return dict(self._get_layer(source))

    def peek_in_layer(self, name: str, source: FactSource) -> Optional[FactValue]:
        return self._get_layer(source).get(name)

    def get_changed_since(self, timestamp: float) -> Set[str]:
        return {name for name, ts in self._timestamps.items() if ts > timestamp}

    def get_overrides(self) -> Set[str]:
        return set(self._overrides)
