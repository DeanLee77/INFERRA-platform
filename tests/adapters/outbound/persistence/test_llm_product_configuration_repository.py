import base64

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.outbound.llm import provider_registry
from src.adapters.outbound.persistence.llm_product_configuration_repository import (
    LLMProductConfigurationRepository,
)
from src.services.llm_configuration_service import LLMConfigurationService


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _fernet_key(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _enable_aegis_key_encryption(monkeypatch, key: str = FERNET_TEST_KEY) -> None:
    monkeypatch.setenv("AEGIS_LLM_API_KEY_ENCRYPTION_KEY", key)
    monkeypatch.delenv("AEGIS_LLM_API_KEY_ENCRYPTION_KEY_FILE", raising=False)
    monkeypatch.delenv("AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS", raising=False)
    monkeypatch.delenv("AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS_FILE", raising=False)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _stored_api_key(db):
    return db.execute(
        text("SELECT api_key FROM llm_product_configuration WHERE product_id = 'aegis'")
    ).scalar_one()


def test_aegis_api_key_is_encrypted_at_rest_and_resolves_for_runtime(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    _enable_aegis_key_encryption(monkeypatch)
    db = _session()
    try:
        repository = LLMProductConfigurationRepository(db)
        repository.upsert(
            product_id="aegis",
            enabled=True,
            provider_id="nvidia",
            provider_name=None,
            model_id="deepseek-ai/deepseek-v4-pro",
            model_name=None,
            base_url="https://aegis-runtime.example.invalid/v1",
            api=None,
            api_key="stored-runtime-secret",
            allowed_operations=["advisory_explanation"],
            budget={},
            evaluation_gate_status="pending",
            updated_by="test-operator",
        )

        stored_api_key = _stored_api_key(db)
        assert stored_api_key.startswith("enc:v1:")
        assert "stored-runtime-secret" not in stored_api_key

        service = LLMConfigurationService(repository)
        resolved = service.resolve_product_client_config("aegis")
        assert resolved is not None
        assert resolved.api_key == "stored-runtime-secret"
    finally:
        db.close()


def test_legacy_plaintext_aegis_key_is_migrated_on_read(monkeypatch):
    _enable_aegis_key_encryption(monkeypatch)
    db = _session()
    try:
        repository = LLMProductConfigurationRepository(db)
        repository.upsert(
            product_id="aegis",
            enabled=True,
            provider_id="nvidia",
            provider_name=None,
            model_id="deepseek-ai/deepseek-v4-pro",
            model_name=None,
            base_url="https://aegis-runtime.example.invalid/v1",
            api=None,
            api_key=None,
            allowed_operations=[],
            budget={},
            evaluation_gate_status="pending",
            updated_by="legacy-test",
        )
        db.execute(
            text(
                "UPDATE llm_product_configuration SET api_key = :api_key "
                "WHERE product_id = 'aegis'"
            ),
            {"api_key": "legacy-plaintext-secret"},
        )
        db.commit()

        loaded = repository.get("aegis")
        assert loaded["api_key"] == "legacy-plaintext-secret"

        stored_api_key = _stored_api_key(db)
        assert stored_api_key.startswith("enc:v1:")
        assert "legacy-plaintext-secret" not in stored_api_key
    finally:
        db.close()


def test_previous_aegis_encryption_key_is_rotated_on_read(monkeypatch):
    old_key = _fernet_key(b"previous-key-material-32-bytes!!")
    _enable_aegis_key_encryption(monkeypatch)
    monkeypatch.setenv("AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS", old_key)
    old_token = "enc:v1:" + Fernet(old_key.encode("ascii")).encrypt(
        b"rotated-runtime-secret"
    ).decode("ascii")
    db = _session()
    try:
        repository = LLMProductConfigurationRepository(db)
        repository.upsert(
            product_id="aegis",
            enabled=True,
            provider_id="nvidia",
            provider_name=None,
            model_id="deepseek-ai/deepseek-v4-pro",
            model_name=None,
            base_url="https://aegis-runtime.example.invalid/v1",
            api=None,
            api_key=None,
            allowed_operations=[],
            budget={},
            evaluation_gate_status="pending",
            updated_by="rotation-test",
        )
        db.execute(
            text(
                "UPDATE llm_product_configuration SET api_key = :api_key "
                "WHERE product_id = 'aegis'"
            ),
            {"api_key": old_token},
        )
        db.commit()

        loaded = repository.get("aegis")
        assert loaded["api_key"] == "rotated-runtime-secret"

        stored_api_key = _stored_api_key(db)
        assert stored_api_key.startswith("enc:v1:")
        assert stored_api_key != old_token
        plaintext = Fernet(FERNET_TEST_KEY.encode("ascii")).decrypt(
            stored_api_key.removeprefix("enc:v1:").encode("ascii")
        )
        assert plaintext == b"rotated-runtime-secret"
    finally:
        db.close()
