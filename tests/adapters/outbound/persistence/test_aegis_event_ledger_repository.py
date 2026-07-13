import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.aegis_event_ledger_repository import (
    AegisEventLedgerRepository,
    AegisEventSequenceError,
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
