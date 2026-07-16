from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.aegis_rule_repository import (
    AegisRuleRepositoryImpl,
)
from src.adapters.outbound.persistence.aegis_trigger_policy_repository import (
    AegisTriggerPolicyRepository,
)
from src.adapters.outbound.persistence.aegis_workflow_repository import (
    AegisWorkflowConcurrencyError,
    AegisWorkflowRepository,
)
from src.adapters.outbound.persistence.models import (
    AegisFileORM,
    AegisHistoryORM,
    AegisRuleORM,
    AegisTriggerPolicyORM,
    AegisTriggerReceiptORM,
    AegisWorkflowDefinitionORM,
    AegisWorkflowVersionORM,
)
from src.ports.aegis_repository_ports import AegisTriggerIdempotencyConflictError


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(
        bind=engine,
        tables=[
            AegisRuleORM.__table__,
            AegisFileORM.__table__,
            AegisHistoryORM.__table__,
            AegisWorkflowDefinitionORM.__table__,
            AegisWorkflowVersionORM.__table__,
            AegisTriggerPolicyORM.__table__,
            AegisTriggerReceiptORM.__table__,
        ],
    )
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_rule_repository_crud_files_history_and_updates(db):
    repository = AegisRuleRepositoryImpl(db)

    assert repository.find_rule_by_rule_name("") is None
    assert repository.find_id_by_name("missing") is None
    assert repository.find_rule_text_by_rule_name("missing") is None
    assert repository.find_rule_by_rule_name_with_latest_history("missing") is None
    assert repository.find_all_rules() == []

    first_id = repository.create_rule(
        {
            "rule_name": "Rule One",
            "rule_category": "initial",
            "rule_description": "first version",
            "target_node_name": "target one",
        }
    )
    second_id = repository.create_rule(
        {
            "rule_name": "Rule Two",
            "rule_category": "secondary",
            "rule_description": "second rule",
        }
    )
    assert (first_id, second_id) == (1, 2)
    assert repository.find_id_by_name("Rule One") == first_id

    entity = repository.find_rule_by_rule_name("Rule One")
    assert entity.name == "Rule One"
    assert entity.target_node_name == "target one"
    assert repository.find_rule_text_by_rule_name("Rule One") is None

    repository.create_rule_file(first_id, bytearray(b"first content"))
    repository.create_rule_file(first_id, bytearray(b"latest content"))
    repository.create_rule_history(first_id, {"revision": 1})
    repository.create_rule_history(first_id, {"revision": 2})
    assert repository.find_rule_text_by_rule_name("Rule One").files == b"latest content"
    latest = repository.find_rule_by_rule_name_with_latest_history("Rule One")
    assert latest["rule"].rule_id == first_id
    assert latest["history"] == {"revision": 2}

    all_rules = repository.find_all_rules()
    assert [item["name"] for item in all_rules] == ["Rule One", "Rule Two"]
    assert all_rules[0]["targetNodeName"] == "target one"

    assert repository.update_rule_name_and_category("Rule One", "Renamed", "updated") is True
    assert repository.update_rule_name_and_category("missing", "unused", "unused") is False
    assert repository.update_rule_metadata(
        "Renamed", "Renamed", "metadata", "new description"
    ) is True
    assert repository.find_rule_by_rule_name("Renamed").target_node_name == "target one"
    assert repository.update_rule_metadata(
        "Renamed",
        "Renamed",
        "metadata",
        "new description",
        target_node_name="target two",
        update_target=True,
    ) is True
    assert repository.update_rule_target("Renamed", "final target") is True
    assert repository.update_rule_target("missing", "unused") is False

    existing_id = repository.create_rule(
        {
            "rule_name": "Renamed",
            "rule_category": "replaced",
            "rule_description": "replacement metadata",
            "target_node_name": "replacement target",
        }
    )
    assert existing_id == first_id
    updated = repository.find_rule_by_rule_name("Renamed")
    assert (updated.category, updated.description, updated.target_node_name) == (
        "replaced",
        "replacement metadata",
        "replacement target",
    )


