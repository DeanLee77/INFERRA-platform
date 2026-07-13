from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.inbound.http.dependencies import get_db_session
from src.adapters.outbound.llm import provider_registry
from src.adapters.outbound.llm.client import LLMClient
from src.adapters.outbound.persistence.llm_product_configuration_repository import (
    LLMProductConfigurationRepository,
)
from src.main import app
from src.services.llm_configuration_service import (
    LLMConfigurationService,
    LLMProductConfigurationError,
)


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _enable_aegis_key_encryption(monkeypatch, key: str = FERNET_TEST_KEY) -> None:
    monkeypatch.setenv("AEGIS_LLM_API_KEY_ENCRYPTION_KEY", key)
    monkeypatch.delenv("AEGIS_LLM_API_KEY_ENCRYPTION_KEY_FILE", raising=False)
    monkeypatch.delenv("AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS", raising=False)
    monkeypatch.delenv("AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS_FILE", raising=False)


def _llm_config_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = _override
    return TestClient(app)


def test_list_llm_providers_returns_redacted_catalog(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "MODALRESEARCH_API_KEY", "secret")
    client = TestClient(app)

    response = client.get("/api/v1/llm/providers")

    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    assert "secret" not in str(body)
    assert any(provider["id"] == "modalResearch" for provider in body["providers"])


def test_resolve_llm_selection_validates_provider_model(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", "secret")
    client = TestClient(app)

    response = client.post(
        "/api/v1/llm/selection/resolve",
        json={"provider_id": "nvidia", "model_id": "z-ai/glm-5.1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "provider_id": "nvidia",
        "provider_name": "NVIDIA NIM",
        "model_id": "z-ai/glm-5.1",
        "model_name": "z-ai/glm-5.1",
        "context": 262144,
        "api": "openai-completions",
    }


def test_resolve_llm_selection_returns_400_for_unknown_model():
    client = TestClient(app)

    response = client.post(
        "/api/v1/llm/selection/resolve",
        json={"provider_id": "nvidia", "model_id": "bad"},
    )

    assert response.status_code == 400


def test_update_axiom_configuration_returns_missing_secret_state(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", None)
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/axiom",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "z-ai/glm-5.1",
                "allowed_operations": ["document_conversion"],
                "budget": {"monthly_usd": 25},
                "evaluation_gate_status": "pending",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["product_id"] == "axiom"
        assert body["status"] == "secret_required"
        assert body["secret_status"] == "missing"
        assert body["configured"] is False
        assert body["provider_id"] == "nvidia"
        assert body["model_id"] == "z-ai/glm-5.1"
        assert body["allowed_operations"] == ["document_conversion"]
        assert body["budget"] == {"monthly_usd": 25}

        read_back = client.get("/api/v1/llm/configuration/axiom")
        assert read_back.status_code == 200
        assert read_back.json()["status"] == "secret_required"
    finally:
        app.dependency_overrides.clear()


def test_update_aegis_configuration_returns_configured_without_raw_secret(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "configured-secret")
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "provider_name": "AEGIS private NVIDIA gateway",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "model_name": "AEGIS DeepSeek guard model",
                "endpoint_url": "https://aegis-llm.example.invalid/v1",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["product_id"] == "aegis"
        assert body["status"] == "configured"
        assert body["secret_status"] == "configured"
        assert body["configured"] is True
        assert body["provider_name"] == "AEGIS private NVIDIA gateway"
        assert body["model_name"] == "AEGIS DeepSeek guard model"
        assert body["base_url"] == "https://aegis-llm.example.invalid/v1"
        assert body["endpoint_url"] == "https://aegis-llm.example.invalid/v1"
        assert "configured-secret" not in str(body)

        read_back = client.get("/api/v1/llm/configuration/aegis")
        assert read_back.status_code == 200
        assert read_back.json()["provider_name"] == "AEGIS private NVIDIA gateway"
        assert read_back.json()["model_name"] == "AEGIS DeepSeek guard model"
        assert read_back.json()["endpoint_url"] == "https://aegis-llm.example.invalid/v1"
    finally:
        app.dependency_overrides.clear()


def test_update_configuration_rejects_invalid_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "configured-secret")
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/axiom",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "bad-model",
            },
        )

        assert response.status_code == 400
        assert "Unknown model" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "top-secret-value"},
        {"apiKey": "top-secret-value"},
        {"clear_api_key": True},
        {"clearApiKey": True},
    ],
)
def test_update_aegis_configuration_rejects_credential_fields_without_secret_write_header(
    payload,
):
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            json=payload,
        )

        assert response.status_code == 400
        assert "server-managed" in response.json()["detail"]
        assert "top-secret-value" not in str(response.json())
    finally:
        app.dependency_overrides.clear()


