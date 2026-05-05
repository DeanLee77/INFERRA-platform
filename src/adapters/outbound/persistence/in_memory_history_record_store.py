"""
In-memory HistoryRecordStore implementation.

Suitable for single-session use and testing.
Phase 2 will add a SQLAlchemy-backed implementation.
"""

from typing import Dict, Optional

from src.domain.nodes.record import HistoryRecord
from src.ports.history_record_store_port import HistoryRecordStorePort


class InMemoryHistoryRecordStore(HistoryRecordStorePort):
    """
    Thread-unsafe in-memory store for HistoryRecords.

    Stores records keyed by rule_name -> node_name -> HistoryRecord.
    Use only in single-session or test contexts. For multi-session
    production use, replace with the DB-backed implementation.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, HistoryRecord]] = {}

    def get_records(self, rule_name: str) -> Dict[str, HistoryRecord]:
        return dict(self._store.get(rule_name, {}))

    def get_record(self, rule_name: str, node_name: str) -> Optional[HistoryRecord]:
        return self._store.get(rule_name, {}).get(node_name)

    def update_record(self, rule_name: str, record: HistoryRecord) -> None:
        if rule_name not in self._store:
            self._store[rule_name] = {}
        self._store[rule_name][record.name] = record

    def clear(self, rule_name: Optional[str] = None) -> None:
        if rule_name is not None:
            self._store.pop(rule_name, None)
        else:
            self._store.clear()
