from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.infrastructure.logging_config import get_logger
from src.ports.aegis_repository_ports import AegisWorkflowRepositoryPort

from .models import AegisWorkflowDefinitionORM, AegisWorkflowVersionORM

_logger = get_logger(__name__)


class AegisWorkflowConcurrencyError(ValueError):
    """Raised when a workflow update is based on a stale version hash."""


class AegisWorkflowRepository(AegisWorkflowRepositoryPort):
    """Persistence adapter for AEGIS workflow authoring definitions and versions."""

    def __init__(self, db: Session):
        self._db = db

    def list_definitions(self) -> list[dict[str, Any]]:
        return [
            self._definition_to_dict(definition)
            for definition in self._db.query(AegisWorkflowDefinitionORM)
            .order_by(AegisWorkflowDefinitionORM.created_at)
            .all()
        ]

    def get_definition(self, workflow_id: str) -> dict[str, Any] | None:
        definition = self._definition_orm(workflow_id)
        return self._definition_to_dict(definition) if definition else None

    def get_latest_version(self, workflow_id: str) -> dict[str, Any] | None:
        version = self._latest_version_orm(workflow_id)
        return self._version_to_dict(version) if version else None

    def list_versions(self, workflow_id: str) -> list[dict[str, Any]]:
        self._require_definition(workflow_id)
        return [
            self._version_to_dict(version)
            for version in self._db.query(AegisWorkflowVersionORM)
            .filter_by(workflow_id=workflow_id)
            .order_by(AegisWorkflowVersionORM.version_number)
            .all()
        ]

    def get_version(self, workflow_id: str, version_id: str) -> dict[str, Any] | None:
        self._require_definition(workflow_id)
        version = (
            self._db.query(AegisWorkflowVersionORM)
            .filter_by(workflow_id=workflow_id, version_id=version_id)
            .first()
        )
        return self._version_to_dict(version) if version else None

    def create_definition(
        self,
        *,
        workflow_id: str,
        title: str,
        domain: str,
        created_by: str | None,
    ) -> dict[str, Any]:
        if self._definition_orm(workflow_id) is not None:
            raise ValueError(f"AEGIS workflow '{workflow_id}' already exists")
        try:
            definition = AegisWorkflowDefinitionORM(
                workflow_id=workflow_id,
                title=title,
                domain=domain,
                created_by=created_by,
            )
            self._db.add(definition)
            self._db.commit()
            self._db.refresh(definition)
            return self._definition_to_dict(definition)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("aegis_workflow_definition_create_failed", workflow_id=workflow_id, error=str(exc))
            raise

    def append_version(
        self,
        *,
        workflow_id: str,
        version_id: str,
        definition_payload: dict[str, Any],
        validation_snapshot: dict[str, Any],
        version_hash: str,
        graph_hash: str,
        status: str,
        expected_version_hash: str | None = None,
        compile_output: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        definition = self._require_definition(workflow_id)
        latest_version = self._latest_version_orm(workflow_id)
        if expected_version_hash and (
            latest_version is None or latest_version.version_hash != expected_version_hash
        ):
            raise AegisWorkflowConcurrencyError(
                f"Workflow '{workflow_id}' changed; expected {expected_version_hash}"
            )

        try:
            version_number = int(definition.version_counter or 0) + 1
            version = AegisWorkflowVersionORM(
                version_id=version_id,
                workflow_id=workflow_id,
                version_number=version_number,
                definition_payload=definition_payload,
                validation_snapshot=validation_snapshot,
                compile_output=compile_output,
                version_hash=version_hash,
                graph_hash=graph_hash,
                status=status,
                created_by=created_by,
            )
            definition.title = str(definition_payload.get("title") or definition.title)
            definition.domain = str(definition_payload.get("domain") or definition.domain)
            definition.status = status
            definition.current_version_id = version_id
            definition.version_counter = version_number
            self._db.add(version)
            self._db.commit()
            self._db.refresh(version)
            return self._version_to_dict(version)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("aegis_workflow_version_append_failed", workflow_id=workflow_id, error=str(exc))
            raise

    def store_compile_output(
        self,
        *,
        workflow_id: str,
        version_id: str,
        compile_output: dict[str, Any],
        status: str,
    ) -> dict[str, Any]:
        definition = self._require_definition(workflow_id)
        version = (
            self._db.query(AegisWorkflowVersionORM)
            .filter_by(workflow_id=workflow_id, version_id=version_id)
            .first()
        )
        if version is None:
            raise LookupError(f"Workflow version '{version_id}' was not found")
        try:
            version.compile_output = compile_output
            version.status = status
            definition.status = status
            definition.current_version_id = version_id
            self._db.commit()
            self._db.refresh(version)
            return self._version_to_dict(version)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception("aegis_workflow_compile_store_failed", workflow_id=workflow_id, error=str(exc))
            raise

    def _definition_orm(self, workflow_id: str) -> AegisWorkflowDefinitionORM | None:
        return self._db.query(AegisWorkflowDefinitionORM).filter_by(workflow_id=workflow_id).first()

    def _require_definition(self, workflow_id: str) -> AegisWorkflowDefinitionORM:
        definition = self._definition_orm(workflow_id)
        if definition is None:
            raise LookupError(f"AEGIS workflow '{workflow_id}' was not found")
        return definition

    def _latest_version_orm(self, workflow_id: str) -> AegisWorkflowVersionORM | None:
        return (
            self._db.query(AegisWorkflowVersionORM)
            .filter_by(workflow_id=workflow_id)
            .order_by(AegisWorkflowVersionORM.version_number.desc())
            .first()
        )

    def _definition_to_dict(self, definition: AegisWorkflowDefinitionORM) -> dict[str, Any]:
        latest_version = self._latest_version_orm(definition.workflow_id)
        return {
            "id": definition.workflow_id,
            "title": definition.title,
            "domain": definition.domain,
            "status": definition.status,
            "isSynthetic": False,
            "currentVersionId": definition.current_version_id,
            "currentVersionHash": latest_version.version_hash if latest_version else None,
            "graphHash": latest_version.graph_hash if latest_version else None,
            "version": latest_version.version_number if latest_version else None,
            "createdBy": definition.created_by,
            "createdAt": definition.created_at.isoformat() if definition.created_at else None,
            "updatedAt": definition.updated_at.isoformat() if definition.updated_at else None,
        }

    @staticmethod
    def _version_to_dict(version: AegisWorkflowVersionORM) -> dict[str, Any]:
        return {
            "versionId": version.version_id,
            "workflowId": version.workflow_id,
            "version": version.version_number,
            "definition": version.definition_payload,
            "validation": version.validation_snapshot,
            "compileOutput": version.compile_output,
            "versionHash": version.version_hash,
            "graphHash": version.graph_hash,
            "status": version.status,
            "createdBy": version.created_by,
            "createdAt": version.created_at.isoformat() if version.created_at else None,
        }
