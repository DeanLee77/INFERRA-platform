from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.adapters.inbound.http.dependencies import get_db_session, require_scope
from src.adapters.outbound.llm.provider_registry import (
    list_provider_catalog,
    resolve_llm_config,
)
from src.adapters.outbound.persistence.llm_product_configuration_repository import (
    LLMProductConfigurationRepository,
)
from src.services.llm_configuration_service import (
    LLMConfigurationService,
    LLMProductConfigurationError,
    SETTINGS_CREDENTIAL_ERROR,
    SETTINGS_CREDENTIAL_FIELDS,
)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


class LLMSelectionRequest(BaseModel):
    provider_id: Optional[str] = Field(default=None, description="Provider id")
    model_id: Optional[str] = Field(default=None, description="Model id")


class LLMSelectionResponse(BaseModel):
    configured: bool
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    context: int = 0
    api: Optional[str] = None


class LLMProductConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: Optional[bool] = Field(default=None, description="Whether this product may use LLM assistance")
    provider_id: Optional[str] = Field(default=None, description="Configured provider id")
    provider_name: Optional[str] = Field(default=None, description="Secret-free provider display name")
    model_id: Optional[str] = Field(default=None, description="Configured model id")
    model_name: Optional[str] = Field(default=None, description="Secret-free model display name")
    allowed_operations: Optional[list[str]] = Field(default=None, description="Allowed product operations")
    budget: Optional[dict[str, Any]] = Field(default=None, description="Secret-free budget envelope metadata")
    evaluation_gate_status: Optional[str] = Field(default=None, description="Evaluation gate status metadata")
    base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("base_url", "baseUrl", "baseURL"),
        description="AEGIS OpenAI-compatible provider endpoint; rejected for AXIOM",
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="Compatibility alias for base_url",
    )
    endpoint_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("endpoint_url", "endpointUrl"),
        description="Compatibility alias for base_url",
    )
    api_base: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("api_base", "apiBase"),
        description="Compatibility alias for base_url",
    )
    api_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("api_base_url", "apiBaseUrl"),
        description="Compatibility alias for base_url",
    )
    api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("api_key", "apiKey"),
        description="Write-only AEGIS provider credential",
    )
    clear_api_key: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("clear_api_key", "clearApiKey"),
        description="Clear the stored AEGIS provider credential",
    )

class LLMValidationErrorResponse(BaseModel):
    code: str
    message: str


class LLMProductConfigurationResponse(BaseModel):
    product_id: str
    enabled: bool
    configured: bool
    status: str
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    context: int = 0
    api: Optional[str] = None
    base_url: Optional[str] = None
    endpoint_url: Optional[str] = None
    endpoint_policy: str = "deployment_managed"
    secret_status: str = "not_applicable"
    api_key_hint: Optional[str] = Field(default=None, description="Masked API key hint (e.g. 'sk-...abc4') when a key is stored")
    allowed_operations: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    evaluation_gate_status: str = "pending"
    validation_error: Optional[LLMValidationErrorResponse] = None
    updated_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LLMProductConfigurationListResponse(BaseModel):
    products: list[LLMProductConfigurationResponse]


@router.get("/providers", dependencies=[Depends(require_scope("llm:read"))])
async def list_llm_providers() -> dict:
    """Return redacted provider/model metadata for frontend model pickers."""
    return {"providers": list_provider_catalog()}


@router.get("/selection", dependencies=[Depends(require_scope("llm:read"))], response_model=LLMSelectionResponse)
async def get_current_llm_selection() -> LLMSelectionResponse:
    """Return the currently configured default LLM selection, without secrets."""
    return _selection_response(None, None)


@router.post(
    "/selection/resolve",
    dependencies=[Depends(require_scope("llm:read"))],
    response_model=LLMSelectionResponse,
)
async def resolve_llm_selection(payload: LLMSelectionRequest) -> LLMSelectionResponse:
    """Validate a frontend provider/model choice without persisting global state."""
    return _selection_response(payload.provider_id, payload.model_id)


@router.get(
    "/configuration",
    dependencies=[Depends(require_scope("llm:read"))],
    response_model=LLMProductConfigurationListResponse,
)
async def list_llm_product_configurations(
    db: Session = Depends(get_db_session),
) -> LLMProductConfigurationListResponse:
    """Return redacted effective AXIOM/AEGIS LLM configuration states."""
    service = _configuration_service(db)
    return LLMProductConfigurationListResponse(products=service.list_product_states())


