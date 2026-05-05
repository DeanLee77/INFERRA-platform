from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    SQLALCHEMY_DATABASE_URI: str = "postgresql://localhost:5432/inferra"
    MAX_CONTENT_LENGTH: int = 16777216
    ZAI_BASE_URL: Optional[str] = None
    ZAI_API_KEY: Optional[str] = None
    ZAI_MODEL: Optional[str] = None
    LLM_TIMEOUT: float = 30.0
    RULE_PROMPT_PATH: str = "inferra_prompt.md"
    DEMO: Optional[str] = None
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".doc"]
    ALLOWED_MIMES: List[str] = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