@pytest.mark.parametrize(
    ("method", "args", "match"),
    [
        ("create_rule", ({"rule_category": "x"},), "rule_name is required"),
        ("create_rule_file", (None, bytearray(b"x")), "rule_id is required"),
        ("create_rule_file", (1, None), "new_file is required"),
        ("create_rule_history", (None, {}), "rule_id is required"),
        ("create_rule_history", (1, None), "history payload is required"),
    ],
)
def test_rule_repository_validates_required_inputs(db, method, args, match):
    with pytest.raises(ValueError, match=match):
        getattr(AegisRuleRepositoryImpl(db), method)(*args)


@pytest.mark.parametrize(
    "operation",
    [
        "update_rule_name_and_category",
        "update_rule_metadata",
        "create_rule",
        "update_rule_target",
        "create_rule_file",
        "create_rule_history",
    ],
)
def test_rule_repository_rolls_back_sqlalchemy_failures(operation):
    mock_db = MagicMock()
    query = mock_db.query.return_value
    query.filter_by.return_value.first.return_value = None
    query.filter_by.return_value.update.return_value = 1
    mock_db.commit.side_effect = SQLAlchemyError("write failed")
    repository = AegisRuleRepositoryImpl(mock_db)
    repository._next_id = MagicMock(return_value=1)
    calls = {
        "update_rule_name_and_category": ("old", "new", "category"),
        "update_rule_metadata": ("old", "new", "category", "description"),
        "create_rule": ({"rule_name": "new"},),
        "update_rule_target": ("name", "target"),
        "create_rule_file": (1, bytearray(b"content")),
        "create_rule_history": (1, {"revision": 1}),
    }

    with pytest.raises(SQLAlchemyError, match="write failed"):
        getattr(repository, operation)(*calls[operation])

    mock_db.rollback.assert_called_once_with()


def test_rule_repository_rolls_back_existing_rule_metadata_failure():
    mock_db = MagicMock()
    existing = MagicMock(rule_id=7)
    mock_db.query.return_value.filter_by.return_value.first.return_value = existing
    mock_db.commit.side_effect = SQLAlchemyError("update failed")
    repository = AegisRuleRepositoryImpl(mock_db)

    with pytest.raises(SQLAlchemyError, match="update failed"):
        repository.create_rule({"rule_name": "existing"})

    mock_db.rollback.assert_called_once_with()


def _workflow_definition_payload(title="Workflow One", domain="claims"):
    return {
        "id": "workflow-one",
        "title": title,
        "domain": domain,
        "nodes": [],
        "edges": [],
    }


def test_workflow_repository_version_lifecycle_and_concurrency(db):
    repository = AegisWorkflowRepository(db)

    assert repository.list_definitions() == []
    assert repository.get_definition("missing") is None
    assert repository.get_latest_version("missing") is None
    with pytest.raises(LookupError, match="was not found"):
        repository.list_versions("missing")
    with pytest.raises(LookupError, match="was not found"):
        repository.get_version("missing", "v1")

    created = repository.create_definition(
        workflow_id="workflow-one",
        title="Workflow One",
        domain="claims",
        created_by="author",
    )
    assert created["currentVersionHash"] is None
    assert created["createdAt"] is not None
    with pytest.raises(ValueError, match="already exists"):
        repository.create_definition(
            workflow_id="workflow-one",
            title="Duplicate",
            domain="claims",
            created_by=None,
        )
    with pytest.raises(AegisWorkflowConcurrencyError, match="expected stale"):
        repository.append_version(
            workflow_id="workflow-one",
            version_id="v-stale",
            definition_payload=_workflow_definition_payload(),
            validation_snapshot={},
            version_hash="hash-stale",
            graph_hash="graph-stale",
            status="draft",
            expected_version_hash="stale",
        )

    first = repository.append_version(
        workflow_id="workflow-one",
        version_id="v1",
        definition_payload=_workflow_definition_payload(),
        validation_snapshot={"valid": True},
        compile_output=None,
        version_hash="hash-v1",
        graph_hash="graph-v1",
        status="validated",
        created_by="author",
    )
    assert first["version"] == 1
    assert repository.get_latest_version("workflow-one")["versionId"] == "v1"
    assert repository.get_version("workflow-one", "missing") is None

    second = repository.append_version(
        workflow_id="workflow-one",
        version_id="v2",
        definition_payload=_workflow_definition_payload("Workflow Renamed", "benefits"),
        validation_snapshot={"valid": True},
        compile_output={"status": "compiled"},
        version_hash="hash-v2",
        graph_hash="graph-v2",
        status="compiled",
        expected_version_hash="hash-v1",
    )
    assert second["version"] == 2
    assert [item["versionId"] for item in repository.list_versions("workflow-one")] == [
        "v1",
        "v2",
    ]
    definition = repository.get_definition("workflow-one")
    assert definition["title"] == "Workflow Renamed"
    assert definition["domain"] == "benefits"
    assert definition["currentVersionHash"] == "hash-v2"
    assert repository.list_definitions()[0]["graphHash"] == "graph-v2"

    with pytest.raises(LookupError, match="version 'missing'"):
        repository.store_compile_output(
            workflow_id="workflow-one",
            version_id="missing",
            compile_output={},
            status="compiled",
        )
    compiled = repository.store_compile_output(
        workflow_id="workflow-one",
        version_id="v2",
        compile_output={"artifact": "rule text"},
        status="published",
    )
    assert compiled["compileOutput"] == {"artifact": "rule text"}
    assert compiled["status"] == "published"