@router.get(
    "/configuration/{product_id}",
    dependencies=[Depends(require_scope("llm:read"))],
    response_model=LLMProductConfigurationResponse,
)
async def get_llm_product_configuration(
    product_id: str,
    db: Session = Depends(get_db_session),
) -> LLMProductConfigurationResponse:
    """Return a redacted effective product LLM configuration state."""
    try:
        return LLMProductConfigurationResponse.model_validate(
            _configuration_service(db).get_product_state(product_id)
        )
    except LLMProductConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/configuration/{product_id}/providers",
    dependencies=[Depends(require_scope("llm:read"))],
)
async def list_llm_product_providers(
    product_id: str,
    db: Session = Depends(get_db_session),
) -> dict:
    """Return the redacted provider catalog with product selection flags."""
    try:
        return {
            "providers": _configuration_service(db).provider_catalog_for_product(product_id)
        }
    except LLMProductConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put(
    "/configuration/{product_id}",
    dependencies=[Depends(require_scope("llm:write"))],
    response_model=LLMProductConfigurationResponse,
)
async def update_llm_product_configuration(
    product_id: str,
    payload: LLMProductConfigurationRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> LLMProductConfigurationResponse:
    """Persist product LLM configuration overrides without returning secrets."""
    allow_credential_write = _allow_product_credential_write(product_id, request)
    try:
        state = _configuration_service(db).update_product_configuration(
            product_id,
            _configuration_payload(
                payload,
                allow_credential_write=allow_credential_write,
            ),
            updated_by=_request_user_id(request),
            allow_credential_write=allow_credential_write,
        )
        return LLMProductConfigurationResponse.model_validate(state)
    except LLMProductConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class LLMConnectivityCheckResponse(BaseModel):
    product_id: str
    reachable: bool
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None


@router.post(
    "/configuration/{product_id}/test",
    dependencies=[Depends(require_scope("llm:read"))],
    response_model=LLMConnectivityCheckResponse,
)
async def test_llm_product_connectivity(
    product_id: str,
    db: Session = Depends(get_db_session),
) -> LLMConnectivityCheckResponse:
    """Test LLM provider connectivity for a product configuration.

    Sends a lightweight request to the configured provider endpoint
    using the stored API key to verify the connection works.
    """
    import time as _time

    service = _configuration_service(db)
    resolved = service.resolve_product_client_config(product_id)
    if resolved is None:
        return LLMConnectivityCheckResponse(
            product_id=product_id,
            reachable=False,
            error="No LLM provider configured for this product",
        )

    import httpx

    start = _time.monotonic()
    try:
        # Use the /models endpoint as a lightweight connectivity check
        # (all OpenAI-compatible APIs support this)
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {resolved.api_key}"}
            response = await client.get(
                f"{resolved.base_url.rstrip('/')}/models",
                headers=headers,
            )
        latency_ms = int((_time.monotonic() - start) * 1000)

        if response.status_code < 500:
            return LLMConnectivityCheckResponse(
                product_id=product_id,
                reachable=response.status_code < 400,
                provider_id=resolved.provider_id,
                model_id=resolved.model_id,
                latency_ms=latency_ms,
                error=None if response.status_code < 400 else f"HTTP {response.status_code}: {response.text[:200]}",
            )

        return LLMConnectivityCheckResponse(
            product_id=product_id,
            reachable=False,
            provider_id=resolved.provider_id,
            model_id=resolved.model_id,
            latency_ms=latency_ms,
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )
    except Exception as exc:
        latency_ms = int((_time.monotonic() - start) * 1000)
        return LLMConnectivityCheckResponse(
            product_id=product_id,
            reachable=False,
            provider_id=resolved.provider_id,
            model_id=resolved.model_id,
            latency_ms=latency_ms,
            error=str(exc),
        )


def _selection_response(
    provider_id: Optional[str],
    model_id: Optional[str],
) -> LLMSelectionResponse:
    try:
        resolved = resolve_llm_config(provider_id=provider_id, model_id=model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if resolved is None:
        return LLMSelectionResponse(configured=False)

    return LLMSelectionResponse(
        configured=True,
        provider_id=resolved.provider_id,
        provider_name=resolved.provider_name,
        model_id=resolved.model_id,
        model_name=resolved.model_name,
        context=resolved.context,
        api=resolved.api,
    )


def _configuration_service(db: Session) -> LLMConfigurationService:
    return LLMConfigurationService(LLMProductConfigurationRepository(db))


def _configuration_payload(
    payload: LLMProductConfigurationRequest,
    *,
    allow_credential_write: bool = False,
) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    if SETTINGS_CREDENTIAL_FIELDS.intersection(values) and not allow_credential_write:
        raise LLMProductConfigurationError(SETTINGS_CREDENTIAL_ERROR)
    return {
        field: values[field]
        for field in LLMProductConfigurationRequest.model_fields
        if field in values
    }


def _allow_product_credential_write(product_id: str, request: Request) -> bool:
    return (
        product_id.strip().lower() in ("aegis", "axiom")
        and request.headers.get("x-inferra-secret-write") == "write-only"
    )


def _request_user_id(request: Request) -> Optional[str]:
    user_id = request.scope.get("inferra_user_id")
    return str(user_id) if user_id else None
