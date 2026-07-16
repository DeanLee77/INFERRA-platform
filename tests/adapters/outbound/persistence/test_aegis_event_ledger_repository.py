from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.aegis_event_ledger_repository import (
    AegisEventLedgerRepository,
    AegisEventSequenceError,
    AegisIdempotencyConflictError,
    _dict_value,
    _string_list,
)
from src.adapters.outbound.persistence.models import (
    AegisActionProposalORM,
    AegisEventLedgerEntryORM,
    AegisFileORM,
    AegisHistoryORM,
    AegisRuleORM,
    AegisSessionSnapshotORM,
    AegisWorkflowDefinitionORM,
    AegisWorkflowRunORM,
    AegisWorkflowVersionORM,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _tables():
    return [
        AegisRuleORM.__table__,
        AegisFileORM.__table__,
        AegisHistoryORM.__table__,
        AegisWorkflowDefinitionORM.__table__,
        AegisWorkflowVersionORM.__table__,
        AegisWorkflowRunORM.__table__,
        AegisActionProposalORM.__table__,
        AegisEventLedgerEntryORM.__table__,
        AegisSessionSnapshotORM.__table__,
    ]


def _repository():
    engine = _engine()
    database.Base.metadata.create_all(bind=engine, tables=_tables())
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    return db, AegisEventLedgerRepository(db)


def _proposal_payload():
    return {
        "proposalId": "proposal-robot-1",
        "action": {"kind": "robot.reroute", "target": "AMR-17"},
        "evidenceRefs": ["ev-request"],
        "evidenceHashes": {"ev-request": "sha256:request"},
        "policyHashes": {
            "ruleVersionHash": "sha256:rule-v1",
            "policyVersionHash": "sha256:policy-v1",
            "importTreeHash": "sha256:import-v1",
            "validationStatus": "valid",
        },
        "optionSet": {
            "considered": [
                {"id": "robot-wait", "label": "Wait"},
                {"id": "robot-dock", "label": "Return to dock"},
            ]
        },
        "gateDecision": {"allowed": False, "reason": "Obstacle confidence below certified threshold."},
        "sla": {"state": "met", "deadline": "2026-06-01T00:10:00Z"},
        "approverChain": [{"actorId": "dock-safety-lead", "role": "override authority"}],
    }


def _create_run(repository: AegisEventLedgerRepository):
    return repository.create_workflow_run(
        run_id="run-robot-1",
        workflow_id="workflow-robot",
        workflow_version_id="wfv-1",
        proposal_id="proposal-robot-1",
        proposal_payload=_proposal_payload(),
        actor={"kind": "agent", "id": "planner.alpha", "role": "AI planner"},
        facts={"obstacleConfidence": 0.72, "batteryReservePercent": 61},
        policy_hashes={"graphHash": "sha256:graph-v1"},
    )


def _append_decision_events(repository: AegisEventLedgerRepository):
    repository.append_event(
        run_id="run-robot-1",
        event_type="rule.evaluation.completed",
        idempotency_key="run-robot-1:gate",
        actor={"kind": "system", "id": "aegis-rule-gate", "role": "policy gate"},
        evidence_refs=["ev-obstacle-confidence"],
        policy_hashes={"ruleVersionHash": "sha256:rule-v2", "importTreeHash": "sha256:import-v2"},
        payload={
            "gateDecision": {"allowed": False, "reason": "Below threshold", "confidence": 1.0},
            "evidenceHashes": {"ev-obstacle-confidence": "sha256:obstacle"},
        },
    )
    repository.append_event(
        run_id="run-robot-1",
        event_type="options.generated",
        idempotency_key="run-robot-1:options",
        payload={
            "optionSet": {
                "considered": [
                    {"id": "robot-wait", "status": "available"},
                    {"id": "robot-dock", "status": "available"},
                    {"id": "robot-reroute", "status": "blocked"},
                ],
                "rejectedOptionIds": ["robot-reroute"],
            }
        },
    )
    repository.append_event(
        run_id="run-robot-1",
        event_type="option.selected",
        idempotency_key="run-robot-1:option-selected",
        payload={"selectedOptionId": "robot-dock", "rejectedOptionIds": ["robot-reroute"]},
    )
    repository.append_event(
        run_id="run-robot-1",
        event_type="approval.granted",
        idempotency_key="run-robot-1:approval",
        payload={
            "approval": {"approvalId": "approval-1", "status": "granted"},
            "approverChain": [{"actorId": "dock-safety-lead", "role": "override authority"}],
        },
    )
    repository.append_event(
        run_id="run-robot-1",
        event_type="fallback.not_required",
        idempotency_key="run-robot-1:fallback",
        payload={"fallback": {"state": "not_required", "reason": "Approval granted"}},
    )
    repository.append_event(
        run_id="run-robot-1",
        event_type="receipt.sealed",
        idempotency_key="run-robot-1:receipt",
        payload={
            "runStatus": "sealed",
            "receipt": {"receiptId": "receipt-1", "receiptHash": "sha256:receipt-v1"},
        },
    )


def test_aegis_bootstrap_creates_event_ledger_and_snapshot_tables(monkeypatch):
    legacy_engine = _engine()
    aegis_engine = _engine()
    LegacySession = sessionmaker(autocommit=False, autoflush=False, bind=legacy_engine)
    AegisSession = sessionmaker(autocommit=False, autoflush=False, bind=aegis_engine)

    monkeypatch.setattr(database, "engine", legacy_engine)
    monkeypatch.setattr(database, "aegis_engine", aegis_engine)
    monkeypatch.setattr(database, "SessionLocal", LegacySession)
    monkeypatch.setattr(database, "AegisSessionLocal", AegisSession)
    monkeypatch.setattr(database, "_aegis_tables_ready", False)

    database.ensure_aegis_rule_store_tables()

    table_names = set(inspect(aegis_engine).get_table_names())
    assert {
        "aegis_workflow_run",
        "aegis_action_proposal",
        "aegis_event_ledger_entry",
        "aegis_session_snapshot",
    } <= table_names


def test_append_events_are_ordered_hash_chained_and_idempotent():
    db, repository = _repository()
    try:
        _create_run(repository)

        first = repository.append_event(
            run_id="run-robot-1",
            event_type="rule.evaluation.completed",
            idempotency_key="run-robot-1:gate",
            payload={"gateDecision": {"allowed": False}},
            evidence_refs=["ev-obstacle-confidence"],
        )
        replay = repository.append_event(
            run_id="run-robot-1",
            event_type="rule.evaluation.completed",
            idempotency_key="run-robot-1:gate",
            payload={"gateDecision": {"allowed": False}},
            evidence_refs=["ev-obstacle-confidence"],
        )
        second = repository.append_event(
            run_id="run-robot-1",
            event_type="options.generated",
            idempotency_key="run-robot-1:options",
            sequence=2,
            payload={"optionSet": {"considered": [{"id": "robot-dock"}]}},
        )

        assert first["event"]["sequence"] == 1
        assert first["event"]["previousHash"] == "sha256:aegis-ledger-genesis"
        assert replay["idempotentReplay"] is True
        assert replay["event"]["eventId"] == first["event"]["eventId"]
        assert second["event"]["sequence"] == 2
        assert second["event"]["previousHash"] == first["event"]["eventHash"]
        assert len(repository.list_events("run-robot-1")) == 2

        with pytest.raises(AegisEventSequenceError, match="expected 3, got 4"):
            repository.append_event(
                run_id="run-robot-1",
                event_type="approval.granted",
                idempotency_key="run-robot-1:approval-gap",
                sequence=4,
            )
    finally:
        db.close()


def test_session_snapshot_reconstructs_decision_without_mutable_runtime_state():
    db, repository = _repository()
    try:
        _create_run(repository)
        _append_decision_events(repository)

        stored = repository.materialize_session_snapshot("run-robot-1", snapshot_id="snapshot-robot-1")
        latest = repository.get_latest_snapshot("run-robot-1")
        snapshot = stored["snapshot"]

        assert latest["snapshotId"] == "snapshot-robot-1"
        assert stored["eventSequenceRange"] == [1, 6]
        assert stored["snapshotHash"].startswith("sha256:")
        assert stored["proposalHash"].startswith("sha256:")
        assert stored["evidenceHash"].startswith("sha256:")
        assert stored["policyHash"].startswith("sha256:")
        assert stored["optionSetHash"].startswith("sha256:")
        assert stored["approvalHash"].startswith("sha256:")
        assert stored["fallbackHash"].startswith("sha256:")
        assert stored["receiptHash"] == "sha256:receipt-v1"
        assert stored["importTreeHash"] == "sha256:import-v2"

        assert snapshot["proposal"]["action"]["kind"] == "robot.reroute"
        assert snapshot["actor"]["id"] == "planner.alpha"
        assert snapshot["facts"]["obstacleConfidence"] == 0.72
        assert snapshot["evidence"]["refs"] == ["ev-request", "ev-obstacle-confidence"]
        assert snapshot["evidence"]["hashes"]["ev-obstacle-confidence"] == "sha256:obstacle"
        assert snapshot["policy"]["ruleVersionHash"] == "sha256:rule-v2"
        assert snapshot["policy"]["importTreeHash"] == "sha256:import-v2"
        assert snapshot["options"]["selectedOptionId"] == "robot-dock"
        assert snapshot["options"]["rejectedOptionIds"] == ["robot-reroute"]
        assert snapshot["approval"]["status"] == "granted"
        assert snapshot["approval"]["approverChain"][0]["actorId"] == "dock-safety-lead"
        assert snapshot["fallback"]["state"] == "not_required"
        assert snapshot["sla"]["state"] == "met"
        assert snapshot["gateDecision"]["allowed"] is False
        assert snapshot["receipt"]["receiptHash"] == "sha256:receipt-v1"
    finally:
        db.close()


def test_correction_events_preserve_original_history_and_surface_snapshot_corrections():
    db, repository = _repository()
    try:
        _create_run(repository)
        original = repository.append_event(
            run_id="run-robot-1",
            event_id="evt-gate-original",
            event_type="rule.evaluation.completed",
            idempotency_key="run-robot-1:gate",
            payload={"gateDecision": {"allowed": False, "reason": "Initial sensor confidence"}},
        )

        correction = repository.append_correction(
            run_id="run-robot-1",
            corrects_event_id="evt-gate-original",
            idempotency_key="run-robot-1:gate-correction",
            reason="Sensor confidence rounded in display layer",
            patch={"payload.gateDecision.reason": "Initial sensor confidence rounded down"},
            actor={"kind": "system", "id": "aegis-ledger", "role": "ledger correction authority"},
        )
        events = repository.list_events("run-robot-1")
        snapshot = repository.materialize_session_snapshot("run-robot-1")["snapshot"]

        assert original["event"]["eventId"] == "evt-gate-original"
        assert events[0]["eventId"] == "evt-gate-original"
        assert events[0]["payload"]["gateDecision"]["reason"] == "Initial sensor confidence"
        assert events[0]["correctionOfEventId"] is None
        assert correction["event"]["sequence"] == 2
        assert correction["event"]["correctionOfEventId"] == "evt-gate-original"
        assert snapshot["corrections"] == [
            {
                "eventId": correction["event"]["eventId"],
                "sequence": 2,
                "correctsEventId": "evt-gate-original",
                "reason": "Sensor confidence rounded in display layer",
                "patch": {"payload.gateDecision.reason": "Initial sensor confidence rounded down"},
            }
        ]
        assert [event["eventId"] for event in snapshot["events"]] == [
            "evt-gate-original",
            correction["event"]["eventId"],
        ]
    finally:
        db.close()


def test_run_lookup_listing_validation_and_idempotency_conflict_paths():
    db, repository = _repository()
    try:
        assert repository.get_workflow_run("missing") is None
        assert repository.get_run_id_for_proposal("missing") is None
        assert repository.list_workflow_runs() == []
        assert repository.get_latest_snapshot("missing") is None
        with pytest.raises(LookupError, match="workflow run 'missing'"):
            repository.list_events("missing")
        with pytest.raises(ValueError, match="event_type is required"):
            repository.append_event(
                run_id="missing", event_type=" ", idempotency_key="key"
            )
        with pytest.raises(ValueError, match="idempotency_key is required"):
            repository.append_event(
                run_id="missing", event_type="event", idempotency_key=" "
            )
        with pytest.raises(LookupError, match="event 'missing'"):
            repository.append_correction(
                run_id="missing",
                corrects_event_id="missing",
                idempotency_key="correction",
                reason="reason",
                patch={},
            )

        created = _create_run(repository)
        assert created["runId"] == "run-robot-1"
        assert repository.get_workflow_run("run-robot-1")["workflowId"] == "workflow-robot"
        assert repository.get_run_id_for_proposal("proposal-robot-1") == "run-robot-1"
        assert len(repository.list_workflow_runs()) == 1
        assert len(repository.list_workflow_runs(workflow_id="workflow-robot")) == 1
        assert repository.list_workflow_runs(workflow_id="other") == []
        assert repository.get_latest_action_proposal("run-robot-1")["proposalId"] == "proposal-robot-1"
        with pytest.raises(ValueError, match="already exists"):
            _create_run(repository)

        repository.append_event(
            run_id="run-robot-1",
            event_type="rule.evaluation.completed",
            idempotency_key="same-key",
            payload={"allowed": True},
        )
        with pytest.raises(AegisIdempotencyConflictError, match="different event content"):
            repository.append_event(
                run_id="run-robot-1",
                event_type="rule.evaluation.completed",
                idempotency_key="same-key",
                payload={"allowed": False},
            )
    finally:
        db.close()


def test_latest_action_proposal_requires_a_proposal():
    db, repository = _repository()
    try:
        db.add(
            AegisWorkflowRunORM(
                run_id="run-without-proposal",
                workflow_id="workflow",
            )
        )
        db.commit()

        with pytest.raises(LookupError, match="action proposal"):
            repository.get_latest_action_proposal("run-without-proposal")
    finally:
        db.close()


def test_event_ledger_write_failures_roll_back(monkeypatch):
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    mock_db.commit.side_effect = SQLAlchemyError("write failed")
    repository = AegisEventLedgerRepository(mock_db)

    with pytest.raises(SQLAlchemyError, match="write failed"):
        repository.create_workflow_run(
            run_id="run",
            workflow_id="workflow",
            workflow_version_id=None,
            proposal_id="proposal",
            proposal_payload={},
        )
    mock_db.rollback.assert_called_once_with()

    mock_db.reset_mock()
    mock_db.commit.side_effect = SQLAlchemyError("append failed")
    run = MagicMock(status="running")
    monkeypatch.setattr(repository, "_require_run", lambda _run_id: run)
    monkeypatch.setattr(repository, "_event_by_idempotency", lambda *_args: None)
    monkeypatch.setattr(repository, "_next_sequence", lambda _run_id: 1)
    monkeypatch.setattr(repository, "_latest_event_hash", lambda _run_id: "genesis")
    with pytest.raises(SQLAlchemyError, match="append failed"):
        repository.append_event(
            run_id="run",
            event_type="event",
            idempotency_key="key",
        )
    mock_db.rollback.assert_called_once_with()


def test_snapshot_write_failure_rolls_back(monkeypatch):
    db, repository = _repository()
    try:
        _create_run(repository)
        rollback = MagicMock(wraps=db.rollback)
        monkeypatch.setattr(db, "rollback", rollback)
        monkeypatch.setattr(
            db, "commit", MagicMock(side_effect=SQLAlchemyError("snapshot failed"))
        )

        with pytest.raises(SQLAlchemyError, match="snapshot failed"):
            repository.materialize_session_snapshot("run-robot-1")

        rollback.assert_called_once_with()
    finally:
        db.close()


def test_event_ledger_collection_helpers_are_type_safe():
    source = {"nested": {"value": 1}}
    copied = _dict_value(source)
    copied["nested"]["value"] = 2
    assert source["nested"]["value"] == 1
    assert _dict_value([("not", "a dict")]) == {}
    assert _string_list("not a list") == []
    assert _string_list([1, "two"]) == ["1", "two"]