@pytest.mark.parametrize("operation", ["create", "append", "compile"])
def test_workflow_repository_rolls_back_sqlalchemy_failures(db, monkeypatch, operation):
    repository = AegisWorkflowRepository(db)
    if operation != "create":
        repository.create_definition(
            workflow_id="workflow-one",
            title="Workflow",
            domain="general",
            created_by=None,
        )
    if operation == "compile":
        repository.append_version(
            workflow_id="workflow-one",
            version_id="v1",
            definition_payload=_workflow_definition_payload(),
            validation_snapshot={},
            version_hash="hash-v1",
            graph_hash="graph-v1",
            status="draft",
        )
    rollback = MagicMock(wraps=db.rollback)
    monkeypatch.setattr(db, "rollback", rollback)
    monkeypatch.setattr(db, "commit", MagicMock(side_effect=SQLAlchemyError("write failed")))

    with pytest.raises(SQLAlchemyError, match="write failed"):
        if operation == "create":
            repository.create_definition(
                workflow_id="workflow-failing",
                title="Workflow",
                domain="general",
                created_by=None,
            )
        elif operation == "append":
            repository.append_version(
                workflow_id="workflow-one",
                version_id="v1",
                definition_payload=_workflow_definition_payload(),
                validation_snapshot={},
                version_hash="hash-v1",
                graph_hash="graph-v1",
                status="draft",
            )
        else:
            repository.store_compile_output(
                workflow_id="workflow-one",
                version_id="v1",
                compile_output={},
                status="compiled",
            )

    rollback.assert_called_once_with()


def _policy_kwargs(policy_id="policy-one", *, source_key="source-a", target_key="target-a"):
    return {
        "policy_id": policy_id,
        "version": "1",
        "mode": "governed",
        "source_key": source_key,
        "target_key": target_key,
        "source": {"kind": "event"},
        "target": {"kind": "workflow"},
        "constraints": {"requiresApproval": True},
        "payload": {"name": policy_id},
        "policy_hash": f"hash-{policy_id}",
        "created_by": "author",
    }


def _receipt_kwargs(**overrides):
    values = {
        "trigger_run_id": "trigger-one",
        "policy_id": "policy-one",
        "idempotency_key": "idem-one",
        "event_type": "claim.created",
        "mode": "governed",
        "decision": "execute",
        "status": "completed",
        "source": {"claim": "c1"},
        "target": {"workflow": "w1"},
        "actor": {"id": "system"},
        "facts_passed": {"amount": 10},
        "approval_state": {"status": "granted"},
        "execution": {"status": "done"},
        "guardrail": {"allowed": True},
        "correlation_id": "corr-1",
        "policy_hash": "hash-policy-one",
        "payload": {"request": "payload"},
        "fingerprint": "fingerprint-one",
    }
    values.update(overrides)
    return values


