from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.models import (
    AegisFileORM,
    AegisHistoryORM,
    AegisRuleORM,
    FileORM,
    HistoryORM,
    LLMProductConfigurationORM,
    RuleORM,
)


def _memory_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_aegis_rule_store_bootstraps_legacy_aegis_testing_rules(monkeypatch):
    legacy_engine = _memory_engine()
    aegis_engine = _memory_engine()
    database.Base.metadata.create_all(
        bind=legacy_engine,
        tables=[RuleORM.__table__, FileORM.__table__, HistoryORM.__table__],
    )

    LegacySession = sessionmaker(autocommit=False, autoflush=False, bind=legacy_engine)
    AegisSession = sessionmaker(autocommit=False, autoflush=False, bind=aegis_engine)

    legacy_db = LegacySession()
    aegis_rule = RuleORM(
        rule_name="aegis_test_02_hard_safety_stop",
        rule_category="AEGIS Testing",
        rule_description="Hard-stop safety boundary.",
    )
    aegis_rule.rule_id = 71
    shared_rule = RuleORM(
        rule_name="shared_reference_rule",
        rule_category="Reference",
        rule_description="Not AEGIS scoped.",
    )
    shared_rule.rule_id = 72
    legacy_db.add_all([aegis_rule, shared_rule])
    aegis_file = FileORM(
        rule_id=71,
        files=bytearray(b"hard safety stop gate is satisfied"),
    )
    aegis_file.file_id = 171
    shared_file = FileORM(
        rule_id=72,
        files=bytearray(b"shared reference"),
    )
    shared_file.file_id = 172
    legacy_db.add_all([aegis_file, shared_file])
    aegis_history = HistoryORM(71, {"revision": 1})
    aegis_history.history_id = 271
    legacy_db.add(aegis_history)
    legacy_db.commit()
    legacy_db.close()

    monkeypatch.setattr(database, "engine", legacy_engine)
    monkeypatch.setattr(database, "aegis_engine", aegis_engine)
    monkeypatch.setattr(database, "SessionLocal", LegacySession)
    monkeypatch.setattr(database, "AegisSessionLocal", AegisSession)
    monkeypatch.setattr(database, "_aegis_tables_ready", False)

    database.ensure_aegis_rule_store_tables()

    scoped_db = AegisSession()
    try:
        rules = scoped_db.query(AegisRuleORM).all()
        assert [rule.name for rule in rules] == ["aegis_test_02_hard_safety_stop"]
        assert rules[0].category == "AEGIS Testing"
        copied_file = scoped_db.query(AegisFileORM).one()
        assert copied_file.rule_id == rules[0].rule_id
        assert copied_file.files == b"hard safety stop gate is satisfied"
        copied_history = scoped_db.query(AegisHistoryORM).one()
        assert copied_history.rule_id == rules[0].rule_id
        assert copied_history.history == {"revision": 1}
    finally:
        scoped_db.close()


def test_aegis_database_uri_rejects_shared_platform_database(monkeypatch):
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(
            SQLALCHEMY_DATABASE_URI="postgresql://inferra:inferra@postgres:5432/inferra",
            AEGIS_SQLALCHEMY_DATABASE_URI="postgresql://inferra:other@postgres:5432/inferra",
            AEGIS_ALLOW_SHARED_DATABASE=False,
        ),
    )

    with pytest.raises(RuntimeError, match="distinct database"):
        database.resolve_aegis_database_uri()


def test_aegis_database_uri_requires_explicit_shared_database_override(monkeypatch):
    shared_uri = "postgresql://inferra:inferra@postgres:5432/inferra"
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(
            SQLALCHEMY_DATABASE_URI=shared_uri,
            AEGIS_SQLALCHEMY_DATABASE_URI="",
            AEGIS_ALLOW_SHARED_DATABASE=True,
        ),
    )

    assert database.resolve_aegis_database_uri() == shared_uri


def test_aegis_database_uri_requires_a_uri_when_sharing_is_disabled(monkeypatch):
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(
            SQLALCHEMY_DATABASE_URI="sqlite:///platform.db",
            AEGIS_SQLALCHEMY_DATABASE_URI="",
            AEGIS_ALLOW_SHARED_DATABASE=False,
        ),
    )

    with pytest.raises(RuntimeError, match="must be set"):
        database.resolve_aegis_database_uri()


def test_aegis_database_uri_accepts_a_distinct_database(monkeypatch):
    aegis_uri = "postgresql://inferra:secret@postgres:5432/aegis"
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(
            SQLALCHEMY_DATABASE_URI="postgresql://inferra:secret@postgres:5432/inferra",
            AEGIS_SQLALCHEMY_DATABASE_URI=aegis_uri,
            AEGIS_ALLOW_SHARED_DATABASE=False,
        ),
    )

    assert database.resolve_aegis_database_uri() == aegis_uri


