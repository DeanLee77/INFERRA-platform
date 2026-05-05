"""
SQLAlchemy-backed HistoryRecordStore implementation.

Persists HistoryRecord data to the application database via a dedicated
ORM table. Suitable for multi-session production use where history
records must survive process restarts.

Falls back to in-memory storage when the database session is unavailable.
"""

from typing import Dict, Optional

from sqlalchemy import Column, String, Integer, UniqueConstraint
from sqlalchemy.orm import Session

import structlog

from src.domain.nodes.record import HistoryRecord
from src.ports.history_record_store_port import HistoryRecordStorePort

log = structlog.get_logger()

try:
    from src.adapters.outbound.persistence.database import Base

    class HistoryRecordORM(Base):
        __tablename__ = "history_record"
        __table_args__ = (
            UniqueConstraint("rule_name", "node_name", name="uq_history_record_rule_node"),
        )

        rule_name = Column(String, primary_key=True, nullable=False)
        node_name = Column(String, primary_key=True, nullable=False)
        true_count = Column(Integer, nullable=False, default=0)
        false_count = Column(Integer, nullable=False, default=0)

    _ORM_AVAILABLE = True
except Exception:
    _ORM_AVAILABLE = False


class SqlAlchemyHistoryRecordStore(HistoryRecordStorePort):
    """
    SQLAlchemy-backed store for HistoryRecords.

    Stores records in a ``history_record`` table keyed by
    (rule_name, node_name). Falls back to an in-memory dict
    when the DB session is None (e.g. in test environments
    without a database fixture).

    Args:
        session: SQLAlchemy Session for database access.
            If None, falls back to in-memory storage.
    """

    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self._fallback: Dict[str, Dict[str, HistoryRecord]] = {}

    def get_records(self, rule_name: str) -> Dict[str, HistoryRecord]:
        if self._session is None or not _ORM_AVAILABLE:
            return dict(self._fallback.get(rule_name, {}))

        rows = (
            self._session.query(HistoryRecordORM)
            .filter(HistoryRecordORM.rule_name == rule_name)
            .all()
        )
        return {
            row.node_name: HistoryRecord(
                name=row.node_name,
                true_count=row.true_count,
                false_count=row.false_count,
            )
            for row in rows
        }

    def get_record(self, rule_name: str, node_name: str) -> Optional[HistoryRecord]:
        if self._session is None or not _ORM_AVAILABLE:
            return self._fallback.get(rule_name, {}).get(node_name)

        row = (
            self._session.query(HistoryRecordORM)
            .filter(
                HistoryRecordORM.rule_name == rule_name,
                HistoryRecordORM.node_name == node_name,
            )
            .first()
        )
        if row is None:
            return None
        return HistoryRecord(
            name=row.node_name,
            true_count=row.true_count,
            false_count=row.false_count,
        )

    def update_record(self, rule_name: str, record: HistoryRecord) -> None:
        if self._session is None or not _ORM_AVAILABLE:
            if rule_name not in self._fallback:
                self._fallback[rule_name] = {}
            self._fallback[rule_name][record.name] = record
            return

        row = (
            self._session.query(HistoryRecordORM)
            .filter(
                HistoryRecordORM.rule_name == rule_name,
                HistoryRecordORM.node_name == record.name,
            )
            .first()
        )
        if row is None:
            row = HistoryRecordORM(
                rule_name=rule_name,
                node_name=record.name,
                true_count=record.true_count,
                false_count=record.false_count,
            )
            self._session.add(row)
        else:
            row.true_count = record.true_count
            row.false_count = record.false_count
        self._session.commit()

    def clear(self, rule_name: Optional[str] = None) -> None:
        if self._session is None or not _ORM_AVAILABLE:
            if rule_name is not None:
                self._fallback.pop(rule_name, None)
            else:
                self._fallback.clear()
            return

        if rule_name is not None:
            self._session.query(HistoryRecordORM).filter(
                HistoryRecordORM.rule_name == rule_name
            ).delete()
        else:
            self._session.query(HistoryRecordORM).delete()
        self._session.commit()
