"""Persistence ports used by the AEGIS domain services.

The contracts intentionally exchange primitive dictionaries so the domain
does not depend on SQLAlchemy models or persistence-adapter exception types.
"""

from abc import ABCMeta, abstractmethod
from typing import Any


class AegisTriggerIdempotencyConflictError(ValueError):
    """Raised when a trigger idempotency key is reused with different content."""


class AegisEventLedgerPort(metaclass=ABCMeta):
    @abstractmethod
    def create_workflow_run(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def get_workflow_run(self, run_id: str) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def list_workflow_runs(
        self,
        workflow_id: str | None = None,
    ) -> list[dict[str, Any]]:
        pass  # pragma: no cover

    @abstractmethod
    def get_run_id_for_proposal(self, proposal_id: str) -> str | None:
        pass  # pragma: no cover

    @abstractmethod
    def get_latest_action_proposal(self, run_id: str) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def append_event(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        pass  # pragma: no cover

    @abstractmethod
    def materialize_session_snapshot(
        self,
        run_id: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def get_latest_snapshot(self, run_id: str) -> dict[str, Any] | None:
        pass  # pragma: no cover


class AegisTriggerPolicyPort(metaclass=ABCMeta):
    @abstractmethod
    def upsert_policy(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def get_policy(self, policy_id: str) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def list_policies(
        self,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        pass  # pragma: no cover

    @abstractmethod
    def find_active_conflict(self, **kwargs: Any) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def get_receipt_by_idempotency(self, **kwargs: Any) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def append_receipt(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover


class AegisWorkflowRepositoryPort(metaclass=ABCMeta):
    @abstractmethod
    def list_definitions(self) -> list[dict[str, Any]]:
        pass  # pragma: no cover

    @abstractmethod
    def get_definition(self, workflow_id: str) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def get_latest_version(self, workflow_id: str) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def list_versions(self, workflow_id: str) -> list[dict[str, Any]]:
        pass  # pragma: no cover

    @abstractmethod
    def get_version(
        self,
        workflow_id: str,
        version_id: str,
    ) -> dict[str, Any] | None:
        pass  # pragma: no cover

    @abstractmethod
    def create_definition(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def append_version(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover

    @abstractmethod
    def store_compile_output(self, **kwargs: Any) -> dict[str, Any]:
        pass  # pragma: no cover
