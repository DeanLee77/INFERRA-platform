from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.config import settings
from src.infrastructure.secrets import read_secret


OPENAI_COMPLETIONS_API = "openai-completions"


@dataclass(frozen=True)
class LLMModelDefinition:
    id: str
    name: str
    context: int


@dataclass(frozen=True)
class LLMProviderDefinition:
    id: str
    name: str
    base_url: str
    api: str
    models: tuple[LLMModelDefinition, ...]
    default_model_id: str
    api_key_env: str
    api_key_settings_attr: Optional[str] = None


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider_id: str
    provider_name: str
    base_url: str
    api: str
    api_key: str
    model_id: str
    model_name: str
    context: int


@dataclass(frozen=True)
class ResolvedLLMMetadata:
    provider_id: str
    provider_name: str
    base_url: str
    api: str
    model_id: str
    model_name: str
    context: int
    secret_status: str
    endpoint_policy: str


BUILT_IN_PROVIDERS: dict[str, LLMProviderDefinition] = {
    "modalResearch": LLMProviderDefinition(
        id="modalResearch",
        name="Modal Research",
        base_url="https://api.us-west-2.modal.direct/v1",
        api=OPENAI_COMPLETIONS_API,
        api_key_env="MODALRESEARCH_API_KEY",
        api_key_settings_attr="MODALRESEARCH_API_KEY",
        default_model_id="zai-org/GLM-5.1-FP8",
        models=(
            LLMModelDefinition(
                id="zai-org/GLM-5-FP8",
                name="GLM-5 FP8",
                context=262144,
            ),
            LLMModelDefinition(
                id="zai-org/GLM-5-FP8-2",
                name="GLM-5-FP8-2",
                context=262144,
            ),
            LLMModelDefinition(
                id="zai-org/GLM-5.1-FP8",
                name="GLM-5.1-FP8",
                context=262144,
            ),
        ),
    ),
    "nvidia": LLMProviderDefinition(
        id="nvidia",
        name="NVIDIA NIM",
        base_url="https://integrate.api.nvidia.com/v1",
        api=OPENAI_COMPLETIONS_API,
        api_key_env="NVIDIA_API_KEY",
        api_key_settings_attr="NVIDIA_API_KEY",
        default_model_id="deepseek-ai/deepseek-v4-pro",
        models=(
            LLMModelDefinition(
                id="openai/gpt-oss-120b",
                name="openai/gpt-oss-120b",
                context=262144,
            ),
            LLMModelDefinition(
                id="qwen/qwen3.5-397b-a17b",
                name="qwen/qwen3.5-397b-a17b",
                context=262144,
            ),
            LLMModelDefinition(
                id="deepseek-ai/deepseek-v4-pro",
                name="deepseek-ai/deepseek-v4-pro",
                context=262144,
            ),
            LLMModelDefinition(
                id="google/gemma-4-31b-it",
                name="google/gemma-4-31b-it",
                context=262144,
            ),
            LLMModelDefinition(
                id="z-ai/glm-5.1",
                name="z-ai/glm-5.1",
                context=262144,
            ),
            LLMModelDefinition(
                id="moonshotai/kimi-k2.6",
                name="moonshotai/kimi-k2.6",
                context=262144,
            ),
        ),
    ),
}


def provider_catalog() -> tuple[LLMProviderDefinition, ...]:
    providers = list(BUILT_IN_PROVIDERS.values())
    legacy = _legacy_zai_provider()
    if legacy is not None:
        providers.append(legacy)
    custom = _custom_provider()
    if custom is not None:
        providers.append(custom)
    return tuple(providers)


