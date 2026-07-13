from threading import Lock

from sqlalchemy import create_engine, inspect, or_, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker, declarative_base

from src.config import settings
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)

AEGIS_TEST_CATEGORY = "AEGIS Testing"
AEGIS_TEST_RULE_PREFIX = "aegis_test_"


def _database_scope(database_uri: str) -> tuple[str | None, str | None, int | None, str | None]:
    url = make_url(database_uri)
    return (url.get_backend_name(), url.host, url.port, url.database)


def resolve_aegis_database_uri() -> str:
    aegis_database_uri = settings.AEGIS_SQLALCHEMY_DATABASE_URI
    if not aegis_database_uri:
        if settings.AEGIS_ALLOW_SHARED_DATABASE:
            return settings.SQLALCHEMY_DATABASE_URI
        raise RuntimeError(
            "AEGIS_SQLALCHEMY_DATABASE_URI must be set for deployed AEGIS rule-store access"
        )

    if (
        not settings.AEGIS_ALLOW_SHARED_DATABASE
        and _database_scope(aegis_database_uri) == _database_scope(settings.SQLALCHEMY_DATABASE_URI)
    ):
        raise RuntimeError(
            "AEGIS_SQLALCHEMY_DATABASE_URI must target a distinct database from "
            "SQLALCHEMY_DATABASE_URI"
        )
    return aegis_database_uri


engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_aegis_database_uri = resolve_aegis_database_uri()
aegis_engine = create_engine(_aegis_database_uri)
AegisSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=aegis_engine)
_aegis_tables_ready = False
_aegis_tables_lock = Lock()
_llm_configuration_tables_ready = False
_llm_configuration_tables_lock = Lock()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_aegis_rule_store_tables() -> None:
    global _aegis_tables_ready
    if _aegis_tables_ready:
        return
    with _aegis_tables_lock:
        if _aegis_tables_ready:
            return
        from .models import (
            AegisActionProposalORM,
            AegisEventLedgerEntryORM,
            AegisFileORM,
            AegisHistoryORM,
            AegisRuleORM,
            AegisSessionSnapshotORM,
            AegisTriggerPolicyORM,
            AegisTriggerReceiptORM,
            AegisWorkflowDefinitionORM,
            AegisWorkflowRunORM,
            AegisWorkflowVersionORM,
        )

        Base.metadata.create_all(
            bind=aegis_engine,
            tables=[
                AegisRuleORM.__table__,
                AegisFileORM.__table__,
                AegisHistoryORM.__table__,
                AegisWorkflowDefinitionORM.__table__,
                AegisWorkflowVersionORM.__table__,
                AegisWorkflowRunORM.__table__,
                AegisActionProposalORM.__table__,
                AegisEventLedgerEntryORM.__table__,
                AegisSessionSnapshotORM.__table__,
                AegisTriggerPolicyORM.__table__,
                AegisTriggerReceiptORM.__table__,
            ],
            checkfirst=True,
        )
        _ensure_aegis_rule_store_schema()
        _bootstrap_legacy_aegis_testing_rules()
        _aegis_tables_ready = True


def ensure_llm_configuration_tables() -> None:
    global _llm_configuration_tables_ready
    if _llm_configuration_tables_ready:
        return
    with _llm_configuration_tables_lock:
        if _llm_configuration_tables_ready:
            return
        from .models import LLMProductConfigurationORM

        Base.metadata.create_all(
            bind=engine,
            tables=[LLMProductConfigurationORM.__table__],
            checkfirst=True,
        )
        _llm_configuration_tables_ready = True


def _ensure_aegis_rule_store_schema() -> None:
    inspector = inspect(aegis_engine)
    if not inspector.has_table("aegis_rule"):
        return
    existing_columns = {column["name"] for column in inspector.get_columns("aegis_rule")}
    if "target_node_name" not in existing_columns:
        with aegis_engine.begin() as connection:
            connection.execute(text("ALTER TABLE aegis_rule ADD COLUMN target_node_name VARCHAR"))


