from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List, Optional

from src.infrastructure.secrets import postgres_database_uri_from_env


class Settings(BaseSettings):
    SQLALCHEMY_DATABASE_URI: str = "postgresql://localhost:5432/inferra"
    AEGIS_SQLALCHEMY_DATABASE_URI: Optional[str] = "postgresql://localhost:5432/inferra_aegis"
    AEGIS_ALLOW_SHARED_DATABASE: bool = False
    MAX_CONTENT_LENGTH: int = 16777216
    DOCUMENT_CONVERSION_MAX_PDF_PAGES: int = 100
    DOCUMENT_CONVERSION_MAX_OUTPUT_CHARS: int = 200000
    DOCUMENT_CONVERSION_MAX_EXPANSION_RATIO: float = 100.0
    DOCUMENT_CONVERSION_TIMEOUT_SECONDS: float = 20.0
    DOCUMENT_LLM_MAX_PROMPT_CHARS: int = 50000
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
    PROVIDER_EVIDENCE_ALLOW_PUBLIC_WEB_SEARCH: bool = False
    PROVIDER_EVIDENCE_ALLOW_USER_SUPPLIED_URLS: bool = True
    PROVIDER_EVIDENCE_ALLOW_USER_SUPPLIED_DOCUMENTS: bool = True
    PROVIDER_EVIDENCE_ALLOW_LLM_ADVISORY: bool = False
    PROVIDER_EVIDENCE_REQUIRE_OFFICIAL_SOURCE_CONFIRMATION: bool = True
    PROVIDER_EVIDENCE_MAX_PUBLIC_RESULTS: int = 5
    SNOMED_MBS_DATA_ROOT: str = "docs/SNOMED CT AU and MBS related"
    SNOMED_MBS_OUTPUT_DIR: str = "var/snomed_mbs"
    SNOMED_MBS_PACKAGE_PREFERENCE: str = "Snapshot"
    SNOMED_MBS_INCLUDE_ATTRIBUTE_RELATIONSHIPS: bool = False
    SNOMED_MBS_MBS_XML_URL: str = (
        "https://www.mbsonline.gov.au/internet/mbsonline/publishing.nsf/"
        "650f3eec0dfb990fca25692100069854/"
        "d4bd04ca56657072ca258df70023b066/$FILE/MBS-XML-20260701.XML"
    )
    SNOMED_MBS_MBS_XML_PATH: Optional[str] = None
    SNOMED_MBS_PHI_CLINICAL_CATEGORIES_PATH: Optional[str] = None
    RULE_PROMPT_PATH: str = "inferra_prompt.md"
    DEMO: Optional[str] = None
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".doc"]
    ALLOWED_MIMES: List[str] = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def resolve_secret_backed_database_uris(self) -> "Settings":
        self.SQLALCHEMY_DATABASE_URI = postgres_database_uri_from_env(
            "SQLALCHEMY_DATABASE_URI",
            self.SQLALCHEMY_DATABASE_URI,
            database_env_name="POSTGRES_DB",
            default_database="inferra",
        )
        self.AEGIS_SQLALCHEMY_DATABASE_URI = postgres_database_uri_from_env(
            "AEGIS_SQLALCHEMY_DATABASE_URI",
            self.AEGIS_SQLALCHEMY_DATABASE_URI or "",
            database_env_name="AEGIS_POSTGRES_DB",
            default_database="inferra_aegis",
        )
        return self


settings = Settings()
