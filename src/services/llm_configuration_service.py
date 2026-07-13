from __future__ import annotations

import ipaddress
import os
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from src.adapters.outbound.llm.provider_registry import (
    ResolvedLLMConfig,
    get_provider,
    list_provider_catalog,
    resolve_llm_config,
    resolve_llm_metadata,
)
from src.config import settings

SUPPORTED_LLM_PRODUCTS = ("axiom", "aegis")
API_KEY_PAYLOAD_FIELDS = ("api_key", "apiKey")
CLEAR_API_KEY_PAYLOAD_FIELDS = ("clear_api_key", "clearApiKey")
SETTINGS_CREDENTIAL_FIELDS = frozenset(
    (*API_KEY_PAYLOAD_FIELDS, *CLEAR_API_KEY_PAYLOAD_FIELDS)
)
SETTINGS_CREDENTIAL_ERROR = (
    "Provider credentials are server-managed and cannot be changed through settings payloads"
)
RUNTIME_ENDPOINT_FIELDS = (
    "base_url",
    "endpoint",
    "endpoint_url",
    "api_base",
    "api_base_url",
)
BLOCKED_ENDPOINT_HOSTNAMES = {
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
}
BLOCKED_ENDPOINT_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
)

DEFAULT_ALLOWED_OPERATIONS: dict[str, list[str]] = {
    "axiom": [
        "document_conversion",
        "goal_mapping",
        "question_prompt",
        "trace_explanation",
        "abduction",
        "ontology_query",
    ],
    "aegis": [
        "advisory_explanation",
        "workflow_authoring_assist",
        "evidence_summary",
    ],
}


class LLMProductConfigurationError(ValueError):
    """Raised when a product LLM configuration is invalid."""


def normalize_product_id(product_id: str) -> str:
    normalized = str(product_id or "").strip().lower()
    if normalized not in SUPPORTED_LLM_PRODUCTS:
        supported = ", ".join(SUPPORTED_LLM_PRODUCTS)
        raise LLMProductConfigurationError(
            f"Unsupported LLM product '{product_id}'. Supported products: {supported}"
        )
    return normalized


