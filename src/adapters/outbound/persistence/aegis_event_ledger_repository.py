from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.domain.aegis.rule_store import stable_hash
from src.domain.aegis.session_snapshot import build_session_snapshot
from src.infrastructure.logging_config import get_logger

from .models import (
    AegisActionProposalORM,
    AegisEventLedgerEntryORM,
    AegisSessionSnapshotORM,
    AegisWorkflowRunORM,
)

_logger = get_logger(__name__)

GENESIS_EVENT_HASH = "sha256:aegis-ledger-genesis"


class AegisEventSequenceError(ValueError):
    """Raised when a ledger append would create a sequence gap."""


class AegisIdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused with different event content."""


class AegisEventLedgerRepository:
    """SQLAlchemy adapter for persistent AEGIS event ledger and snapshots."""

    def __init__(self, db: Session):
        self._db = db

    def create_workflow_run(
        self,
        *,
        run_id: str,
        workflow_id: str,
        workflow_version_id: str | None,
        proposal_id: str,
        proposal_payload: dict[str, Any],
        actor: dict[str, Any] | None = None,
        facts: dict[str, Any] | None = None,
        policy_hashes: dict[str, Any] | None = None,
        status: str = "running",
    ) -> dict[str, Any]:
        if self._run_orm(run_id) is not None:
            raise ValueError(f"AEGIS workflow run '{run_id}' already exists")
        try:
            run = AegisWorkflowRunORM(
                run_id=run_id,
                workflow_id=workflow_id,
                workflow_version_id=workflow_version_id,
                status=status,
                actor=actor,
                facts=facts,
                policy_hashes=policy_hashes,
            )
            proposal = AegisActionProposalORM(
                proposal_id=proposal_id,
                run_id=run_id,
                proposal_payload=proposal_payload,
                actor=actor,
                facts=facts,
                evidence_refs=_string_list(proposal_payload.get("evidenceRefs")),
                policy_hashes=_dict_value(policy_hashes) | _dict_value(proposal_payload.get("policyHashes")),
                option_set=_dict_value(proposal_payload.get("optionSet")),
                gate_decision=_dict_value(proposal_payload.get("gateDecision")),
            )
            self._db.add(run)
            self._db.add(proposal)
            self._db.commit()
            self._db.refresh(run)
            return self._run_to_dict(run)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("aegis_workflow_run_create_failed", run_id=run_id, error=str(exc))
            raise

    def get_workflow_run(self, run_id: str) -> dict[str, Any] | None:
        run = self._run_orm(run_id)
        return self._run_to_dict(run) if run else None

    def list_workflow_runs(self) -> list[dict[str, Any]]:
        runs = (
            self._db.query(AegisWorkflowRunORM)
            .order_by(AegisWorkflowRunORM.created_at.asc(), AegisWorkflowRunORM.run_id.asc())
            .all()
        )
        return [self._run_to_dict(run) for run in runs]

    def get_run_id_for_proposal(self, proposal_id: str) -> str | None:
        proposal = self._db.query(AegisActionProposalORM).filter_by(proposal_id=proposal_id).first()
        return proposal.run_id if proposal else None

    def list_workflow_runs(self, workflow_id: str | None = None) -> list[dict[str, Any]]:
        query = self._db.query(AegisWorkflowRunORM).order_by(AegisWorkflowRunORM.created_at.desc())
        if workflow_id:
            query = query.filter_by(workflow_id=workflow_id)
        return [self._run_to_dict(run) for run in query.all()]

    def get_latest_action_proposal(self, run_id: str) -> dict[str, Any]:
        proposal = self._latest_action_proposal(run_id)
        return self._proposal_to_dict(proposal)

    def append_event(
        self,
        *,
        run_id: str,
        event_type: str,
        idempotency_key: str,
        actor: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        evidence_refs: list[str] | None = None,
        policy_hashes: dict[str, Any] | None = None,
        option_set: dict[str, Any] | None = None,
        approval_state: dict[str, Any] | None = None,
        fallback_state: dict[str, Any] | None = None,
        receipt: dict[str, Any] | None = None,
        pre_state: dict[str, Any] | None = None,
        sequence: int | None = None,
        event_id: str | None = None,
        correction_of_event_id: str | None = None,
    ) -> dict[str, Any]:
        if not event_type.strip():
            raise ValueError("event_type is required")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")

        run = self._require_run(run_id)
        existing = self._event_by_idempotency(run_id, idempotency_key)
        candidate_fingerprint = self._event_fingerprint(
            event_type=event_type,
            actor=actor,
            payload=payload,
            evidence_refs=evidence_refs,
            policy_hashes=policy_hashes,
            option_set=option_set,
            approval_state=approval_state,
            fallback_state=fallback_state,
            receipt=receipt,
            correction_of_event_id=correction_of_event_id,
        )
        if existing is not None:
            if existing.payload.get("_fingerprint") != candidate_fingerprint:
                raise AegisIdempotencyConflictError(
                    f"Idempotency key '{idempotency_key}' was reused with different event content"
                )
            return {"event": self._event_to_dict(existing), "idempotentReplay": True, "run": self._run_to_dict(run)}

        next_sequence = self._next_sequence(run_id)
        if sequence is not None and int(sequence) != next_sequence:
            raise AegisEventSequenceError(
                f"AEGIS event sequence for run '{run_id}' expected {next_sequence}, got {sequence}"
            )

        previous_hash = self._latest_event_hash(run_id)
        event_payload = deepcopy(payload or {})
        event_payload["_fingerprint"] = candidate_fingerprint
        event_hash = stable_hash(
            {
                "runId": run_id,
                "sequence": next_sequence,
                "type": event_type,
                "actor": actor or {},
                "payload": event_payload,
                "evidenceRefs": evidence_refs or [],
                "policyHashes": policy_hashes or {},
                "previousHash": previous_hash,
                "correctionOfEventId": correction_of_event_id,
            }
        )
        try:
            event = AegisEventLedgerEntryORM(
                event_id=event_id or f"aegis_evt_{uuid4().hex}",
                run_id=run_id,
                sequence=next_sequence,
                idempotency_key=idempotency_key,
                event_type=event_type,
                actor=actor,
                payload=event_payload,
                pre_state=pre_state,
                evidence_refs=evidence_refs,
                policy_hashes=policy_hashes,
                option_set=option_set,
                approval_state=approval_state,
                fallback_state=fallback_state,
                receipt=receipt,
                previous_hash=previous_hash,
                event_hash=event_hash,
                correction_of_event_id=correction_of_event_id,
            )
            run.updated_at = datetime.now()
            if isinstance(event_payload.get("runStatus"), str):
                run.status = event_payload["runStatus"]
            self._db.add(event)
            self._db.commit()
            self._db.refresh(event)
            self._db.refresh(run)
            return {"event": self._event_to_dict(event), "idempotentReplay": False, "run": self._run_to_dict(run)}
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception(
                "aegis_event_ledger_append_failed",
                run_id=run_id,
                idempotency_key=idempotency_key,
                error=str(exc),
            )
            raise

    def append_correction(
        self,
        *,
        run_id: str,
        corrects_event_id: str,
        idempotency_key: str,
        reason: str,
        patch: dict[str, Any],
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = (
            self._db.query(AegisEventLedgerEntryORM)
            .filter_by(run_id=run_id, event_id=corrects_event_id)
            .first()
        )
        if target is None:
            raise LookupError(f"AEGIS event '{corrects_event_id}' was not found")
        return self.append_event(
            run_id=run_id,
            event_type="ledger.correction.appended",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "correctsEventId": corrects_event_id,
                "reason": reason,
                "patch": patch,
            },
            correction_of_event_id=corrects_event_id,
        )

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        self._require_run(run_id)
        return [
            self._event_to_dict(event)
            for event in self._db.query(AegisEventLedgerEntryORM)
            .filter_by(run_id=run_id)
            .order_by(AegisEventLedgerEntryORM.sequence)
            .all()
        ]

    def materialize_session_snapshot(self, run_id: str, snapshot_id: str | None = None) -> dict[str, Any]:
        run = self._require_run(run_id)
        proposal = self._latest_action_proposal(run_id)
        events = self.list_events(run_id)
        snapshot_payload = build_session_snapshot(
            run=self._run_to_dict(run),
            action_proposal=self._proposal_to_dict(proposal),
            events=events,
        )
        section_hashes = snapshot_payload["sectionHashes"]
        sequence_range = snapshot_payload["run"]["eventSequenceRange"]
        snapshot = AegisSessionSnapshotORM(
            snapshot_id=snapshot_id or f"aegis_snapshot_{uuid4().hex}",
            run_id=run_id,
            event_sequence_start=int(sequence_range[0]),
            event_sequence_end=int(sequence_range[1]),
            snapshot_hash=snapshot_payload["snapshotHash"],
            proposal_hash=section_hashes["proposalHash"],
            evidence_hash=section_hashes["evidenceHash"],
            policy_hash=section_hashes["policyHash"],
            import_tree_hash=snapshot_payload["policy"].get("importTreeHash"),
            option_set_hash=section_hashes["optionSetHash"],
            approval_hash=section_hashes["approvalHash"],
            fallback_hash=section_hashes["fallbackHash"],
            receipt_hash=section_hashes["receiptHash"],
            snapshot_payload=snapshot_payload,
        )
        try:
            self._db.add(snapshot)
            self._db.commit()
            self._db.refresh(snapshot)
            return self._snapshot_to_dict(snapshot)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("aegis_session_snapshot_materialize_failed", run_id=run_id, error=str(exc))
            raise

    def get_latest_snapshot(self, run_id: str) -> dict[str, Any] | None:
        snapshot = (
            self._db.query(AegisSessionSnapshotORM)
            .filter_by(run_id=run_id)
            .order_by(AegisSessionSnapshotORM.created_at.desc())
            .first()
        )
        return self._snapshot_to_dict(snapshot) if snapshot else None

    def _run_orm(self, run_id: str) -> AegisWorkflowRunORM | None:
        return self._db.query(AegisWorkflowRunORM).filter_by(run_id=run_id).first()

    def _require_run(self, run_id: str) -> AegisWorkflowRunORM:
        run = self._run_orm(run_id)
        if run is None:
            raise LookupError(f"AEGIS workflow run '{run_id}' was not found")
        return run

    def _latest_action_proposal(self, run_id: str) -> AegisActionProposalORM:
        proposal = (
            self._db.query(AegisActionProposalORM)
            .filter_by(run_id=run_id)
            .order_by(AegisActionProposalORM.created_at.desc())
            .first()
        )
        if proposal is None:
            raise LookupError(f"AEGIS action proposal for run '{run_id}' was not found")
        return proposal

    def _event_by_idempotency(self, run_id: str, idempotency_key: str) -> AegisEventLedgerEntryORM | None:
        return (
            self._db.query(AegisEventLedgerEntryORM)
            .filter_by(run_id=run_id, idempotency_key=idempotency_key)
            .first()
        )

    def _next_sequence(self, run_id: str) -> int:
        latest_sequence = (
            self._db.query(func.max(AegisEventLedgerEntryORM.sequence))
            .filter_by(run_id=run_id)
            .scalar()
        )
        return int(latest_sequence or 0) + 1

    def _latest_event_hash(self, run_id: str) -> str:
        event = (
            self._db.query(AegisEventLedgerEntryORM)
            .filter_by(run_id=run_id)
            .order_by(AegisEventLedgerEntryORM.sequence.desc())
            .first()
        )
        return event.event_hash if event else GENESIS_EVENT_HASH

    @staticmethod
    def _event_fingerprint(
        *,
        event_type: str,
        actor: dict[str, Any] | None,
        payload: dict[str, Any] | None,
        evidence_refs: list[str] | None,
        policy_hashes: dict[str, Any] | None,
        option_set: dict[str, Any] | None,
        approval_state: dict[str, Any] | None,
        fallback_state: dict[str, Any] | None,
        receipt: dict[str, Any] | None,
        correction_of_event_id: str | None,
    ) -> str:
        return stable_hash(
            {
                "type": event_type,
                "actor": actor or {},
                "payload": payload or {},
                "evidenceRefs": evidence_refs or [],
                "policyHashes": policy_hashes or {},
                "optionSet": option_set or {},
                "approvalState": approval_state or {},
                "fallbackState": fallback_state or {},
                "receipt": receipt or {},
                "correctionOfEventId": correction_of_event_id,
            }
        )

    @staticmethod
    def _run_to_dict(run: AegisWorkflowRunORM) -> dict[str, Any]:
        return {
            "runId": run.run_id,
            "workflowId": run.workflow_id,
            "workflowVersionId": run.workflow_version_id,
            "status": run.status,
            "actor": deepcopy(run.actor or {}),
            "facts": deepcopy(run.facts or {}),
            "policyHashes": deepcopy(run.policy_hashes or {}),
            "createdAt": run.created_at.isoformat() if run.created_at else None,
            "updatedAt": run.updated_at.isoformat() if run.updated_at else None,
        }

    @staticmethod
    def _proposal_to_dict(proposal: AegisActionProposalORM) -> dict[str, Any]:
        proposal_payload = deepcopy(proposal.proposal_payload or {})
        return {
            "proposalId": proposal.proposal_id,
            "runId": proposal.run_id,
            "proposal": proposal_payload,
            "actor": deepcopy(proposal.actor or {}),
            "facts": deepcopy(proposal.facts or {}),
            "evidenceRefs": deepcopy(proposal.evidence_refs or []),
            "evidenceHashes": deepcopy(proposal_payload.get("evidenceHashes") or {}),
            "policyHashes": deepcopy(proposal.policy_hashes or {}),
            "optionSet": deepcopy(proposal.option_set or {}),
            "gateDecision": deepcopy(proposal.gate_decision or {}),
            "approval": deepcopy(proposal_payload.get("approval") or {}),
            "approverChain": deepcopy(proposal_payload.get("approverChain") or []),
            "fallback": deepcopy(proposal_payload.get("fallback") or {}),
            "sla": deepcopy(proposal_payload.get("sla") or {}),
            "receipt": deepcopy(proposal_payload.get("receipt") or {}),
            "receiptHash": proposal_payload.get("receiptHash"),
            "createdAt": proposal.created_at.isoformat() if proposal.created_at else None,
        }

    @staticmethod
    def _event_to_dict(event: AegisEventLedgerEntryORM) -> dict[str, Any]:
        payload = deepcopy(event.payload or {})
        payload.pop("_fingerprint", None)
        return {
            "eventId": event.event_id,
            "runId": event.run_id,
            "sequence": event.sequence,
            "idempotencyKey": event.idempotency_key,
            "type": event.event_type,
            "actor": deepcopy(event.actor or {}),
            "payload": payload,
            "preState": deepcopy(event.pre_state or {}),
            "evidenceRefs": deepcopy(event.evidence_refs or []),
            "policyHashes": deepcopy(event.policy_hashes or {}),
            "optionSet": deepcopy(event.option_set or {}),
            "approvalState": deepcopy(event.approval_state or {}),
            "fallbackState": deepcopy(event.fallback_state or {}),
            "receipt": deepcopy(event.receipt or {}),
            "previousHash": event.previous_hash,
            "eventHash": event.event_hash,
            "correctionOfEventId": event.correction_of_event_id,
            "createdAt": event.created_at.isoformat() if event.created_at else None,
        }

    @staticmethod
    def _snapshot_to_dict(snapshot: AegisSessionSnapshotORM) -> dict[str, Any]:
        return {
            "snapshotId": snapshot.snapshot_id,
            "runId": snapshot.run_id,
            "eventSequenceRange": [snapshot.event_sequence_start, snapshot.event_sequence_end],
            "snapshotHash": snapshot.snapshot_hash,
            "proposalHash": snapshot.proposal_hash,
            "evidenceHash": snapshot.evidence_hash,
            "policyHash": snapshot.policy_hash,
            "importTreeHash": snapshot.import_tree_hash,
            "optionSetHash": snapshot.option_set_hash,
            "approvalHash": snapshot.approval_hash,
            "fallbackHash": snapshot.fallback_hash,
            "receiptHash": snapshot.receipt_hash,
            "snapshot": deepcopy(snapshot.snapshot_payload or {}),
            "createdAt": snapshot.created_at.isoformat() if snapshot.created_at else None,
        }


def _dict_value(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