def test_update_aegis_configuration_accepts_write_only_credential_header(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    _enable_aegis_key_encryption(monkeypatch)
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            headers={"x-inferra-secret-write": "write-only"},
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "api_key": "top-secret-value",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["product_id"] == "aegis"
        assert body["status"] == "configured"
        assert body["secret_status"] == "configured"
        assert body["configured"] is True
        assert "top-secret-value" not in str(body)

        read_back = client.get("/api/v1/llm/configuration/aegis")
        assert read_back.status_code == 200
        assert read_back.json()["status"] == "configured"
        assert "top-secret-value" not in str(read_back.json())
    finally:
        app.dependency_overrides.clear()


def test_update_aegis_configuration_clears_write_only_credential(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    _enable_aegis_key_encryption(monkeypatch)
    client = _llm_config_client()
    try:
        configured = client.put(
            "/api/v1/llm/configuration/aegis",
            headers={"x-inferra-secret-write": "write-only"},
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "api_key": "top-secret-value",
            },
        )
        assert configured.status_code == 200

        cleared = client.put(
            "/api/v1/llm/configuration/aegis",
            headers={"x-inferra-secret-write": "write-only"},
            json={"clearApiKey": True},
        )

        assert cleared.status_code == 200
        body = cleared.json()
        assert body["status"] == "secret_required"
        assert body["secret_status"] == "missing"
        assert body["configured"] is False
        assert "top-secret-value" not in str(body)
    finally:
        app.dependency_overrides.clear()


def test_update_axiom_configuration_rejects_credential_header_without_leaking_value():
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/axiom",
            headers={"x-inferra-secret-write": "write-only"},
            json={"api_key": "top-secret-value"},
        )

        assert response.status_code == 400
        assert "server-managed" in response.json()["detail"]
        assert "top-secret-value" not in str(response.json())
    finally:
        app.dependency_overrides.clear()


def test_update_aegis_configuration_rejects_conflicting_credential_fields_with_header(
    monkeypatch,
):
    _enable_aegis_key_encryption(monkeypatch)
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            headers={"x-inferra-secret-write": "write-only"},
            json={"apiKey": "top-secret-value", "clearApiKey": True},
        )

        assert response.status_code == 400
        assert "api_key and clear_api_key cannot be set" in response.json()["detail"]
        assert "top-secret-value" not in str(response.json())
    finally:
        app.dependency_overrides.clear()


def test_update_axiom_configuration_rejects_credential_payload_without_leaking_value():
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/axiom",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "api_key": "top-secret-value",
            },
        )

        assert response.status_code == 400
        assert "top-secret-value" not in str(response.json())
        assert "server-managed" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_service_rejects_settings_credential_fields_without_leaking_value():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        service = LLMConfigurationService(LLMProductConfigurationRepository(db))

        with pytest.raises(LLMProductConfigurationError) as exc_info:
            service.update_product_configuration(
                "aegis",
                {"api_key": "top-secret-value"},
                updated_by="test-operator",
            )

        assert "server-managed" in str(exc_info.value)
        assert "top-secret-value" not in str(exc_info.value)
    finally:
        db.close()


@pytest.mark.parametrize(
    "endpoint_field",
    [
        "base_url",
        "baseUrl",
        "baseURL",
        "endpoint",
        "endpoint_url",
        "endpointUrl",
        "api_base",
        "apiBase",
        "api_base_url",
        "apiBaseUrl",
    ],
)
def test_update_aegis_configuration_accepts_runtime_endpoint_aliases(
    monkeypatch,
    endpoint_field,
):
    monkeypatch.setenv("NVIDIA_API_KEY", "alias-secret")
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                endpoint_field: "https://example.invalid/v1",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["base_url"] == "https://example.invalid/v1"
        assert body["endpoint_url"] == "https://example.invalid/v1"
        assert body["status"] == "configured"
        assert "alias-secret" not in str(body)
    finally:
        app.dependency_overrides.clear()


