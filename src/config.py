from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    SQLALCHEMY_DATABASE_URI: str = "postgresql://localhost:5432/inferra"
    MAX_CONTENT_LENGTH: int = 16777216
    INFERRA_LLM_PROVIDER: Optional[str] = None
    INFERRA_LLM_MODEL: Optional[str] = None
    INFERRA_LLM_BASE_URL: Optional[str] = None
    INFERRA_LLM_API_KEY: Optional[str] = None
    INFERRA_LLM_API: str = "openai-completions"
    MODALRESEARCH_API_KEY: Optional[str] = None
    NVIDIA_API_KEY: Optional[str] = None
    ZAI_BASE_URL: Optional[str] = None
    ZAI_API_KEY: Optional[str] = None
    ZAI_MODEL: Optional[str] = None
    LLM_TIMEOUT: float = 30.0
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BACKOFF_SECONDS: float = 0.1
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = 3
    LLM_CIRCUIT_RECOVERY_TIMEOUT_SECONDS: float = 30.0
    RULE_PROMPT_PATH: str = "inferra_prompt.md"
    DEMO: Optional[str] = None
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".doc"]
    ALLOWED_MIMES: List[str] = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
