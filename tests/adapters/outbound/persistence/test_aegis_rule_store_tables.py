from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.models import (
    AegisFileORM,
    AegisRuleORM,
    FileORM,
    HistoryORM,
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