def test_database_session_dependencies_always_close(monkeypatch):
    platform_session = MagicMock()
    aegis_session = MagicMock()
    ensure = MagicMock()
    monkeypatch.setattr(database, "SessionLocal", lambda: platform_session)
    monkeypatch.setattr(database, "AegisSessionLocal", lambda: aegis_session)
    monkeypatch.setattr(database, "ensure_aegis_rule_store_tables", ensure)

    platform_generator = database.get_db()
    assert next(platform_generator) is platform_session
    platform_generator.close()
    platform_session.close.assert_called_once_with()

    aegis_generator = database.get_aegis_db()
    assert next(aegis_generator) is aegis_session
    aegis_generator.close()
    ensure.assert_called_once_with()
    aegis_session.close.assert_called_once_with()


def test_llm_configuration_table_creation_is_idempotent(monkeypatch):
    engine = _memory_engine()
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_llm_configuration_tables_ready", False)

    database.ensure_llm_configuration_tables()
    database.ensure_llm_configuration_tables()

    assert inspect(engine).has_table(LLMProductConfigurationORM.__tablename__)
    assert database._llm_configuration_tables_ready is True


@pytest.mark.parametrize("kind", ["aegis", "llm"])
def test_table_initialization_double_checks_inside_lock(monkeypatch, kind):
    class MarkReadyOnEnter:
        def __enter__(self):
            if kind == "aegis":
                database._aegis_tables_ready = True
            else:
                database._llm_configuration_tables_ready = True

        def __exit__(self, *_args):
            return False

    create_all = MagicMock()
    monkeypatch.setattr(database.Base.metadata, "create_all", create_all)
    if kind == "aegis":
        monkeypatch.setattr(database, "_aegis_tables_ready", False)
        monkeypatch.setattr(database, "_aegis_tables_lock", MarkReadyOnEnter())
        database.ensure_aegis_rule_store_tables()
    else:
        monkeypatch.setattr(database, "_llm_configuration_tables_ready", False)
        monkeypatch.setattr(database, "_llm_configuration_tables_lock", MarkReadyOnEnter())
        database.ensure_llm_configuration_tables()

    create_all.assert_not_called()


def test_schema_guard_handles_missing_table_and_adds_missing_target_column(monkeypatch):
    inspector = MagicMock()
    inspector.has_table.return_value = False
    monkeypatch.setattr(database, "inspect", lambda _engine: inspector)
    database._ensure_aegis_rule_store_schema()

    connection = MagicMock()
    begin = MagicMock()
    begin.__enter__.return_value = connection
    begin.__exit__.return_value = False
    engine = MagicMock()
    engine.begin.return_value = begin
    inspector.has_table.return_value = True
    inspector.get_columns.return_value = [{"name": "rule_id"}]
    monkeypatch.setattr(database, "aegis_engine", engine)

    database._ensure_aegis_rule_store_schema()

    connection.execute.assert_called_once()
    assert "ADD COLUMN target_node_name" in str(connection.execute.call_args.args[0])


def test_bootstrap_returns_when_legacy_rule_table_is_absent(monkeypatch):
    inspector = MagicMock()
    inspector.has_table.return_value = False
    monkeypatch.setattr(database, "inspect", lambda _engine: inspector)
    legacy_session = MagicMock()
    aegis_session = MagicMock()
    monkeypatch.setattr(database, "SessionLocal", lambda: legacy_session)
    monkeypatch.setattr(database, "AegisSessionLocal", lambda: aegis_session)

    database._bootstrap_legacy_aegis_testing_rules()

    legacy_session.assert_not_called()
    aegis_session.assert_not_called()


def test_bootstrap_empty_legacy_store_closes_both_sessions(monkeypatch):
    legacy_engine = _memory_engine()
    aegis_engine = _memory_engine()
    database.Base.metadata.create_all(
        bind=legacy_engine,
        tables=[RuleORM.__table__, FileORM.__table__, HistoryORM.__table__],
    )
    database.Base.metadata.create_all(
        bind=aegis_engine,
        tables=[AegisRuleORM.__table__, AegisFileORM.__table__, AegisHistoryORM.__table__],
    )
    LegacySession = sessionmaker(autocommit=False, autoflush=False, bind=legacy_engine)
    AegisSession = sessionmaker(autocommit=False, autoflush=False, bind=aegis_engine)
    legacy_db = LegacySession()
    aegis_db = AegisSession()
    legacy_close = MagicMock(wraps=legacy_db.close)
    aegis_close = MagicMock(wraps=aegis_db.close)
    monkeypatch.setattr(legacy_db, "close", legacy_close)
    monkeypatch.setattr(aegis_db, "close", aegis_close)
    monkeypatch.setattr(database, "engine", legacy_engine)
    monkeypatch.setattr(database, "SessionLocal", lambda: legacy_db)
    monkeypatch.setattr(database, "AegisSessionLocal", lambda: aegis_db)

    database._bootstrap_legacy_aegis_testing_rules()

    legacy_close.assert_called_once_with()
    aegis_close.assert_called_once_with()


