from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

import src.services.llm_configuration_service as configuration_module
from src.services.llm_configuration_service import (
    LLMConfigurationService,
    LLMProductConfigurationError,
    _default_model_for_provider,
    _is_blocked_endpoint_host,
    _is_endpoint_allowlisted,
    _mask_api_key,
    _parse_ip_address,
    _string_list,
    _validate_base_url,
    normalize_product_id,
)


def _configuration(**overrides):
    value = {
        "product_id": "axiom",
        "enabled": True,
        "provider_id": "provider",
        "provider_name": None,
        "model_id": "model",
        "model_name": None,
        "base_url": None,
        "api": None,
        "api_key": "secret-key",
        "allowed_operations": ["goal_mapping"],
        "budget": {},
        "evaluation_gate_status": "pending",
        "updated_by": None,
        "created_at": None,
        "updated_at": None,
    }
    value.update(overrides)
    return value


def _metadata(*, secret_status="configured"):
    return SimpleNamespace(
        provider_id="provider",
        provider_name="Provider",
        model_id="model",
        model_name="Model",
        context=8192,
        api="chat_completions",
        base_url="https://api.example.com",
        endpoint_policy="deployment_managed",
        secret_status=secret_status,
    )


def test_product_normalization_listing_and_snapshot_contract(monkeypatch):
    with pytest.raises(LLMProductConfigurationError, match="Unsupported LLM product"):
        normalize_product_id("unknown")

    service = LLMConfigurationService(MagicMock())
    monkeypatch.setattr(
        service,
        "get_product_state",
        MagicMock(side_effect=lambda product_id: {"product_id": product_id}),
    )
    assert service.list_product_states() == [
        {"product_id": "axiom"},
        {"product_id": "aegis"},
    ]

    state = {
        "product_id": "axiom",
        "enabled": False,
        "configured": False,
        "status": "not_configured",
        "provider_id": None,
        "provider_name": None,
        "model_id": None,
        "model_name": None,
        "context": 0,
        "api": None,
        "base_url": None,
        "endpoint_policy": "deployment_managed",
        "secret_status": "not_applicable",
        "api_key_hint": None,
        "allowed_operations": ["goal_mapping"],
        "budget": {"requests": 10},
        "evaluation_gate_status": "pending",
        "validation_error": None,
    }
    monkeypatch.setattr(service, "get_product_state", MagicMock(return_value=state))

    snapshot = service.snapshot_for_product("axiom")

    assert snapshot["endpoint_url"] is None
    assert snapshot["allowed_operations"] == ["goal_mapping"]
    assert snapshot["budget"] == {"requests": 10}


def test_update_rejects_model_without_provider_and_normalizes_api_and_budget(monkeypatch):
    service = LLMConfigurationService(MagicMock())
    monkeypatch.setattr(
        service,
        "_effective_configuration",
        MagicMock(
            return_value=_configuration(
                enabled=False,
                provider_id=None,
                model_id=None,
                api_key=None,
            )
        ),
    )

    with pytest.raises(LLMProductConfigurationError, match="model_id requires provider_id"):
        service.update_product_configuration("axiom", {"model_id": "orphan-model"})

    assert service._normalized_payload({"api": " responses "}) == {
        "api": "responses"
    }
    with pytest.raises(LLMProductConfigurationError, match="budget must be an object"):
        service._normalized_payload({"budget": ["invalid"]})


def test_effective_configuration_applies_provider_default_models(monkeypatch):
    service = LLMConfigurationService(MagicMock())
    default_model = MagicMock(return_value="provider-default")
    monkeypatch.setattr(configuration_module, "_default_model_for_provider", default_model)

    monkeypatch.setattr(configuration_module.settings, "INFERRA_LLM_PROVIDER", "provider")
    monkeypatch.setattr(configuration_module.settings, "INFERRA_LLM_MODEL", None)
    default = service._effective_configuration("axiom", None)
    assert default["model_id"] == "provider-default"

    monkeypatch.setattr(configuration_module.settings, "INFERRA_LLM_PROVIDER", None)
    stored = service._effective_configuration(
        "axiom",
        {"provider_id": "stored-provider", "model_id": None},
    )
    assert stored["model_id"] == "provider-default"
    assert default_model.call_count == 2


def test_build_state_covers_validation_none_disabled_and_missing_secret_paths(
    monkeypatch,
):
    service = LLMConfigurationService(MagicMock())

    monkeypatch.setattr(
        configuration_module,
        "resolve_llm_metadata",
        MagicMock(side_effect=ValueError("unknown model")),
    )
    invalid = service._build_state(_configuration())
    assert invalid["status"] == "model_unavailable"
    assert invalid["validation_error"] == {
        "code": "model_unavailable",
        "message": "unknown model",
    }

    monkeypatch.setattr(
        configuration_module,
        "resolve_llm_metadata",
        MagicMock(return_value=None),
    )
    unavailable = service._build_state(_configuration())
    assert unavailable["status"] == "not_configured"

    monkeypatch.setattr(
        configuration_module,
        "resolve_llm_metadata",
        MagicMock(return_value=_metadata()),
    )
    disabled = service._build_state(_configuration(enabled=False))
    assert disabled["status"] == "disabled"

    monkeypatch.setattr(
        configuration_module,
        "resolve_llm_config",
        MagicMock(return_value=None),
    )
    missing = service._build_state(_configuration(enabled=True))
    assert missing["status"] == "secret_required"
    assert missing["secret_status"] == "missing"


def test_provider_catalog_and_client_resolution_cover_empty_states(monkeypatch):
    repository = MagicMock()
    service = LLMConfigurationService(repository)
    monkeypatch.setattr(
        service,
        "get_product_state",
        MagicMock(return_value={"provider_id": "provider", "model_id": "model"}),
    )
    catalog = MagicMock(return_value=[{"id": "provider"}])
    monkeypatch.setattr(configuration_module, "list_provider_catalog", catalog)

    assert service.provider_catalog_for_product("axiom") == [{"id": "provider"}]
    catalog.assert_called_once_with(
        selected_provider_id="provider",
        selected_model_id="model",
    )

    monkeypatch.setattr(
        service,
        "_effective_configuration",
        MagicMock(return_value=_configuration(enabled=False)),
    )
    assert service.resolve_product_client_config("axiom") is None

    monkeypatch.setattr(
        service,
        "_effective_configuration",
        MagicMock(return_value=_configuration(enabled=True)),
    )
    monkeypatch.setattr(configuration_module, "_validate_base_url", MagicMock())
    monkeypatch.setattr(
        configuration_module,
        "resolve_llm_config",
        MagicMock(return_value=None),
    )
    assert service.resolve_product_client_config("axiom") is None


def test_default_model_and_base_url_validation_failures(monkeypatch):
    monkeypatch.setattr(
        configuration_module,
        "get_provider",
        MagicMock(side_effect=ValueError("unknown provider")),
    )
    assert _default_model_for_provider("unknown") is None

    with pytest.raises(LLMProductConfigurationError, match="include a hostname"):
        _validate_base_url("http://:80")


def test_endpoint_allowlist_supports_global_url_wildcard_and_exact_host(monkeypatch):
    parsed = urlparse("https://api.example.com/v1")
    monkeypatch.setenv("INFERRA_LLM_ENDPOINT_ALLOWLIST", "*")
    assert _is_endpoint_allowlisted(parsed) is True

    monkeypatch.setenv(
        "INFERRA_LLM_ENDPOINT_ALLOWLIST",
        "https://other.example,*.example.com",
    )
    assert _is_endpoint_allowlisted(parsed) is True

    exact = urlparse("https://api.example.net/v1")
    monkeypatch.setenv("INFERRA_LLM_ENDPOINT_ALLOWLIST", "api.example.net")
    assert _is_endpoint_allowlisted(exact) is True


def test_endpoint_and_scalar_helpers_cover_suffix_unicode_and_short_values():
    assert _is_blocked_endpoint_host("service.internal") is True
    assert _parse_ip_address("²") is None

    default = ["goal_mapping"]
    assert _string_list(None, default) == default
    with pytest.raises(LLMProductConfigurationError, match="must be a list"):
        _string_list(("goal_mapping",), default)

    assert _mask_api_key("abcde") == "***...de"
    assert _mask_api_key("abc") == "****"