def list_provider_catalog(
    *,
    selected_provider_id: Optional[str] = None,
    selected_model_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    selected = select_provider_id(selected_provider_id)
    return [
        {
            "id": provider.id,
            "name": provider.name,
            "base_url": provider.base_url,
            "api": provider.api,
            "configured": bool(_api_key_for(provider)),
            "endpoint_policy": endpoint_policy_for(provider),
            "selected": provider.id == selected,
            "default_model_id": provider.default_model_id,
            "models": [
                {
                    "id": model.id,
                    "name": model.name,
                    "context": model.context,
                    "selected": (
                        provider.id == selected
                        and model.id
                        == select_model_id(provider, selected_model_id)
                    ),
                }
                for model in provider.models
            ],
        }
        for provider in provider_catalog()
    ]


def resolve_llm_metadata(
    provider_id: Optional[str] = None,
    model_id: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[ResolvedLLMMetadata]:
    provider = get_provider(select_provider_id(provider_id))
    if provider is None:
        return None
    model = get_model(provider, select_model_id(provider, model_id))
    effective_base_url = _clean(base_url) or provider.base_url
    effective_api_key = _clean(api_key) or _api_key_for(provider)
    return ResolvedLLMMetadata(
        provider_id=provider.id,
        provider_name=provider.name,
        base_url=effective_base_url,
        api=provider.api,
        model_id=model.id,
        model_name=model.name,
        context=model.context,
        secret_status="configured" if effective_api_key else "missing",
        endpoint_policy="stored_override" if _clean(base_url) else endpoint_policy_for(provider),
    )


def resolve_llm_config(
    provider_id: Optional[str] = None,
    model_id: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[ResolvedLLMConfig]:
    metadata = resolve_llm_metadata(
        provider_id=provider_id,
        model_id=model_id,
        base_url=base_url,
        api_key=api_key,
    )
    if metadata is None:
        return None
    provider = get_provider(metadata.provider_id)
    if provider is None:
        return None
    effective_api_key = _clean(api_key) or _api_key_for(provider)
    if not metadata.base_url or not effective_api_key:
        return None
    return ResolvedLLMConfig(
        provider_id=metadata.provider_id,
        provider_name=metadata.provider_name,
        base_url=metadata.base_url,
        api=metadata.api,
        api_key=effective_api_key,
        model_id=metadata.model_id,
        model_name=metadata.model_name,
        context=metadata.context,
    )


def select_provider_id(provider_id: Optional[str] = None) -> Optional[str]:
    requested = _clean(provider_id) or _clean(settings.INFERRA_LLM_PROVIDER)
    if requested:
        return requested
    for candidate in ("modalResearch", "nvidia"):
        provider = BUILT_IN_PROVIDERS[candidate]
        if _api_key_for(provider):
            return candidate
    if settings.ZAI_BASE_URL or settings.ZAI_API_KEY or settings.ZAI_MODEL:
        return "zai"
    if settings.INFERRA_LLM_BASE_URL or settings.INFERRA_LLM_API_KEY:
        return "custom"
    return None


def select_model_id(provider: LLMProviderDefinition, model_id: Optional[str] = None) -> str:
    requested = _clean(model_id) or _clean(settings.INFERRA_LLM_MODEL)
    if requested:
        return requested
    if provider.id == "zai" and settings.ZAI_MODEL:
        return settings.ZAI_MODEL
    return provider.default_model_id


def get_provider(provider_id: Optional[str]) -> Optional[LLMProviderDefinition]:
    if provider_id is None:
        return None
    for provider in provider_catalog():
        if provider.id == provider_id:
            return provider
    raise ValueError(f"Unknown LLM provider '{provider_id}'")


def get_model(
    provider: LLMProviderDefinition,
    model_id: str,
) -> LLMModelDefinition:
    for model in provider.models:
        if model.id == model_id:
            return model
    raise ValueError(f"Unknown model '{model_id}' for provider '{provider.id}'")


def secret_status_for(provider: LLMProviderDefinition) -> str:
    return "configured" if _api_key_for(provider) else "missing"


def endpoint_policy_for(provider: LLMProviderDefinition) -> str:
    if provider.id in BUILT_IN_PROVIDERS:
        return "read_only"
    return "deployment_managed"


def _api_key_for(provider: LLMProviderDefinition) -> Optional[str]:
    default = (
        getattr(settings, provider.api_key_settings_attr, None)
        if provider.api_key_settings_attr
        else None
    )
    return read_secret(provider.api_key_env, default)


def _legacy_zai_provider() -> Optional[LLMProviderDefinition]:
    if not settings.ZAI_BASE_URL and not settings.ZAI_API_KEY and not settings.ZAI_MODEL:
        return None
    model_id = settings.ZAI_MODEL or "zai-default"
    return LLMProviderDefinition(
        id="zai",
        name="Legacy ZAI",
        base_url=settings.ZAI_BASE_URL or "",
        api=OPENAI_COMPLETIONS_API,
        api_key_env="ZAI_API_KEY",
        api_key_settings_attr="ZAI_API_KEY",
        default_model_id=model_id,
        models=(
            LLMModelDefinition(
                id=model_id,
                name=model_id,
                context=0,
            ),
        ),
    )


def _custom_provider() -> Optional[LLMProviderDefinition]:
    if not settings.INFERRA_LLM_BASE_URL and not settings.INFERRA_LLM_API_KEY:
        return None
    model_id = settings.INFERRA_LLM_MODEL or "custom-model"
    return LLMProviderDefinition(
        id="custom",
        name="Custom OpenAI-Compatible",
        base_url=settings.INFERRA_LLM_BASE_URL or "",
        api=settings.INFERRA_LLM_API,
        api_key_env="INFERRA_LLM_API_KEY",
        api_key_settings_attr="INFERRA_LLM_API_KEY",
        default_model_id=model_id,
        models=(
            LLMModelDefinition(
                id=model_id,
                name=model_id,
                context=0,
            ),
        ),
    )


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
