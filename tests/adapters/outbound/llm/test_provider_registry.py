from src.adapters.outbound.llm import provider_registry
from src.adapters.outbound.llm.client import LLMClient


def test_provider_catalog_exposes_models_without_api_keys(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "MODALRESEARCH_API_KEY", "secret")

    catalog = provider_registry.list_provider_catalog(selected_provider_id="modalResearch")

    modal = next(provider for provider in catalog if provider["id"] == "modalResearch")
    assert modal["configured"] is True
    assert modal["selected"] is True
    assert modal["default_model_id"] == "zai-org/GLM-5.1-FP8"
    assert "secret" not in str(catalog)
    assert {model["id"] for model in modal["models"]} >= {
        "zai-org/GLM-5-FP8",
        "zai-org/GLM-5-FP8-2",
        "zai-org/GLM-5.1-FP8",
    }


def test_resolve_llm_config_uses_provider_specific_key(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_PROVIDER", "nvidia")
    monkeypatch.setattr(provider_registry.settings, "INFERRA_LLM_MODEL", "z-ai/glm-5.1")
    monkeypatch.setattr(provider_registry.settings, "NVIDIA_API_KEY", "secret")

    resolved = provider_registry.resolve_llm_config()

    assert resolved is not None
    assert resolved.provider_id == "nvidia"
    assert resolved.model_id == "z-ai/glm-5.1"
    assert resolved.api_key == "secret"


def test_resolve_llm_config_rejects_unknown_model():
    try:
        provider_registry.resolve_llm_config(
            provider_id="modalResearch",
            model_id="not-a-model",
        )
    except ValueError as exc:
        assert "Unknown model" in str(exc)
    else:
        raise AssertionError("Expected invalid model to raise ValueError")


def test_llm_client_can_be_instantiated_with_per_request_selection(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "MODALRESEARCH_API_KEY", "secret")

    client = LLMClient(
        provider_id="modalResearch",
        model_id="zai-org/GLM-5.1-FP8",
    )

    assert client.client is not None
    assert client.provider_id == "modalResearch"
    assert client.model == "zai-org/GLM-5.1-FP8"
    assert client.context_window == 262144