def _bootstrap_legacy_aegis_testing_rules() -> None:
    """Copy already-ingested AEGIS test-pack rules into the scoped AEGIS store."""

    from .models import (
        AegisFileORM,
        AegisHistoryORM,
        AegisRuleORM,
        FileORM,
        HistoryORM,
        RuleORM,
    )

    legacy_inspector = inspect(engine)
    if not legacy_inspector.has_table(RuleORM.__tablename__):
        return

    copy_histories = legacy_inspector.has_table(HistoryORM.__tablename__)
    legacy_db = SessionLocal()
    aegis_db = AegisSessionLocal()
    legacy_rules = []
    try:
        legacy_rules = (
            legacy_db.query(RuleORM)
            .filter(
                or_(
                    RuleORM.category == AEGIS_TEST_CATEGORY,
                    RuleORM.name.like(f"{AEGIS_TEST_RULE_PREFIX}%"),
                )
            )
            .order_by(RuleORM.rule_id)
            .all()
        )
        if not legacy_rules:
            return

        existing_names = {name for (name,) in aegis_db.query(AegisRuleORM.name).all()}
        used_rule_ids = {rule_id for (rule_id,) in aegis_db.query(AegisRuleORM.rule_id).all()}
        used_file_ids = {file_id for (file_id,) in aegis_db.query(AegisFileORM.file_id).all()}
        used_history_ids = {
            history_id for (history_id,) in aegis_db.query(AegisHistoryORM.history_id).all()
        }
        copied_count = 0

        for legacy_rule in legacy_rules:
            if not legacy_rule.name or legacy_rule.name in existing_names:
                continue

            aegis_rule = AegisRuleORM(
                rule_name=legacy_rule.name,
                rule_category=legacy_rule.category,
                rule_description=legacy_rule.description,
            )
            if legacy_rule.rule_id is not None and legacy_rule.rule_id not in used_rule_ids:
                aegis_rule.rule_id = legacy_rule.rule_id
                used_rule_ids.add(legacy_rule.rule_id)
            aegis_db.add(aegis_rule)
            aegis_db.flush()

            for legacy_file in legacy_rule.rule_files.order_by(FileORM.file_id).all():
                aegis_file = AegisFileORM(rule_id=aegis_rule.rule_id, files=legacy_file.files)
                if legacy_file.file_id is not None and legacy_file.file_id not in used_file_ids:
                    aegis_file.file_id = legacy_file.file_id
                    used_file_ids.add(legacy_file.file_id)
                aegis_db.add(aegis_file)

            if copy_histories:
                for legacy_history in legacy_rule.rule_histories.order_by(HistoryORM.history_id).all():
                    aegis_history = AegisHistoryORM(aegis_rule.rule_id, legacy_history.history)
                    if (
                        legacy_history.history_id is not None
                        and legacy_history.history_id not in used_history_ids
                    ):
                        aegis_history.history_id = legacy_history.history_id
                        used_history_ids.add(legacy_history.history_id)
                    aegis_db.add(aegis_history)

            existing_names.add(legacy_rule.name)
            copied_count += 1

        if copied_count:
            aegis_db.commit()
            _logger.info("bootstrapped_aegis_testing_rules", copied_count=copied_count)
        else:
            aegis_db.rollback()
    except SQLAlchemyError as exc:
        aegis_db.rollback()
        if isinstance(exc, IntegrityError):
            expected_names = {rule.name for rule in legacy_rules if rule.name}
            existing_names = {
                name
                for (name,) in aegis_db.query(AegisRuleORM.name)
                .filter(AegisRuleORM.name.in_(expected_names))
                .all()
            }
            if expected_names and expected_names.issubset(existing_names):
                _logger.info(
                    "aegis_rule_store_bootstrap_already_completed",
                    expected_count=len(expected_names),
                )
                return
        _logger.exception("aegis_rule_store_bootstrap_failed", error=str(exc))
        raise
    finally:
        legacy_db.close()
        aegis_db.close()


def get_aegis_db():
    ensure_aegis_rule_store_tables()
    db = AegisSessionLocal()
    try:
        yield db
    finally:
        db.close()
