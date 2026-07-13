from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.infrastructure.llm_secret_encryption import (
    decrypt_llm_api_key,
    encrypt_llm_api_key,
)
from src.infrastructure.logging_config import get_logger

from .models import LLMProductConfigurationORM

_logger = get_logger(__name__)


class LLMProductConfigurationRepository:
    """Persistence adapter for AXIOM/AEGIS LLM settings."""

    def __init__(self, db: Session):
        self._db = db
        self._ensure_table()

    def get(self, product_id: str) -> dict[str, Any] | None:
        config = self._orm(product_id)
        return self._to_dict(config) if config else None

    def upsert(
        self,
        *,
        product_id: str,
        enabled: bool,
        provider_id: str | None,
        provider_name: str | None,
        model_id: str | None,
        model_name: str | None,
        base_url: str | None,
        api: str | None,
        api_key: str | None,
        allowed_operations: list[str],
        budget: dict[str, Any],
        evaluation_gate_status: str,
        updated_by: str | None,
    ) -> dict[str, Any]:
        existing = self._orm(product_id)
        stored_api_key = encrypt_llm_api_key(api_key)
        try:
            if existing is None:
                config = LLMProductConfigurationORM(
                    product_id=product_id,
                    enabled=enabled,
                    provider_id=provider_id,
                    provider_name=provider_name,
                    model_id=model_id,
                    model_name=model_name,
                    base_url=base_url,
                    api=api,
                    api_key=stored_api_key,
                    allowed_operations=allowed_operations,
                    budget=budget,
                    evaluation_gate_status=evaluation_gate_status,
                    updated_by=updated_by,
                )
                self._db.add(config)
            else:
                config = existing
                config.enabled = enabled
                config.provider_id = provider_id
                config.provider_name = provider_name
                config.model_id = model_id
                config.model_name = model_name
                config.base_url = base_url
                config.api = api
                config.api_key = stored_api_key
                config.allowed_operations = allowed_operations
                config.budget = budget
                config.evaluation_gate_status = evaluation_gate_status
                config.updated_by = updated_by
                config.updated_at = datetime.now()
            self._db.commit()
            self._db.refresh(config)
            return self._to_dict(config, api_key=api_key)
        except SQLAlchemyError as exc:
            self._db.rollback()
            _logger.exception(
                "llm_product_configuration_upsert_failed",
                product_id=product_id,
                error=str(exc),
            )
            raise

    def _orm(self, product_id: str) -> LLMProductConfigurationORM | None:
        return (
            self._db.query(LLMProductConfigurationORM)
            .filter_by(product_id=product_id)
            .first()
        )

    def _ensure_table(self) -> None:
        LLMProductConfigurationORM.__table__.metadata.create_all(
            bind=self._db.get_bind(),
            tables=[LLMProductConfigurationORM.__table__],
            checkfirst=True,
        )
        self._ensure_column("base_url")
        self._ensure_column("provider_name")
        self._ensure_column("model_name")
        self._ensure_column("api")
        self._ensure_column("api_key")

    def _ensure_column(self, column_name: str) -> None:
        bind = self._db.get_bind()
        table_name = LLMProductConfigurationORM.__tablename__
        existing = {column["name"] for column in inspect(bind).get_columns(table_name)}
        if column_name in existing:
            return
        with bind.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} VARCHAR"))

    def _read_api_key(self, config: LLMProductConfigurationORM) -> str | None:
        resolved = decrypt_llm_api_key(config.api_key)
        if resolved.needs_rotation:
            config.api_key = encrypt_llm_api_key(resolved.value)
            config.updated_at = datetime.now()
            self._db.commit()
            self._db.refresh(config)
        return resolved.value

    def _to_dict(
        self,
        config: LLMProductConfigurationORM,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        resolved_api_key = api_key if api_key is not None else self._read_api_key(config)
        return {
            "product_id": config.product_id,
            "enabled": bool(config.enabled),
            "provider_id": config.provider_id,
            "provider_name": config.provider_name,
            "model_id": config.model_id,
            "model_name": config.model_name,
            "base_url": config.base_url,
            "api": config.api,
            "api_key": resolved_api_key,
            "allowed_operations": list(config.allowed_operations or []),
            "budget": dict(config.budget or {}),
            "evaluation_gate_status": config.evaluation_gate_status,
            "updated_by": config.updated_by,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }
