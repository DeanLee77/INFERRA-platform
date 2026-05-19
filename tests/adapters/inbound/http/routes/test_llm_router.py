from fastapi.testclient import TestClient

from src.adapters.outbound.llm import provider_registry
from src.main import app


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