def test_bootstrap_skips_rules_that_already_exist_and_rolls_back(monkeypatch):
    legacy_engine = _memory_engine()
    aegis_engine = _memory_engine()
    database.Base.metadata.create_all(
        bind=legacy_engine,
        tables=[RuleORM.__table__, FileORM.__table__, HistoryORM.__table__],
    )
    database.Base.metadata.create_all(
        bind=aegis_engine,
        tables=[AegisRuleORM.__table__, AegisFileORM.__table__, AegisHistoryORM.__table__],
    )
    LegacySession = sessionmaker(autocommit=False, autoflush=False, bind=legacy_engine)
    AegisSession = sessionmaker(autocommit=False, autoflush=False, bind=aegis_engine)
    legacy_db = LegacySession()
    legacy_rule = RuleORM(
        rule_name="aegis_test_existing",
        rule_category="AEGIS Testing",
        rule_description="legacy",
    )
    legacy_rule.rule_id = 1
    legacy_db.add(legacy_rule)
    legacy_db.commit()
    legacy_db.close()
    aegis_db = AegisSession()
    scoped_rule = AegisRuleORM(
        rule_name="aegis_test_existing",
        rule_category="AEGIS Testing",
        rule_description="already copied",
    )
    scoped_rule.rule_id = 1
    aegis_db.add(scoped_rule)
    aegis_db.commit()
    aegis_db.close()
    monkeypatch.setattr(database, "engine", legacy_engine)
    monkeypatch.setattr(database, "SessionLocal", LegacySession)
    monkeypatch.setattr(database, "AegisSessionLocal", AegisSession)

    database._bootstrap_legacy_aegis_testing_rules()

    check = AegisSession()
    try:
        assert check.query(AegisRuleORM).count() == 1
    finally:
        check.close()


def test_table_ready_fast_paths_do_not_touch_metadata(monkeypatch):
    create_all = MagicMock()
    monkeypatch.setattr(database.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(database, "_aegis_tables_ready", True)
    monkeypatch.setattr(database, "_llm_configuration_tables_ready", True)

    database.ensure_aegis_rule_store_tables()
    database.ensure_llm_configuration_tables()

    create_all.assert_not_called()


def test_bootstrap_reraises_generic_database_failures_and_closes_sessions(monkeypatch):
    inspector = MagicMock()
    inspector.has_table.return_value = True
    legacy_db = MagicMock()
    aegis_db = MagicMock()
    legacy_db.query.return_value.filter.return_value.order_by.return_value.all.side_effect = (
        SQLAlchemyError("read failed")
    )
    monkeypatch.setattr(database, "inspect", lambda _engine: inspector)
    monkeypatch.setattr(database, "SessionLocal", lambda: legacy_db)
    monkeypatch.setattr(database, "AegisSessionLocal", lambda: aegis_db)

    with pytest.raises(SQLAlchemyError, match="read failed"):
        database._bootstrap_legacy_aegis_testing_rules()

    aegis_db.rollback.assert_called_once_with()
    legacy_db.close.assert_called_once_with()
    aegis_db.close.assert_called_once_with()


def test_bootstrap_treats_integrity_error_as_completed_when_names_exist(monkeypatch):
    inspector = MagicMock()
    inspector.has_table.return_value = True
    legacy_rule = SimpleNamespace(
        name="aegis_test_existing",
        category="AEGIS Testing",
        description="legacy",
        rule_id=1,
    )
    legacy_db = MagicMock()
    legacy_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        legacy_rule
    ]
    aegis_db = MagicMock()
    initial_queries = []
    for values in ([], [], [], []):
        query = MagicMock()
        query.all.return_value = values
        initial_queries.append(query)
    duplicate_query = MagicMock()
    duplicate_query.filter.return_value.all.return_value = [("aegis_test_existing",)]
    aegis_db.query.side_effect = [*initial_queries, duplicate_query]
    aegis_db.flush.side_effect = IntegrityError(
        "insert aegis rule", {}, RuntimeError("duplicate")
    )
    monkeypatch.setattr(database, "inspect", lambda _engine: inspector)
    monkeypatch.setattr(database, "SessionLocal", lambda: legacy_db)
    monkeypatch.setattr(database, "AegisSessionLocal", lambda: aegis_db)

    database._bootstrap_legacy_aegis_testing_rules()

    aegis_db.rollback.assert_called_once_with()
    legacy_db.close.assert_called_once_with()
    aegis_db.close.assert_called_once_with()
