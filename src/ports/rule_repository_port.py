from abc import ABCMeta, abstractmethod
from typing import Any, Dict, List, Optional
from src.domain.models.rule import RuleEntity, RuleFileEntity, RuleHistoryEntity


class RuleRepositoryPort(metaclass=ABCMeta):
    @abstractmethod
    def find_id_by_name(self, rule_name: str) -> Optional[int]:
        pass  # pragma: no cover

    @abstractmethod
    def find_rule_by_rule_name(self, rule_name: str) -> Optional[RuleEntity]:
        pass  # pragma: no cover

    @abstractmethod
    def find_rule_text_by_rule_name(self, rule_name: str) -> Optional[RuleFileEntity]:
        pass  # pragma: no cover

    @abstractmethod
    def find_all_rules(self) -> List[Dict[str, Any]]:
        pass  # pragma: no cover

    @abstractmethod
    def update_rule_name_and_category(self, old_rule_name: str, new_rule_name: str, new_category: str) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def create_rule(self, rule_details: Dict[str, Any]) -> int:
        pass  # pragma: no cover

    @abstractmethod
    def create_rule_file(self, rule_id: int, new_file: bytearray) -> None:
        pass  # pragma: no cover

    @abstractmethod
    def create_rule_history(self, rule_id: int, history: Dict[str, Any]) -> None:
        pass  # pragma: no cover

    @abstractmethod
    def find_rule_by_rule_name_with_latest_history(self, rule_name: str) -> Optional[Dict[str, Any]]:
        pass  # pragma: no cover