def test_aegis_and_axiom_llm_configurations_are_independent(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-secret")
    monkeypatch.setenv("MODALRESEARCH_API_KEY", "modal-secret")
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    client = _llm_config_client()
    try:
        axiom = client.put(
            "/api/v1/llm/configuration/axiom",
            json={
                "enabled": True,
                "provider_id": "modalResearch",
                "model_id": "zai-org/GLM-5.1-FP8",
                "base_url": "https://axiom-llm.example/v1",
            },
        )
        aegis = client.put(
            "/api/v1/llm/configuration/aegis",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "provider_name": "AEGIS provider",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "model_name": "AEGIS model",
                "base_url": "https://aegis-llm.example/v1",
            },
        )

        assert axiom.status_code == 400
        assert aegis.status_code == 200

        axiom_body = client.get("/api/v1/llm/configuration/axiom").json()
        aegis_body = client.get("/api/v1/llm/configuration/aegis").json()
        assert axiom_body["base_url"] is None
        assert aegis_body["provider_id"] == "nvidia"
        assert aegis_body["provider_name"] == "AEGIS provider"
        assert aegis_body["model_id"] == "deepseek-ai/deepseek-v4-pro"
        assert aegis_body["model_name"] == "AEGIS model"
        assert aegis_body["base_url"] == "https://aegis-llm.example/v1"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "base_url",
    ["not-a-url", "ftp://llm.example/v1", "https://user:pass@llm.example/v1"],
)
def test_update_configuration_rejects_invalid_endpoint_without_leaking_secret(
    monkeypatch,
    base_url,
):
    monkeypatch.setenv("NVIDIA_API_KEY", "bad-endpoint-secret")
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "base_url": base_url,
            },
        )

        assert response.status_code == 400
        assert "bad-endpoint-secret" not in str(response.json())
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://llm.example/v1",
        "https://localhost:11434/v1",
        "https://127.0.0.1:11434/v1",
        "https://2130706433/v1",
        "https://10.0.0.5/v1",
        "https://172.16.0.5/v1",
        "https://192.168.1.9/v1",
        "https://169.254.169.254/latest",
        "https://[::1]/v1",
        "https://metadata.google.internal/v1",
    ],
)
def test_update_configuration_rejects_unsafe_endpoint_targets_without_leaking_secret(
    monkeypatch,
    base_url,
):
    monkeypatch.setenv("NVIDIA_API_KEY", "unsafe-endpoint-secret")
    monkeypatch.delenv("INFERRA_LLM_ENDPOINT_ALLOWLIST", raising=False)
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "base_url": base_url,
            },
        )

        assert response.status_code == 400
        assert "unsafe-endpoint-secret" not in str(response.json())
        assert "not allowed" in response.json()["detail"] or "HTTPS" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_update_configuration_allows_explicitly_allowlisted_gateway(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "allowlisted-endpoint-secret")
    monkeypatch.setenv("INFERRA_LLM_ENDPOINT_ALLOWLIST", "http://127.0.0.1:11434")
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/aegis",
            json={
                "enabled": True,
                "provider_id": "nvidia",
                "model_id": "deepseek-ai/deepseek-v4-pro",
                "base_url": "http://127.0.0.1:11434/v1",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["endpoint_url"] == "http://127.0.0.1:11434/v1"
        assert "allowlisted-endpoint-secret" not in str(body)
    finally:
        app.dependency_overrides.clear()


def test_saved_aegis_configuration_resolves_runtime_client_config(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", None)
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", None)
    _enable_aegis_key_encryption(monkeypatch)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        repository = LLMProductConfigurationRepository(db)
        repository.upsert(
            product_id="aegis",
            enabled=True,
            provider_id="nvidia",
            provider_name="AEGIS private NVIDIA gateway",
            model_id="deepseek-ai/deepseek-v4-pro",
            model_name="AEGIS DeepSeek guard model",
            base_url="https://aegis-runtime.example.invalid/v1",
            api=None,
            api_key="stored-runtime-secret",
            allowed_operations=["advisory_explanation"],
            budget={},
            evaluation_gate_status="pending",
            updated_by="test-operator",
        )
        service = LLMConfigurationService(repository)

        resolved = service.resolve_product_client_config("aegis")
        assert resolved is not None
        assert resolved.provider_id == "nvidia"
        assert resolved.provider_name == "AEGIS private NVIDIA gateway"
        assert resolved.model_id == "deepseek-ai/deepseek-v4-pro"
        assert resolved.model_name == "AEGIS DeepSeek guard model"
        assert resolved.base_url == "https://aegis-runtime.example.invalid/v1"
        assert resolved.api_key == "stored-runtime-secret"

        client = LLMClient(resolved_config=resolved)
        assert client.client is not None
        assert client.provider_name == "AEGIS private NVIDIA gateway"
        assert client.model_name == "AEGIS DeepSeek guard model"
        assert client.base_url == "https://aegis-runtime.example.invalid/v1"
    finally:
        db.close()


def test_update_configuration_uses_selected_provider_default_model(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", "deepseek-ai/deepseek-v4-pro")
    monkeypatch.setattr(provider_registry.settings, "MODALRESEARCH_API_KEY", "modal-secret")
    client = _llm_config_client()
    try:
        response = client.put(
            "/api/v1/llm/configuration/axiom",
            json={
                "enabled": True,
                "provider_id": "modalResearch",
            },
        )

        assert response.status_code == 200
        assert response.json()["model_id"] == "zai-org/GLM-5.1-FP8"
        assert response.json()["status"] == "configured"
        assert "modal-secret" not in str(response.json())
    finally:
        app.dependency_overrides.clear()
