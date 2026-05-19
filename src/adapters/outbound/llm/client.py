from typing import Optional

from openai import OpenAI
from src.adapters.outbound.llm.provider_registry import resolve_llm_config
from src.config import settings
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)


class LLMClient:
    _instance: Optional['LLMClient'] = None
    _client: Optional[OpenAI] = None
    _model: Optional[str] = None
    _provider_id: Optional[str] = None
    _provider_name: Optional[str] = None
    _model_name: Optional[str] = None
    _context_window: int = 0
    _base_url: Optional[str] = None
    _timeout: float = 30.0

    def __new__(
        cls,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        if provider_id or model_id:
            instance = super().__new__(cls)
            instance._initialize(provider_id=provider_id, model_id=model_id)
            return instance
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(
        self,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        self._client = None
        self._model = None
        self._provider_id = None
        self._provider_name = None
        self._model_name = None
        self._context_window = 0
        self._base_url = None
        self._timeout = settings.LLM_TIMEOUT

        try:
            resolved = resolve_llm_config(provider_id=provider_id, model_id=model_id)
        except ValueError as exc:
            _logger.warning(
                "llm_selection_invalid",
                provider_id=provider_id,
                model_id=model_id,
                error=str(exc),
            )
            return

        if resolved is None:
            _logger.warning(
                "llm_client_not_configured",
                provider_id=provider_id,
                model_id=model_id,
            )
            return

        self._model = resolved.model_id
        self._provider_id = resolved.provider_id
        self._provider_name = resolved.provider_name
        self._model_name = resolved.model_name
        self._context_window = resolved.context
        self._base_url = resolved.base_url
        self._client = OpenAI(base_url=resolved.base_url, api_key=resolved.api_key)

    @property
    def client(self) -> Optional[OpenAI]:
        return self._client

    @property
    def model(self) -> Optional[str]:
        return self._model

    @property
    def provider_id(self) -> Optional[str]:
        return self._provider_id

    @property
    def provider_name(self) -> Optional[str]:
        return self._provider_name

    @property
    def model_name(self) -> Optional[str]:
        return self._model_name

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def base_url(self) -> Optional[str]:
        return self._base_url

    @property
    def timeout(self) -> float:
        return self._timeout


def reset_llm_client() -> None:
    LLMClient._instance = None