def test_trigger_policy_repository_policy_and_receipt_lifecycle(db):
    repository = AegisTriggerPolicyRepository(db)

    assert repository.get_policy("missing") is None
    assert repository.list_policies() == []
    assert repository.get_receipt_by_idempotency(
        policy_id="policy-one", idempotency_key="missing"
    ) is None

    created = repository.upsert_policy(**_policy_kwargs())
    repository.upsert_policy(
        **_policy_kwargs("policy-two", source_key="source-b", target_key="target-b")
    )
    assert created["policyId"] == "policy-one"
    assert created["createdAt"] is not None
    assert [item["policyId"] for item in repository.list_policies(status="active")] == [
        "policy-one",
        "policy-two",
    ]
    assert repository.find_active_conflict(
        source_key="source-a",
        target_key="target-a",
        exclude_policy_id="policy-one",
    ) is None

    conflict = repository.upsert_policy(
        **_policy_kwargs("policy-conflict", source_key="source-a", target_key="target-a")
    )
    assert repository.find_active_conflict(
        source_key="source-a",
        target_key="target-a",
        exclude_policy_id="policy-one",
    )["policyId"] == conflict["policyId"]

    update = _policy_kwargs()
    update.update(version="2", status="disabled", payload={"name": "updated"})
    updated = repository.upsert_policy(**update)
    assert updated["version"] == "2"
    assert updated["status"] == "disabled"
    assert updated["updatedAt"] is not None
    assert repository.get_policy("policy-one")["payload"] == {"name": "updated"}

    receipt = repository.append_receipt(**_receipt_kwargs())
    assert receipt["idempotentReplay"] is False
    assert receipt["receipt"]["payload"] == {"request": "payload"}
    assert receipt["receipt"]["createdAt"] is not None
    replay = repository.append_receipt(**_receipt_kwargs())
    assert replay["idempotentReplay"] is True
    fetched = repository.get_receipt_by_idempotency(
        policy_id="policy-one", idempotency_key="idem-one"
    )
    assert fetched["receiptHash"].startswith("sha256:")
    with pytest.raises(AegisTriggerIdempotencyConflictError, match="reused"):
        repository.append_receipt(**_receipt_kwargs(fingerprint="different"))


def test_trigger_policy_dict_helpers_handle_empty_values():
    policy = MagicMock(
        policy_id="p",
        version="1",
        status="active",
        mode="m",
        source_key="s",
        target_key="t",
        source=None,
        target=None,
        constraints=None,
        payload=None,
        policy_hash="h",
        created_by=None,
        created_at=None,
        updated_at=None,
    )
    receipt = MagicMock(
        trigger_run_id="r",
        policy_id="p",
        idempotency_key="i",
        event_type="e",
        mode="m",
        decision="d",
        status="s",
        source=None,
        target=None,
        actor=None,
        facts_passed=None,
        approval_state=None,
        execution=None,
        guardrail=None,
        correlation_id=None,
        policy_hash="h",
        receipt_hash="rh",
        payload={"_fingerprint": "hidden"},
        created_at=None,
    )

    assert AegisTriggerPolicyRepository._policy_to_dict(policy)["source"] == {}
    mapped = AegisTriggerPolicyRepository._receipt_to_dict(receipt)
    assert mapped["payload"] == {}
    assert mapped["createdAt"] is None


@pytest.mark.parametrize("operation", ["policy", "receipt"])
def test_trigger_policy_repository_rolls_back_sqlalchemy_failures(monkeypatch, operation):
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    mock_db.commit.side_effect = SQLAlchemyError("write failed")
    repository = AegisTriggerPolicyRepository(mock_db)

    with pytest.raises(SQLAlchemyError, match="write failed"):
        if operation == "policy":
            repository.upsert_policy(**_policy_kwargs())
        else:
            repository.append_receipt(**_receipt_kwargs())

    mock_db.rollback.assert_called_once_with()
