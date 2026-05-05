"""
Tests for SqlAlchemyHistoryRecordStore.

Covers:
- Fallback in-memory mode when session is None
- SQLAlchemy mode with in-memory SQLite
- Port contract compliance
- CRUD operations: get_records, get_record, update_record, clear
- Upsert behavior on update_record
- Empty queries
"""

import pytest

from src.domain.nodes.record import HistoryRecord
from src.ports.history_record_store_port import HistoryRecordStorePort
from src.adapters.outbound.persistence.sqlalchemy_history_record_store import (
    SqlAlchemyHistoryRecordStore,
)


class TestFallbackMode:
    def test_get_records_empty(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        assert store.get_records("rule1") == {}

    def test_update_and_get_record(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        r = HistoryRecord(name="age", true_count=5, false_count=2)
        store.update_record("rule1", r)
        assert store.get_record("rule1", "age") == r

    def test_get_records_returns_copy(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        store.update_record("rule1", HistoryRecord(name="a", true_count=1))
        records = store.get_records("rule1")
        records["a"] = HistoryRecord(name="a", true_count=99)
        assert store.get_record("rule1", "a").true_count == 1

    def test_clear_specific_rule(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        store.update_record("rule1", HistoryRecord(name="a"))
        store.update_record("rule2", HistoryRecord(name="b"))
        store.clear("rule1")
        assert store.get_record("rule1", "a") is None
        assert store.get_record("rule2", "b") is not None

    def test_clear_all(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        store.update_record("rule1", HistoryRecord(name="a"))
        store.update_record("rule2", HistoryRecord(name="b"))
        store.clear()
        assert store.get_records("rule1") == {}
        assert store.get_records("rule2") == {}

    def test_is_instance_of_port(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        assert isinstance(store, HistoryRecordStorePort)

    def test_update_existing_record_replaces(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        store.update_record("rule1", HistoryRecord(name="x", true_count=1))
        store.update_record("rule1", HistoryRecord(name="x", true_count=5, false_count=3))
        result = store.get_record("rule1", "x")
        assert result.true_count == 5
        assert result.false_count == 3

    def test_get_record_nonexistent(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        assert store.get_record("rule1", "missing") is None

    def test_multiple_rules_isolated(self):
        store = SqlAlchemyHistoryRecordStore(session=None)
        store.update_record("rule1", HistoryRecord(name="a", true_count=1))
        store.update_record("rule2", HistoryRecord(name="a", true_count=2))
        assert store.get_record("rule1", "a").true_count == 1
        assert store.get_record("rule2", "a").true_count == 2


class TestSqlAlchemyMode:
    @pytest.fixture(autouse=True)
    def _setup_db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.adapters.outbound.persistence.sqlalchemy_history_record_store import (
            HistoryRecordORM,
        )

        engine = create_engine("sqlite:///:memory:")
        HistoryRecordORM.__table__.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        self.session = SessionLocal()
        yield
        self.session.close()

    def test_get_records_empty(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        assert store.get_records("rule1") == {}

    def test_update_and_get_record(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        r = HistoryRecord(name="age", true_count=5, false_count=2)
        store.update_record("rule1", r)
        result = store.get_record("rule1", "age")
        assert result is not None
        assert result.true_count == 5
        assert result.false_count == 2

    def test_get_records_returns_all(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        store.update_record("rule1", HistoryRecord(name="a", true_count=1))
        store.update_record("rule1", HistoryRecord(name="b", true_count=2))
        records = store.get_records("rule1")
        assert len(records) == 2
        assert records["a"].true_count == 1
        assert records["b"].true_count == 2

    def test_update_existing_upserts(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        store.update_record("rule1", HistoryRecord(name="x", true_count=1))
        store.update_record("rule1", HistoryRecord(name="x", true_count=5, false_count=3))
        result = store.get_record("rule1", "x")
        assert result.true_count == 5
        assert result.false_count == 3

    def test_clear_specific_rule(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        store.update_record("rule1", HistoryRecord(name="a"))
        store.update_record("rule2", HistoryRecord(name="b"))
        store.clear("rule1")
        assert store.get_record("rule1", "a") is None
        assert store.get_record("rule2", "b") is not None

    def test_clear_all(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        store.update_record("rule1", HistoryRecord(name="a"))
        store.update_record("rule2", HistoryRecord(name="b"))
        store.clear()
        assert store.get_records("rule1") == {}
        assert store.get_records("rule2") == {}

    def test_is_instance_of_port(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        assert isinstance(store, HistoryRecordStorePort)

    def test_get_record_nonexistent(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        assert store.get_record("rule1", "missing") is None

    def test_multiple_rules_isolated(self):
        store = SqlAlchemyHistoryRecordStore(session=self.session)
        store.update_record("rule1", HistoryRecord(name="a", true_count=1))
        store.update_record("rule2", HistoryRecord(name="a", true_count=2))
        assert store.get_record("rule1", "a").true_count == 1
        assert store.get_record("rule2", "a").true_count == 2
