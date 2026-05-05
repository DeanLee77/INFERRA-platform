"""
Structured Logging Configuration for INFERRA.

Configures structlog with JSON output for production and
human-readable ConsoleRenderer for development. All Phase 1
modules should use structlog with mandatory fields:

- session_id: identifies the inference session
- node_id: identifies the node being processed
- fact_source: ASSERTED | INFERRED | SEMANTIC
- correlation_id: per-request tracing across layers

Usage:
    import structlog
    logger = structlog.get_logger()
    logger.info("event_name", session_id=..., node_id=...)
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

import structlog


def configure_logging(env: Optional[str] = None) -> None:
    """
    Configure structlog with mandatory fields for Phase 1 traceability.

    Args:
        env: Environment name. If "production", uses JSON renderer.
             Otherwise uses ConsoleRenderer. Defaults to the
             INFERRA_ENV environment variable or "development".
    """
    if env is None:
        env = os.environ.get("INFERRA_ENV", "development")

    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )

    processors: List[Callable[..., Any]] = [
        structlog.contextvars.merge_contextvars,       # correlation_id, session_id, etc.
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if env == "production":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> Any:
    """
    Get a structlog logger with the given name.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        A structlog BoundLogger instance
    """
    return structlog.get_logger(name)
