from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.adapters.outbound.llm.provider_registry import (
    list_provider_catalog,
    resolve_llm_config,
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


@router.get("/providers")
async def list_llm_providers() -> dict:
    """Return redacted provider/model metadata for frontend model pickers."""
    return {"providers": list_provider_catalog()}


@router.get("/selection", response_model=LLMSelectionResponse)
async def get_current_llm_selection() -> LLMSelectionResponse:
    """Return the currently configured default LLM selection, without secrets."""
    return _selection_response(None, None)


@router.post("/selection/resolve", response_model=LLMSelectionResponse)
async def resolve_llm_selection(payload: LLMSelectionRequest) -> LLMSelectionResponse:
    """Validate a frontend provider/model choice without persisting global state."""
    return _selection_response(payload.provider_id, payload.model_id)


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
