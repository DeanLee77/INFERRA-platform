"""Core-owned abstract ports implemented by embedding hosts and Platform."""

from abc import ABCMeta, abstractmethod
from typing import Any, Deque, Dict, Iterable, Iterator, Optional, Set, Tuple

from .records import HistoryRecord
from .values import FactSource, FactValue, FactValueType


class DependencyGraphPort(metaclass=ABCMeta):
    """Abstract interface for graph traversal and back-propagation."""

    @abstractmethod
    def add_dependency_group(
        self,
        parent: str,
        dep_type: int,
        children: Set[str],
    ) -> None:
        pass  # pragma: no cover

    @abstractmethod
    def get_parent_edges(self, node_name: str) -> Set[str]:
        pass  # pragma: no cover

    @abstractmethod
    def get_child_groups(
        self,
        node_name: str,
    ) -> Tuple[Tuple[int, Tuple[str, ...]], ...]:
        pass  # pragma: no cover

    @abstractmethod
    def back_propagate(
        self,
        changed_node: str,
        max_steps: int = 0,
    ) -> Deque[str]:
        pass  # pragma: no cover

    @abstractmethod
    def topological_sort(self) -> Tuple[str, ...]:
        pass  # pragma: no cover

    @abstractmethod
    def all_node_names(self) -> Set[str]:
        pass  # pragma: no cover

    @abstractmethod
    def has_node(self, node_name: str) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def register_node(self, name: str, metadata: Optional[dict] = None) -> int:
        pass  # pragma: no cover

    @abstractmethod
    def edges(self) -> Iterator[Tuple[str, str, int]]:
        pass  # pragma: no cover

    def get_children_by_type(
        self,
        node_name: str,
        type_mask: int,
    ) -> Tuple[str, ...]:
        result: list = []
        for dep_type, children in self.get_child_groups(node_name):
            if dep_type & type_mask == type_mask:
                result.extend(children)
        return tuple(result)

    def get_children_flat(self, node_name: str) -> Tuple[str, ...]:
        result: list = []
        for _, children in self.get_child_groups(node_name):
            result.extend(children)
        return tuple(result)

    def get_dependency_type(self, parent: str, child: str) -> int:
        for dep_type, children in self.get_child_groups(parent):
            if child in children:
                return dep_type
        return -1

    def has_children_of_type(self, node_name: str, type_mask: int) -> bool:
        return len(self.get_children_by_type(node_name, type_mask)) > 0

    def subgraph(self, node_names: Set[str]) -> "DependencyGraphPort":
        result = self.__class__()
        for name in node_names:
            if self.has_node(name):
                for dep_type, children in self.get_child_groups(name):
                    in_sub = {child for child in children if child in node_names}
                    if in_sub:
                        result.add_dependency_group(name, dep_type, in_sub)
        return result

    def lookup_by_id(self, runtime_id: int) -> Optional[str]:
        return None

    def lookup_by_name(self, name: str) -> Optional[int]:
        return None


class FactStorePort(metaclass=ABCMeta):
    """Abstract interface for layered working-memory persistence."""

    @abstractmethod
    def get_unified_view(self) -> Dict[str, FactValue]:
        ...

    @abstractmethod
    def set_fact(
        self,
        name: str,
        value: FactValue,
        source: FactSource = FactSource.ASSERTED,
    ) -> None:
        ...

    @abstractmethod
    def remove_fact(
        self,
        name: str,
        source: Optional[FactSource] = None,
    ) -> None:
        ...

    @abstractmethod
    def invalidate_layer(self, source: FactSource) -> None:
        ...

    @abstractmethod
    def get_fact_sources(self, name: str) -> Set[FactSource]:
        ...

    @abstractmethod
    def get_layer_snapshot(self, source: FactSource) -> Dict[str, FactValue]:
        ...

    @abstractmethod
    def peek_in_layer(
        self,
        name: str,
        source: FactSource,
    ) -> Optional[FactValue]:
        ...

    @abstractmethod
    def get_changed_since(self, timestamp: float) -> Set[str]:
        ...

    @abstractmethod
    def get_overrides(self) -> Set[str]:
        ...


class HistoryRecordStorePort(metaclass=ABCMeta):
    """Abstract interface for evaluation-history persistence."""

    @abstractmethod
    def get_records(self, rule_name: str) -> Dict[str, HistoryRecord]:
        pass  # pragma: no cover

    @abstractmethod
    def get_record(
        self,
        rule_name: str,
        node_name: str,
    ) -> Optional[HistoryRecord]:
        pass  # pragma: no cover

    @abstractmethod
    def update_record(self, rule_name: str, record: HistoryRecord) -> None:
        pass  # pragma: no cover

    @abstractmethod
    def clear(self, rule_name: Optional[str] = None) -> None:
        pass  # pragma: no cover


class IterationPort(metaclass=ABCMeta):
    """Abstract interface for deterministic iteration evaluation."""

    @abstractmethod
    def initialise(self, list_size: int, quantifier: str, list_name: str) -> None:
        pass  # pragma: no cover

    @abstractmethod
    async def record_answer(
        self,
        index: int,
        question_name: str,
        value: Any,
        node_value_type: FactValueType,
    ) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def evaluate(self) -> FactValue:
        pass  # pragma: no cover

    @abstractmethod
    def get_progress(self) -> Tuple[int, int]:
        pass  # pragma: no cover

    @abstractmethod
    def reset_iterate_context(self) -> None:
        pass  # pragma: no cover


class QuestionStrategyPort(metaclass=ABCMeta):
    """Port contract for pluggable question selection."""

    @abstractmethod
    def should_ask(
        self,
        node: Any,
        working_memory: Dict[str, Any],
        has_children: bool = False,
    ) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def select_next(
        self,
        candidates: Iterable[Any],
        working_memory: Dict[str, Any],
        has_children_by_name: Optional[Dict[str, bool]] = None,
    ) -> Optional[Any]:
        pass  # pragma: no cover

