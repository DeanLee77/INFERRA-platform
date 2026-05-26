from typing import Any, Dict, List, Optional
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.ports.rule_repository_port import RuleRepositoryPort
from src.domain.models.rule import RuleEntity, RuleFileEntity, RuleHistoryEntity
from .models import RuleORM, FileORM, HistoryORM
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)


class RuleRepositoryImpl(RuleRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def _to_rule_entity(self, orm: RuleORM) -> RuleEntity:
        return RuleEntity(
            rule_id=orm.rule_id,
            name=orm.name,
            category=orm.category,
            description=orm.description,
        )

    def _to_file_entity(self, orm: FileORM) -> RuleFileEntity:
        return RuleFileEntity(
            file_id=orm.file_id,
            rule_id=orm.rule_id,
            files=orm.files,
        )

    def find_id_by_name(self, rule_name: str) -> Optional[int]:
        rule = self._db.query(RuleORM).filter_by(name=rule_name).first()
        rule_id = rule.rule_id if rule else None
        _logger.info("rule_id_found", rule_id=rule_id)
        return rule_id

    def find_rule_by_rule_name(self, rule_name: str) -> Optional[RuleEntity]:
        if not rule_name:
            return None
        orm = self._db.query(RuleORM).filter_by(name=rule_name).first()
        return self._to_rule_entity(orm) if orm else None

    def find_rule_text_by_rule_name(self, rule_name: str) -> Optional[RuleFileEntity]:
        rule = self._db.query(RuleORM).filter_by(name=rule_name).first()
        if rule is None:
            return None
        file_orm = rule.get_latest_file()
        return self._to_file_entity(file_orm) if file_orm else None

    def find_all_rules(self) -> List[Dict[str, Any]]:
        result = []
        for rule in self._db.query(RuleORM).all():
            result.append({
                'rule_id': rule.rule_id,
                'name': rule.name,
                'category': rule.category,
                'description': rule.description,
            })
        return result

    def update_rule_name_and_category(self, old_rule_name: str, new_rule_name: str, new_category: str) -> bool:
        try:
            updated_rows = self._db.query(RuleORM).filter_by(name=old_rule_name).update(
                dict(name=new_rule_name, category=new_category)
            )
            self._db.commit()
            return updated_rows > 0
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("rule_update_failed", rule_name=old_rule_name, error=str(exc))
            raise

    def create_rule(self, rule_details: Dict[str, Any]) -> int:
        rule_name = rule_details.get('rule_name')
        if not rule_name:
            raise ValueError("rule_name is required")
        rule_id = self.find_id_by_name(rule_name)
        if rule_id is not None:
            return rule_id
        try:
            rule = RuleORM(**rule_details)
            self._db.add(rule)
            self._db.commit()
            return rule.rule_id
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("rule_create_failed", rule_name=rule_name, error=str(exc))
            raise

    def create_rule_file(self, rule_id: int, new_file: bytearray) -> None:
        if rule_id is None:
            raise ValueError("rule_id is required")
        if new_file is None:
            raise ValueError("new_file is required")
        try:
            _logger.info("creating_rule_file", rule_id=rule_id)
            new_file_record = FileORM(rule_id=rule_id, files=new_file)
            self._db.add(new_file_record)
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("rule_file_create_failed", rule_id=rule_id, error=str(exc))
            raise

    def create_rule_history(self, rule_id: int, history: Dict[str, Any]) -> None:
        if rule_id is None:
            raise ValueError("rule_id is required")
        if history is None:
            raise ValueError("history payload is required")
        try:
            history_record = HistoryORM(rule_id, history)
            self._db.add(history_record)
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("rule_history_create_failed", rule_id=rule_id, error=str(exc))
            raise

    def find_rule_by_rule_name_with_latest_history(self, rule_name: str) -> Optional[Dict[str, Any]]:
        rule_orm = self._db.query(RuleORM).filter_by(name=rule_name).first()
        if rule_orm is None:
            return None
        entity = self._to_rule_entity(rule_orm)
        history_orm = rule_orm.get_latest_history()
        history_data = history_orm.history if history_orm else None
        return {
            'rule': entity,
            'history': history_data,
        }
