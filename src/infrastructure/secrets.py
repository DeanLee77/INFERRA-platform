from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import structlog

log = structlog.get_logger(__name__)


def read_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read an env secret, preferring Docker-style NAME_FILE indirection."""
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        try:
            value = Path(file_path).read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError as exc:
            log.warning(
                "secret_file_read_failed",
                session_id="",
                node_id="",
                fact_source="",
                correlation_id="",
                secret_name=name,
                secret_file=file_path,
                error=str(exc),
            )
    return os.environ.get(name, default)


def redis_url_from_env(env_name: str, default: str, default_db: int) -> str:
    """
    Resolve Redis URLs with Docker-secret support.

    Explicit URLs win. If the URL variable is unset or empty, this builds a
    URL from REDIS_HOST/REDIS_PORT plus REDIS_PASSWORD or REDIS_PASSWORD_FILE.
    """
    configured_url = os.environ.get(env_name)
    if configured_url:
        return configured_url

    password = read_secret("REDIS_PASSWORD")
    if not password:
        return default

    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    escaped_password = quote(password, safe="")
    return f"redis://:{escaped_password}@{host}:{port}/{default_db}"


def redis_client_from_env(env_name: str, default: str, default_db: int):
    """Create a Redis client using the same secret-aware URL resolution."""
    import redis

    return redis.Redis.from_url(redis_url_from_env(env_name, default, default_db))
