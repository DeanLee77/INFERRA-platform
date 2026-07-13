from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.domain.aegis.rule_store import stable_hash
from src.infrastructure.logging_config import get_logger

from .models import AegisTriggerPolicyORM, AegisTriggerReceiptORM

_logger = get_logger(__name__)


class AegisTriggerIdempotencyConflictError(ValueError):
    """Raised when a trigger idempotency key is replayed with different content."""


class AegisTriggerPolicyRepository:
    """SQLAlchemy adapter for governed trigger policies and receipts."""

    def __init__(self, db: Session):
        self._db = db

    def upsert_policy(
        self,
        *,
        policy_id: str,
        version: str,
        mode: str,
        source_key: str,
        target_key: str,
        source: dict[str, Any],
        target: dict[str, Any],
        constraints: dict[str, Any],
        payload: dict[str, Any],
        policy_hash: str,
        status: str = "active",
        created_by: str | None = None,
    ) -> dict[str, Any]:
        existing = self._policy_orm(policy_id)
        try:
            if existing is None:
                policy = AegisTriggerPolicyORM(
                    policy_id=policy_id,
                    version=version,
                    mode=mode,
                    source_key=source_key,
                    target_key=target_key,
                    source=source,
                    target=target,
                    constraints=constraints,
                    payload=payload,
                    policy_hash=policy_hash,
                    status=status,
                    created_by=created_by,
                )
                self._db.add(policy)
            else:
                policy = existing
                policy.version = version
                policy.mode = mode
                policy.status = status
                policy.source_key = source_key
                policy.target_key = target_key
                policy.source = source
                policy.target = target
                policy.constraints = constraints
                policy.payload = payload
                policy.policy_hash = policy_hash
                policy.updated_at = datetime.now()
            self._db.commit()
            self._db.refresh(policy)
            return self._policy_to_dict(policy)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("aegis_trigger_policy_upsert_failed", policy_id=policy_id, error=str(exc))
            raise

    def get_policy(self, policy_id: str) -> dict[str, Any] | None:
        policy = self._policy_orm(policy_id)
        return self._policy_to_dict(policy) if policy else None

    def list_policies(self, *, status: str | None = None) -> list[dict[str, Any]]:
        query = self._db.query(AegisTriggerPolicyORM).order_by(
            AegisTriggerPolicyORM.created_at.asc(),
            AegisTriggerPolicyORM.policy_id.asc(),
        )
        if status:
            query = query.filter_by(status=status)
        return [self._policy_to_dict(policy) for policy in query.all()]

    def find_active_conflict(
        self,
        *,
        source_key: str,
        target_key: str,
        exclude_policy_id: str,
    ) -> dict[str, Any] | None:
        policy = (
            self._db.query(AegisTriggerPolicyORM)
            .filter_by(source_key=source_key, target_key=target_key, status="active")
            .filter(AegisTriggerPolicyORM.policy_id != exclude_policy_id)
            .first()
        )
        return self._policy_to_dict(policy) if policy else None

    def get_receipt_by_idempotency(
        self,
        *,
        policy_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        receipt = (
            self._db.query(AegisTriggerReceiptORM)
            .filter_by(policy_id=policy_id, idempotency_key=idempotency_key)
            .first()
        )
        return self._receipt_to_dict(receipt) if receipt else None

    def append_receipt(
        self,
        *,
        trigger_run_id: str,
        policy_id: str,
        idempotency_key: str,
        event_type: str,
        mode: str,
        decision: str,
        status: str,
        source: dict[str, Any],
        target: dict[str, Any],
        actor: dict[str, Any],
        facts_passed: dict[str, Any],
        approval_state: dict[str, Any],
        execution: dict[str, Any],
        guardrail: dict[str, Any],
        correlation_id: str | None,
        policy_hash: str,
        payload: dict[str, Any],
        fingerprint: str,
    ) -> dict[str, Any]:
        existing = self._receipt_orm(policy_id, idempotency_key)
        if existing is not None:
            if (existing.payload or {}).get("_fingerprint") != fingerprint:
                raise AegisTriggerIdempotencyConflictError(
                    f"Trigger idempotency key '{idempotency_key}' was reused with different content"
                )
            return {"receipt": self._receipt_to_dict(existing), "idempotentReplay": True}

        receipt_payload = deepcopy(payload)
        receipt_payload["_fingerprint"] = fingerprint
        receipt_hash = stable_hash(
            {
                "triggerRunId": trigger_run_id,
                "policyId": policy_id,
                "idempotencyKey": idempotency_key,
                "eventType": event_type,
                "mode": mode,
                "decision": decision,
                "status": status,
                "source": source,
                "target": target,
                "actor": actor,
                "factsPassed": facts_passed,
                "approvalState": approval_state,
                "execution": execution,
                "guardrail": guardrail,
                "correlationId": correlation_id,
                "policyHash": policy_hash,
                "payload": receipt_payload,
            }
        )
        try:
            receipt = AegisTriggerReceiptORM(
                trigger_run_id=trigger_run_id,
                policy_id=policy_id,
                idempotency_key=idempotency_key,
                event_type=event_type,
                mode=mode,
                decision=decision,
                status=status,
                source=source,
                target=target,
                actor=actor,
                facts_passed=facts_passed,
                approval_state=approval_state,
                execution=execution,
                guardrail=guardrail,
                correlation_id=correlation_id,
                policy_hash=policy_hash,
                receipt_hash=receipt_hash,
                payload=receipt_payload,
            )
            self._db.add(receipt)
            self._db.commit()
            self._db.refresh(receipt)
            return {"receipt": self._receipt_to_dict(receipt), "idempotentReplay": False}
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception(
                "aegis_trigger_receipt_append_failed",
                policy_id=policy_id,
                idempotency_key=idempotency_key,
                error=str(exc),
            )
            raise

    def _policy_orm(self, policy_id: str) -> AegisTriggerPolicyORM | None:
        return self._db.query(AegisTriggerPolicyORM).filter_by(policy_id=policy_id).first()

    def _receipt_orm(self, policy_id: str, idempotency_key: str) -> AegisTriggerReceiptORM | None:
        return (
            self._db.query(AegisTriggerReceiptORM)
            .filter_by(policy_id=policy_id, idempotency_key=idempotency_key)
            .first()
        )

    @staticmethod
    def _policy_to_dict(policy: AegisTriggerPolicyORM) -> dict[str, Any]:
        return {
            "policyId": policy.policy_id,
            "version": policy.version,
            "status": policy.status,
            "mode": policy.mode,
            "sourceKey": policy.source_key,
            "targetKey": policy.target_key,
            "source": deepcopy(policy.source or {}),
            "target": deepcopy(policy.target or {}),
            "constraints": deepcopy(policy.constraints or {}),
            "payload": deepcopy(policy.payload or {}),
            "policyHash": policy.policy_hash,
            "createdBy": policy.created_by,
            "createdAt": policy.created_at.isoformat() if policy.created_at else None,
            "updatedAt": policy.updated_at.isoformat() if policy.updated_at else None,
        }

    @staticmethod
    def _receipt_to_dict(receipt: AegisTriggerReceiptORM) -> dict[str, Any]:
        payload = deepcopy(receipt.payload or {})
        payload.pop("_fingerprint", None)
        return {
            "triggerRunId": receipt.trigger_run_id,
            "policyId": receipt.policy_id,
            "idempotencyKey": receipt.idempotency_key,
            "eventType": receipt.event_type,
            "mode": receipt.mode,
            "decision": receipt.decision,
            "status": receipt.status,
            "source": deepcopy(receipt.source or {}),
            "target": deepcopy(receipt.target or {}),
            "actor": deepcopy(receipt.actor or {}),
            "factsPassed": deepcopy(receipt.facts_passed or {}),
            "approvalState": deepcopy(receipt.approval_state or {}),
            "execution": deepcopy(receipt.execution or {}),
            "guardrail": deepcopy(receipt.guardrail or {}),
            "correlationId": receipt.correlation_id,
            "policyHash": receipt.policy_hash,
            "receiptHash": receipt.receipt_hash,
            "payload": payload,
            "createdAt": receipt.created_at.isoformat() if receipt.created_at else None,
        }