class LLMConfigurationService:
    """Build and validate redacted product-level LLM configuration state."""

    def __init__(self, repository):
        self._repository = repository

    def list_product_states(self) -> list[dict[str, Any]]:
        return [self.get_product_state(product_id) for product_id in SUPPORTED_LLM_PRODUCTS]

    def get_product_state(self, product_id: str) -> dict[str, Any]:
        normalized = normalize_product_id(product_id)
        stored = self._repository.get(normalized)
        return self._build_state(self._effective_configuration(normalized, stored))

    def update_product_configuration(
        self,
        product_id: str,
        payload: dict[str, Any],
        *,
        updated_by: str | None = None,
        allow_credential_write: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_product_id(product_id)
        credential_requested = bool(SETTINGS_CREDENTIAL_FIELDS.intersection(payload))
        if credential_requested and not allow_credential_write:
            raise LLMProductConfigurationError(SETTINGS_CREDENTIAL_ERROR)
        endpoint_requested = any(field in payload for field in RUNTIME_ENDPOINT_FIELDS)
        if endpoint_requested and normalized not in ("aegis", "axiom"):
            raise LLMProductConfigurationError(
                "Runtime endpoint changes are not supported; provider endpoints are deployment-managed"
            )

        current = self._effective_configuration(normalized, self._repository.get(normalized))
        normalized_payload = self._normalized_payload(payload)
        candidate = {**current, **normalized_payload}
        provider_changed = (
            "provider_id" in payload
            and current.get("provider_id") != candidate.get("provider_id")
        )
        if "provider_id" in payload and "model_id" not in payload:
            candidate["model_id"] = None
        if provider_changed and not endpoint_requested:
            candidate["base_url"] = None
        if provider_changed and "api_key" not in normalized_payload:
            candidate["api_key"] = None
        if candidate["provider_id"] and not candidate["model_id"]:
            candidate["model_id"] = _default_model_for_provider(candidate["provider_id"])

        if candidate["provider_id"]:
            _validate_base_url(candidate["base_url"])
            resolve_llm_metadata(
                provider_id=candidate["provider_id"],
                model_id=candidate["model_id"],
                base_url=candidate["base_url"],
                api_key=candidate["api_key"],
            )
        elif candidate["model_id"]:
            raise LLMProductConfigurationError("model_id requires provider_id")

        saved = self._repository.upsert(
            product_id=normalized,
            enabled=bool(candidate["enabled"]),
            provider_id=candidate["provider_id"],
            provider_name=candidate["provider_name"],
            model_id=candidate["model_id"],
            model_name=candidate["model_name"],
            base_url=candidate["base_url"],
            api=candidate["api"],
            api_key=candidate["api_key"],
            allowed_operations=list(candidate["allowed_operations"]),
            budget=deepcopy(candidate["budget"]),
            evaluation_gate_status=candidate["evaluation_gate_status"],
            updated_by=updated_by,
        )
        return self._build_state(self._effective_configuration(normalized, saved))

    def snapshot_for_product(self, product_id: str) -> dict[str, Any]:
        state = self.get_product_state(product_id)
        return {
            "product_id": state["product_id"],
            "enabled": state["enabled"],
            "configured": state["configured"],
            "status": state["status"],
            "provider_id": state["provider_id"],
            "provider_name": state["provider_name"],
            "model_id": state["model_id"],
            "model_name": state["model_name"],
            "context": state["context"],
            "api": state["api"],
            "base_url": state["base_url"],
            "endpoint_url": state["base_url"],
            "endpoint_policy": state["endpoint_policy"],
            "secret_status": state["secret_status"],
            "api_key_hint": state.get("api_key_hint"),
            "allowed_operations": list(state["allowed_operations"]),
            "budget": deepcopy(state["budget"]),
            "evaluation_gate_status": state["evaluation_gate_status"],
            "validation_error": deepcopy(state["validation_error"]),
        }

    def _effective_configuration(
        self,
        product_id: str,
        stored: dict[str, Any] | None,
    ) -> dict[str, Any]:
        default_provider_id = _clean(settings.INFERRA_LLM_PROVIDER)
        default_model_id = _clean(settings.INFERRA_LLM_MODEL)
        if default_provider_id and not default_model_id:
            default_model_id = _default_model_for_provider(default_provider_id)
        default = {
            "product_id": product_id,
            "enabled": bool(default_provider_id),
            "provider_id": default_provider_id,
            "provider_name": None,
            "model_id": default_model_id,
            "model_name": None,
            "base_url": None,
            "api": None,
            "api_key": None,
            "allowed_operations": list(DEFAULT_ALLOWED_OPERATIONS[product_id]),
            "budget": {},
            "evaluation_gate_status": "pending",
            "updated_by": None,
            "created_at": None,
            "updated_at": None,
        }
        if not stored:
            return default
        merged = {**default, **stored}
        merged["allowed_operations"] = _string_list(
            merged.get("allowed_operations"),
            default["allowed_operations"],
        )
        merged["budget"] = (
            deepcopy(merged["budget"])
            if isinstance(merged.get("budget"), dict)
            else {}
        )
        merged["provider_id"] = _clean(merged.get("provider_id"))
        merged["provider_name"] = _clean(merged.get("provider_name"))
        merged["model_id"] = _clean(merged.get("model_id"))
        merged["model_name"] = _clean(merged.get("model_name"))
        merged["base_url"] = _clean(merged.get("base_url"))
        merged["api"] = _clean(merged.get("api"))
        merged["api_key"] = _clean(merged.get("api_key"))
        if merged["provider_id"] and not merged["model_id"]:
            merged["model_id"] = _default_model_for_provider(merged["provider_id"])
        merged["evaluation_gate_status"] = _clean(
            merged.get("evaluation_gate_status")
        ) or "pending"
        return merged

    def _build_state(self, config: dict[str, Any]) -> dict[str, Any]:
        provider_id = _clean(config.get("provider_id"))
        provider_name = _clean(config.get("provider_name"))
        model_id = _clean(config.get("model_id"))
        model_name = _clean(config.get("model_name"))
        base_url = _clean(config.get("base_url"))
        api = _clean(config.get("api"))
        api_key = _clean(config.get("api_key"))
        state: dict[str, Any] = {
            "product_id": config["product_id"],
            "enabled": bool(config.get("enabled")),
            "configured": False,
            "status": "not_configured",
            "provider_id": provider_id,
            "provider_name": provider_name,
            "model_id": model_id,
            "model_name": model_name,
            "context": 0,
            "api": api,
            "base_url": base_url,
            "endpoint_url": base_url,
            "endpoint_policy": "deployment_managed",
            "secret_status": "not_applicable",
            "api_key_hint": _mask_api_key(api_key),
            "allowed_operations": list(config["allowed_operations"]),
            "budget": deepcopy(config["budget"]),
            "evaluation_gate_status": config["evaluation_gate_status"],
            "validation_error": None,
            "updated_by": config.get("updated_by"),
            "created_at": config.get("created_at"),
            "updated_at": config.get("updated_at"),
        }
        if provider_id is None:
            return state

        try:
            metadata = resolve_llm_metadata(
                provider_id=provider_id,
                model_id=model_id,
                base_url=config.get("base_url"),
                api_key=api_key,
            )
        except ValueError as exc:
            state["status"] = "model_unavailable" if model_id else "provider_unavailable"
            state["validation_error"] = {
                "code": state["status"],
                "message": str(exc),
            }
            return state

        if metadata is None:
            return state

        state.update(
            {
                "provider_id": metadata.provider_id,
                "provider_name": provider_name or metadata.provider_name,
                "model_id": metadata.model_id,
                "model_name": model_name or metadata.model_name,
                "context": metadata.context,
                "api": api or metadata.api,
                "base_url": metadata.base_url,
                "endpoint_url": metadata.base_url,
                "endpoint_policy": metadata.endpoint_policy,
                "secret_status": metadata.secret_status,
            }
        )
        if not state["enabled"]:
            state["status"] = "disabled"
            return state
        if metadata.secret_status != "configured":
            state["status"] = "secret_required"
            return state
        if resolve_llm_config(
            provider_id=metadata.provider_id,
            model_id=metadata.model_id,
            base_url=config.get("base_url"),
            api_key=api_key,
        ):
            state["configured"] = True
            state["status"] = "configured"
            return state
        state["status"] = "secret_required"
        state["secret_status"] = "missing"
        return state

    @staticmethod
    def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        if "enabled" in payload:
            normalized["enabled"] = bool(payload["enabled"])
        if "provider_id" in payload:
            normalized["provider_id"] = _clean(payload.get("provider_id"))
        if "provider_name" in payload:
            normalized["provider_name"] = _clean(payload.get("provider_name"))
        if "model_id" in payload:
            normalized["model_id"] = _clean(payload.get("model_id"))
        if "model_name" in payload:
            normalized["model_name"] = _clean(payload.get("model_name"))
        for field in RUNTIME_ENDPOINT_FIELDS:
            if field in payload:
                normalized["base_url"] = _clean(payload.get(field))
                break
        if "api" in payload:
            normalized["api"] = _clean(payload.get("api"))
        api_key_field = next(
            (field for field in API_KEY_PAYLOAD_FIELDS if field in payload),
            None,
        )
        clear_api_key = any(
            payload.get(field) is True for field in CLEAR_API_KEY_PAYLOAD_FIELDS
        )
        if api_key_field is not None:
            api_key = _clean(payload.get(api_key_field))
            if api_key and clear_api_key:
                raise LLMProductConfigurationError(
                    "api_key and clear_api_key cannot be set in the same request"
                )
            if api_key:
                normalized["api_key"] = api_key
        if clear_api_key:
            normalized["api_key"] = None
        if "allowed_operations" in payload:
            normalized["allowed_operations"] = _string_list(
                payload.get("allowed_operations"),
                [],
            )
        if "budget" in payload:
            if payload["budget"] is not None and not isinstance(payload["budget"], dict):
                raise LLMProductConfigurationError("budget must be an object")
            normalized["budget"] = deepcopy(payload.get("budget") or {})
        if "evaluation_gate_status" in payload:
            normalized["evaluation_gate_status"] = (
                _clean(payload.get("evaluation_gate_status")) or "pending"
            )
        return normalized

    def provider_catalog_for_product(self, product_id: str) -> list[dict[str, Any]]:
        state = self.get_product_state(product_id)
        return list_provider_catalog(
            selected_provider_id=state["provider_id"],
            selected_model_id=state["model_id"],
        )

    def resolve_product_client_config(self, product_id: str):
        normalized = normalize_product_id(product_id)
        config = self._effective_configuration(
            normalized,
            self._repository.get(normalized),
        )
        if not config["enabled"] or not config["provider_id"]:
            return None
        _validate_base_url(config["base_url"])
        resolved = resolve_llm_config(
            provider_id=config["provider_id"],
            model_id=config["model_id"],
            base_url=config["base_url"],
            api_key=config["api_key"],
        )
        if resolved is None:
            return None
        return ResolvedLLMConfig(
            provider_id=resolved.provider_id,
            provider_name=config["provider_name"] or resolved.provider_name,
            base_url=resolved.base_url,
            api=config["api"] or resolved.api,
            api_key=resolved.api_key,
            model_id=resolved.model_id,
            model_name=config["model_name"] or resolved.model_name,
            context=resolved.context,
        )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _default_model_for_provider(provider_id: str) -> str | None:
    try:
        provider = get_provider(provider_id)
    except ValueError:
        return None
    return provider.default_model_id if provider is not None else None


def _validate_base_url(base_url: str | None) -> None:
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMProductConfigurationError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise LLMProductConfigurationError("base_url must not contain credentials")
    if not parsed.hostname:
        raise LLMProductConfigurationError("base_url must include a hostname")
    if _is_endpoint_allowlisted(parsed):
        return
    if parsed.scheme != "https":
        raise LLMProductConfigurationError(
            "base_url must use HTTPS unless explicitly allowlisted"
        )
    if _is_blocked_endpoint_host(parsed.hostname):
        raise LLMProductConfigurationError(
            "base_url host is not allowed; use a public provider endpoint or INFERRA_LLM_ENDPOINT_ALLOWLIST"
        )


def _is_endpoint_allowlisted(parsed) -> bool:
    host = (parsed.hostname or "").lower().rstrip(".")
    netloc = parsed.netloc.lower()
    target = parsed.geturl().lower().rstrip("/")
    for entry in _endpoint_allowlist_entries():
        if entry == "*":
            return True
        if "://" in entry:
            if target == entry or target.startswith(f"{entry}/"):
                return True
            continue
        if entry.startswith("*.") and (
            host == entry[2:] or host.endswith(entry[1:])
        ):
            return True
        if entry == host or entry == netloc:
            return True
    return False


def _endpoint_allowlist_entries() -> list[str]:
    raw = os.environ.get("INFERRA_LLM_ENDPOINT_ALLOWLIST", "")
    return [item.strip().lower().rstrip("/") for item in raw.split(",") if item.strip()]


def _is_blocked_endpoint_host(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    if host in BLOCKED_ENDPOINT_HOSTNAMES:
        return True
    if any(host.endswith(suffix) for suffix in BLOCKED_ENDPOINT_SUFFIXES):
        return True
    ip_address = _parse_ip_address(host)
    if ip_address is None:
        return False
    return (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_multicast
        or ip_address.is_reserved
        or ip_address.is_unspecified
    )


def _parse_ip_address(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if host.isdigit():
        try:
            value = int(host, 10)
            if 0 <= value <= 2**32 - 1:
                return ipaddress.ip_address(value)
        except ValueError:
            return None
    return None


def _string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list):
        raise LLMProductConfigurationError("allowed_operations must be a list")
    normalized = []
    for item in value:
        text = _clean(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _mask_api_key(api_key: str | None) -> str | None:
    """Return a masked hint like 'sk-...abc4' or None if no key is stored."""
    if not api_key:
        return None
    key = api_key.strip()
    if len(key) <= 8:
        return f"{'*' * len(key[:3])}...{key[-2:]}" if len(key) >= 5 else "****"
    return f"{key[:3]}...{key[-4:]}"
